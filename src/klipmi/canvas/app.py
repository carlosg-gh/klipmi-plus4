# SPDX-License-Identifier: GPL-3.0-or-later
"""The app shell: status bar, navigation bar, pages, modals, toasts, screen sleep.

Pages draw the whole frame each time; the Canvas turns that into the few commands
that changed. While a modal is open the page underneath is frozen (not drawn), and
closing the modal repaints everything.
"""

import asyncio
import inspect
import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Type

from .gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Canvas, Rect, Theme, fill, mix, rounded,
                  text)
from . import widgets as ui

TOP = Rect(0, 0, 800, 44)
CONTENT = Rect(12, 52, 776, 348)
NAV = Rect(0, 408, 800, 72)


class Page:
    title = ""
    nav: Optional[str] = None  # nav item to highlight
    full = False  # draw over the status and nav bars too

    def __init__(self, app: "App"):
        self.app = app

    def enter(self):
        pass

    def leave(self):
        pass

    def draw(self, c: Canvas):
        pass


class Modal(Page):
    """A panel over a frozen page. Draws in `self.panel`."""

    width, height = 560, 300

    @property
    def panel(self) -> Rect:
        return Rect((800 - self.width) // 2, (480 - self.height) // 2, self.width, self.height)

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
        """`nav`: (id, caption, visible(app)) for each navigation item; pages declare `nav = id`."""
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
        self.page: Optional[Page] = None
        self.modal: Optional[Modal] = None
        self.offline_page: Optional[Page] = None
        self.toast_text, self.toast_color, self.toast_until = "", Theme.ACCENT, 0.0
        self.dirty = asyncio.Event() if _loop_running() else None
        self.repaint = True
        self.last_touch = time.time()
        self.sleeping = False
        self.swallow = False
        self.listeners: List[Callable[[dict, dict], None]] = []
        self.frames = 0

    # --- navigation ------------------------------------------------------------

    def register(self, nav_id: str, page: Type[Page]):
        self.nav_pages[nav_id] = page

    def go(self, page: Type[Page] | Page):
        if isinstance(page, type):
            page = page(self)
        if self.page is not None:
            self.page.leave()
        self.page = page
        self.canvas.pressed = None
        page.enter()
        self.repaint = True
        self.invalidate()

    def go_nav(self, nav_id: str):
        if nav_id in self.nav_pages:
            if self.page is not None and self.page.nav == nav_id and type(self.page) is self.nav_pages[nav_id]:
                return
            self.go(self.nav_pages[nav_id])

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
            self.repaint = True
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
        self.repaint = True
        self.invalidate()

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
                    result = target.action()
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
        if self.repaint:
            c.reset(Theme.BG)
            self.repaint = False
        c.begin()
        self.frames += 1
        if self.modal is not None:
            # Keep the frozen page's parts as they are and draw only the modal
            for key in list(c.shown):
                if not key.startswith("modal"):
                    c.seen.add(key)
            self._draw_modal(c)
        else:
            page = self.page
            if self.klippy != "ready" and self.offline_page is not None and not getattr(page, "allow_offline", False):
                page = self.offline_page
            if page is not None and not page.full:
                self._draw_top(c, page)
                self._draw_nav(c, page)
            if page is not None:
                page.draw(c)
        c.end()

    def _draw_top(self, c: Canvas, page: Page):
        now = time.time()
        if self.toast_text and now < self.toast_until:
            ui.card(c, "top/toast", Rect(8, 6, 784, 34), mix(self.toast_color, Theme.BG, 0.25), radius=10)
            c.op("top/toast/t", [text(Rect(20, 6, 760, 34), self.toast_text, FONT_M, Theme.TEXT,
                                      mix(self.toast_color, Theme.BG, 0.25), LEFT)])
            return
        c.op("top/bar", [fill(TOP, Theme.BG)])
        c.op("top/bar/title", [text(Rect(16, 6, 420, 34), page.title, FONT_M, Theme.TEXT, Theme.BG, LEFT)])
        state = self.print_state if self.klippy == "ready" else self.klippy
        color = {"printing": Theme.ACCENT, "paused": Theme.WARN, "error": Theme.ERR, "complete": Theme.OK,
                 "cancelled": Theme.MUTED, "shutdown": Theme.ERR, "startup": Theme.WARN}.get(state, Theme.RAISED)
        ink = Theme.TEXT if color in (Theme.RAISED, Theme.MUTED, Theme.ERR) else Theme.BG
        ui.chip(c, "top/bar/state", Rect(590, 10, 120, 26), state.capitalize(), color, Theme.BG, ink)
        c.op("top/bar/clock", [text(Rect(716, 6, 76, 34), time.strftime("%H:%M"), FONT_M, Theme.MUTED, Theme.BG, RIGHT)])

    def _draw_nav(self, c: Canvas, page: Page):
        items = [(i, cap) for i, cap, visible in self.nav_items if visible(self)]
        c.op("nav", [fill(NAV, Theme.BG), fill(Rect(0, NAV.y, 800, 1), Theme.SURFACE)])
        cells = Rect(8, NAV.y + 8, 784, NAV.h - 16).split_h(len(items), 8)
        for (nav_id, caption), cell in zip(items, cells):
            ui.button(c, "nav/" + nav_id, cell, caption, (lambda n=nav_id: self.go_nav(n)),
                      style=ui.ACCENT if page.nav == nav_id else ui.GHOST, bg=Theme.BG, radius=16)

    def _draw_modal(self, c: Canvas):
        m = self.modal
        p = m.panel
        c.op("modal", rounded(Rect(p.x - 3, p.y - 3, p.w + 6, p.h + 6), Theme.RAISED, 18) + rounded(p, Theme.SURFACE, 16))
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
