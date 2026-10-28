# SPDX-License-Identifier: GPL-3.0-or-later
"""The app shell: icon rail, status bar, pages, modals, toasts, screen sleep.

Pages draw the whole frame each time; the Canvas turns that into the few commands
that changed. While a modal is open the page underneath is frozen (not drawn) but the
rail and status bar stay live; closing the modal repaints the page area.
Modals are either sheets (they cover CONTENT) or dialogs (a framed panel inside CONTENT).
"""

import asyncio
import inspect
import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Type

from .gfx import (FONT_XSB, LEFT, Canvas, Rect, Theme, fill, icon, mix, rounded, soft_disc, text, text_width)
from . import widgets as ui

RAIL = Rect(0, 0, 72, 480)  # permanent icon rail
TOP = Rect(72, 0, 728, 48)  # status bar
CONTENT = Rect(72, 50, 720, 422)
AREA = Rect(72, 48, 728, 432)  # everything a page may repaint
RAIL_ITEM = 48
SPLASH_SECONDS = 240  # after this long without the printer ever being ready, show the offline card with its buttons
STATE_COLOR = {"printing": Theme.ACCENT, "paused": Theme.WARN, "error": Theme.ERR, "complete": Theme.OK,
               "cancelled": Theme.MUTED, "shutdown": Theme.ERR, "startup": Theme.WARN, "disconnected": Theme.ERR}


class Page:
    title = ""
    nav: Optional[str] = None  # rail item to highlight
    bar_temps = True  # show heater readings in the status bar

    def __init__(self, app: "App"):
        self.app = app

    def enter(self):
        pass

    def leave(self):
        pass

    def draw(self, c: Canvas):
        pass


class Modal(Page):
    """Over a frozen page. A sheet (`sheet = True`) owns all of CONTENT on the page background; a dialog is a
    framed SURFACE panel centred in CONTENT. Draws in `self.panel`."""

    width, height = 560, 300
    sheet = False

    @property
    def panel(self) -> Rect:
        if self.sheet:
            return CONTENT
        return Rect(CONTENT.x + (CONTENT.w - self.width) // 2, CONTENT.y + (CONTENT.h - self.height) // 2,
                    self.width, self.height)

    def close(self):
        self.app.close_modal(self)


class Settings:
    """Small per-device preferences, kept in a JSON file next to the config."""

    defaults = {"brightness": 100, "sleep_minutes": 10}

    def __init__(self, path: str):
        self.path = path
        self.values = dict(self.defaults)
        try:
            with open(path, encoding="utf-8") as f:
                self.values.update(json.load(f))
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.values, f)
        except OSError as e:
            logging.warning("could not save settings: %s", e)


class App:
    def __init__(self, sink: Callable[[str], None], printer=None, settings_path: str = "",
                 nav: Sequence[Tuple[str, str, Callable[["App"], bool]]] = ()):
        """`nav`: (id, icon, visible(app)) for each rail item; pages declare `nav = id`."""
        self.canvas = Canvas(sink)
        self.sink = sink
        self.printer = printer
        self.settings = Settings(settings_path or os.path.expanduser("~/.klipmi-canvas.json"))
        self.nav_items = list(nav)
        self.nav_pages: Dict[str, Type[Page]] = {}
        self.status: dict = {}
        self.available: List[str] = []
        self.klippy = "startup"
        self.klippy_message = ""
        self.started = time.time()
        self.was_ready = False
        self.was_splash = False
        self.page: Optional[Page] = None
        self.modal: Optional[Modal] = None
        self.offline_page: Optional[Page] = None
        self.toast_text, self.toast_color, self.toast_until = "", Theme.ACCENT, 0.0
        self.dirty = asyncio.Event() if _loop_running() else None
        self.repaint = True
        self.clear_content = False
        self.close_area: Optional[Rect] = None
        self.last_touch = time.time()
        self.sleeping = False
        self.swallow = False
        self.listeners: List[Callable[[dict, dict], None]] = []
        self.frames = 0
        self.on_estop: Optional[Callable[[], None]] = None  # the rail's stop button
        self.printing_page: Optional[Type[Page]] = None  # what Home shows while a print runs

    # --- navigation ------------------------------------------------------------

    def register(self, nav_id: str, page: Type[Page]):
        self.nav_pages[nav_id] = page

    def go(self, page: Type[Page] | Page):
        if isinstance(page, type):
            page = page(self)
        if self.modal is not None:  # the rail stays live under a modal: leaving the page closes it
            self.modal.leave()
            self.modal = None
            self.close_area = None
        if self.page is not None:
            self.page.leave()
        self.page = page
        self.canvas.pressed = None
        page.enter()
        self.clear_content = True
        self.invalidate()

    def go_nav(self, nav_id: str):
        if nav_id in self.nav_pages:
            if self.page is not None and self.page.nav == nav_id and type(self.page) is self.nav_pages[nav_id] \
                    and self.modal is None:
                return
            target = self.nav_pages[nav_id]
            if nav_id == "home" and self.printing and self.printing_page is not None:
                target = self.printing_page
            self.go(target)

    def open_modal(self, modal: Modal):
        self.modal = modal
        self.canvas.pressed = None
        modal.enter()
        self.invalidate()

    def close_modal(self, modal: Optional[Modal] = None):
        if modal is None or modal is self.modal:
            if self.modal is not None:
                self.modal.leave()
            self.modal = None
            self.close_area = self.canvas.region_of("modal")
            self.invalidate()

    def toast(self, message: str, color: int = Theme.ACCENT, seconds: float = 5.0):
        self.toast_text, self.toast_color, self.toast_until = message, color, time.time() + seconds
        self.invalidate()

    # --- printer helpers -------------------------------------------------------

    def has(self, obj: str) -> bool:
        return obj in self.available

    def get(self, obj: str, field: str, default=None):
        return self.status.get(obj, {}).get(field, default)

    def gcode(self, script: str):
        logging.info("gcode: %s", script.replace("\n", " | "))
        if self.printer is not None:
            self.printer.runGcode(script)

    def call(self, method: str, **params):
        """Moonraker JSON-RPC call; returns an awaitable result."""
        return self.printer.client.call_method(method, **params)

    def spawn(self, coro):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(_log_failure)
        return task

    @property
    def print_state(self) -> str:
        return self.get("print_stats", "state", "standby") or "standby"

    @property
    def printing(self) -> bool:
        return self.print_state in ("printing", "paused")

    # --- events ----------------------------------------------------------------

    def update(self, status: dict):
        old_state = self.print_state
        self.status = status
        for listener in self.listeners:
            listener(status, {"print_state": old_state})
        self.invalidate()

    def set_klippy(self, state: str, message: str = ""):
        self.klippy, self.klippy_message = state, message
        self.was_ready = self.was_ready or state == "ready"
        self.repaint = True
        self.invalidate()

    def splashing(self) -> bool:
        """True while the printer is still booting: a full-screen splash instead of the rail and the offline card."""
        return (self.klippy in ("startup", "connecting", "disconnected") and not self.was_ready
                and time.time() - self.started < SPLASH_SECONDS)

    def invalidate(self):
        if self.dirty is not None:
            self.dirty.set()

    def touch(self, x: int, y: int, pressed: bool):
        self.last_touch = time.time()
        if self.sleeping:
            self.sleeping = False
            self.swallow = True
            self.sink("dim=%d" % self.settings["brightness"])
            return
        if self.swallow:  # the touch that woke the screen does nothing else
            if not pressed:
                self.swallow = False
            return
        target = self.canvas.find(x, y)
        if pressed:
            self.canvas.pressed = target.key if target else None
        else:
            if target is not None and target.key == self.canvas.pressed:
                self.canvas.pressed = None
                try:
                    result = target.action(x, y) if target.wants_xy else target.action()
                    if inspect.isawaitable(result):
                        self.spawn(result)
                except Exception:
                    logging.exception("touch action failed")
            self.canvas.pressed = None
        self.invalidate()

    # --- loop ------------------------------------------------------------------

    async def run(self):
        self.dirty = asyncio.Event()
        self.dirty.set()
        while True:
            try:
                await asyncio.wait_for(self.dirty.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
            self.dirty.clear()
            self._sleep_check()
            if not self.sleeping:
                try:
                    self.render()
                except Exception:
                    logging.exception("render failed")
                    self.repaint = True
            await asyncio.sleep(0.03)  # at most ~30 frames a second

    def _sleep_check(self):
        minutes = self.settings["sleep_minutes"]
        if minutes and not self.sleeping and not self.printing and time.time() - self.last_touch > minutes * 60:
            self.sleeping = True
            self.sink("dim=3")

    def render(self):
        c = self.canvas
        splash = (self.klippy != "ready" and self.offline_page is not None
                  and not getattr(self.page, "allow_offline", False) and self.splashing())
        if splash != self.was_splash:  # the rail and status bar appear or disappear: repaint everything
            self.was_splash = splash
            self.repaint = True
        if self.repaint:
            c.reset(Theme.BG)
            self.repaint = self.clear_content = False
            self.close_area = None
        if self.close_area is not None and self.modal is None:
            c.clear_region(self.close_area, Theme.BG, drop=lambda k: k.startswith("modal"))
            self.close_area = None
        if self.clear_content and self.modal is None:
            # New page: keep the status and navigation bars, repaint only the page area
            c.clear_region(AREA, Theme.BG,
                           drop=lambda k: not (k.startswith("top") or k.startswith("nav")))
            self.clear_content = False
        c.begin()
        self.frames += 1
        page = self.page
        if self.klippy != "ready" and self.offline_page is not None and not getattr(page, "allow_offline", False):
            page = self.offline_page
        if page is not None and not splash:
            self._draw_top(c, self.modal or page)
            self._draw_nav(c, self.modal if self.modal is not None and self.modal.nav else page)
        if self.modal is not None:
            # Keep the frozen page's parts as they are and draw only the modal
            for key in list(c.shown):
                if not (key.startswith("modal") or key.startswith("top") or key.startswith("nav")):
                    c.seen.add(key)
            self._draw_modal(c)
        elif page is not None:
            page.draw(c)
        c.end()

    def heater_readings(self):
        """(icon, temperature) for the status bar."""
        out = []
        for obj, name in (("extruder", "nozzle"), ("heater_bed", "bed"), ("heater_generic chamber", "chamber")):
            if self.has(obj):
                out.append((name, self.get(obj, "temperature", None)))
        return out

    def _draw_top(self, c: Canvas, page: Page):
        now = time.time()
        bar = Rect(TOP.x + 6, 6, TOP.w - 14, 36)
        if self.toast_text and now < self.toast_until:
            face = mix(self.toast_color, Theme.BG, 0.3)
            ui.card(c, "top/toast", Rect(TOP.x, 4, TOP.w - 8, 40), face, radius=10)
            c.op("top/toast/t", [text(Rect(TOP.x + 16, 4, TOP.w - 40, 40), self.toast_text, FONT_XSB, Theme.TEXT, face, LEFT)])
            return
        c.op("top/bar", [fill(TOP, Theme.BG)])
        state = self.print_state if self.klippy == "ready" else self.klippy
        caption = {"standby": "Idle", "complete": "Done"}.get(state, state.capitalize())
        if state in ("printing", "paused"):
            caption += "  %d%%" % int((self.get("display_status", "progress", 0.0) or 0.0) * 100)
        heating = any((self.get(o, "target", 0) or 0) > (self.get(o, "temperature", 0) or 0) + 2
                      for o in ("extruder", "heater_bed", "heater_generic chamber") if self.has(o))
        if state == "standby" and heating:
            caption = "Heating"
        color = STATE_COLOR.get(state, Theme.WARN if heating else Theme.OK)
        cw = text_width(caption, FONT_XSB) + 4
        c.op("top/bar/state", soft_disc(bar.x + 6, bar.y + 18, 5, color, Theme.BG) +
             [text(Rect(bar.x + 20, bar.y, cw, 36), caption, FONT_XSB, Theme.TEXT, Theme.BG, LEFT),
              fill(Rect(bar.x + 20 + cw, bar.y, 300 - cw, 36), Theme.BG)])
        # right side, laid out from the right edge: clock, wifi, then the heaters
        clock = time.strftime("%H:%M")
        x = bar.x + bar.w
        w = text_width(clock, FONT_XSB) + 2
        x -= w
        cmds = [fill(Rect(bar.x + 320, bar.y, bar.w - 320, 36), Theme.BG),
                text(Rect(x, bar.y, w, 36), clock, FONT_XSB, Theme.TEXT, Theme.BG, LEFT)]
        x -= 8 + 24
        cmds.append(icon("wifi", x, bar.y + 6, 24, Theme.BG, Theme.MUTED))
        if page.bar_temps:
            for name, t in reversed(self.heater_readings()):
                s = ui.temp_str(t)
                w = text_width(s, FONT_XSB) + 1 + ui.deg_width(FONT_XSB)
                x -= 18 + w
                cmds += ui.value_cmds(Rect(x, bar.y, w, 36), s, FONT_XSB, Theme.TEXT, Theme.BG, LEFT, True)
                x -= 6 + 24
                cmds.append(icon(name, x, bar.y + 6, 24, Theme.BG, Theme.MUTED))
        c.op("top/bar/right", cmds)

    def _draw_nav(self, c: Canvas, page: Page):
        items = [(i, ic) for i, ic, visible in self.nav_items if visible(self)]
        c.op("nav", [fill(RAIL, Theme.BG)])
        for k, (nav_id, icon_name) in enumerate(items):
            cell = Rect(8, 6 + k * (RAIL_ITEM + 4), 56, RAIL_ITEM)
            on = page.nav == nav_id
            ui.button(c, "nav/" + nav_id, cell, "", (lambda n=nav_id: self.go_nav(n)),
                      style=ui.QUIET if not on else ui.NORMAL, bg=Theme.BG, icon_name=icon_name, icon_size=32,
                      icon_ink=Theme.ACCENT if on else Theme.MUTED, face=Theme.SURFACE if on else None)
        ui.button(c, "nav/stop", Rect(8, RAIL.h - 6 - RAIL_ITEM, 56, RAIL_ITEM), "", self.on_estop, style=ui.DANGER,
                  bg=Theme.BG, icon_name="stop", icon_size=32)

    def _draw_modal(self, c: Canvas):
        m = self.modal
        p = m.panel
        if m.sheet:
            c.op("modal", [fill(AREA, Theme.BG)])
        else:  # a light frame, on a margin of page background so its corners have a known backdrop
            outer = Rect(p.x - 10, p.y - 10, p.w + 20, p.h + 20)
            c.op("modal", [fill(outer, Theme.BG)] + rounded(Rect(p.x - 2, p.y - 2, p.w + 4, p.h + 4), Theme.BORDER, 12, Theme.BG)
                 + rounded(p, Theme.SURFACE, 10, Theme.BORDER))
        m.draw(c)


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _log_failure(task: asyncio.Task):
    if not task.cancelled() and task.exception() is not None:
        logging.error("background task failed", exc_info=task.exception())
