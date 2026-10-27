# SPDX-License-Identifier: GPL-3.0-or-later
"""QIDI Plus 4 UI drawn from the host (`ui = "plus4canvas"`).

Runs on our own minimal HMI firmware (hmi/plus4-canvas): one blank page, fonts and pictures; everything on
the glass is drawn here. Layout: icon rail on the left, status bar on top, pages in CONTENT.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

from klipmi.canvas.app import App, Modal
from klipmi.canvas.gfx import FONT_SB, FONT_XS, LEFT, Rect, Theme, text
from klipmi.canvas.link import SerialLink
from klipmi.canvas import widgets as ui
from klipmi.features import mmu
from klipmi.model.ui import BaseUi
from klipmi.utils import classproperty

from .box import FilamentPage
from .calibrate import CalibratePage
from .dialogs import ManualProbe, confirm, wrapped
from .files import FilesPage
from .home import HomePage, PrintingPage
from .motion import FansPage, MovePage, TempPage
from .system import OfflinePage, SystemPage

NAV = [
    ("home", "home", lambda a: True),
    ("move", "move", lambda a: True),
    ("temp", "temp", lambda a: True),
    ("fans", "fan", lambda a: True),
    ("filament", "spool", lambda a: a.has("mmu")),
    ("files", "files", lambda a: True),
    ("calibrate", "target", lambda a: True),
    ("system", "sys", lambda a: True),
]
PAGES = {"home": HomePage, "move": MovePage, "temp": TempPage, "fans": FansPage, "filament": FilamentPage,
         "files": FilesPage, "calibrate": CalibratePage, "system": SystemPage}


class Prompt(Modal):
    """Klipper `action:prompt` dialogs (used by Happy Hare and many macros)."""

    width = 600

    def __init__(self, app: App, title: str):
        super().__init__(app)
        self.title_text = title
        self.lines: List[str] = []
        self.buttons: List[tuple] = []
        self.height = 300

    def draw(self, c):
        p = self.panel
        c.op("modal/title", [text(Rect(p.x + 24, p.y + 14, p.w - 48, 40), self.title_text or "Printer", FONT_SB, Theme.TEXT,
                                  Theme.SURFACE, LEFT)])
        wrapped(c, "modal/body", Rect(p.x + 24, p.y + 60, p.w - 48, 140), " ".join(self.lines), FONT_XS, Theme.MUTED,
                Theme.SURFACE, 5, 28)
        buttons = self.buttons[:3] or [("Close", "", "")]
        for i, ((label, gcode, color), cell) in enumerate(zip(buttons, Rect(p.x + 20, p.y + p.h - 76, p.w - 40, 56)
                                                              .split_h(len(buttons), 8))):
            style = {"error": ui.DANGER, "primary": ui.ACCENT, "info": ui.ACCENT, "warning": ui.DANGER}.get(color, ui.NORMAL)
            ui.button(c, "modal/b%d" % i, cell, label, (lambda g=gcode: self._press(g)), style=style)

    def _press(self, gcode: str):
        self.close()
        if gcode:
            self.app.gcode(gcode)


class CanvasUI(BaseUi):
    ownsDisplay = True

    @classproperty
    def printerObjects(cls) -> Dict[str, Optional[List[str]]]:
        return {
            "webhooks": ["state", "state_message"],
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
            "heater_generic chamber": ["temperature", "target"],
            "print_stats": None,
            "display_status": None,
            "virtual_sdcard": ["progress", "is_active"],
            "gcode_move": ["speed_factor", "extrude_factor", "homing_origin"],
            "toolhead": ["homed_axes", "position"],
            "fan": ["speed"],
            "fan_generic sidefan": ["speed"],
            "fan_generic filterfan": ["speed"],
            "heater_fan hotend_fan": ["speed"],
            "heater_fan chamber_heater_fan": ["speed"],
            "temperature_fan Mainboard_fan": ["speed"],
            "output_pin caselight": ["value"],
            "idle_timeout": ["state"],
            "exclude_object": ["objects", "excluded_objects"],
            "manual_probe": ["is_active", "z_position"],
            "bed_mesh": ["profile_name", "probed_matrix", "profiles"],
        }

    def __init__(self, state):
        super().__init__(state)
        self.app: Optional[App] = None
        self.link: Optional[SerialLink] = None
        self.pending = ("startup", "")
        self.prompt: Optional[Prompt] = None
        self.reopening = False

    async def resolveObjects(self, available, query):
        objects = {k: v for k, v in self.printerObjects.items() if k in available}
        if self.state.options.klipmi.mmu != "off":
            objects.update(await mmu.resolveObjects(available, query))
        if self.app is not None:
            self.app.available = list(objects)
        self._available = list(objects)
        return objects

    async def start(self):
        options = self.state.options.klipmi
        self.link = SerialLink(options.device, fast=921600, slow=options.baud or 115200)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.link.open)
        app = App(self.link.write, self.state.printer,
                  settings_path=os.path.expanduser("~/printer_data/config/klipmi-canvas.json"), nav=NAV)
        app.available = getattr(self, "_available", [])
        for nav_id, page in PAGES.items():
            app.register(nav_id, page)
        app.printing_page = PrintingPage
        app.offline_page = OfflinePage(app)
        app.on_estop = lambda: confirm(app, "Emergency stop", "Stops all motors and heaters at once. Klipper needs a "
                                       "firmware restart afterwards.", "Stop now",
                                       lambda: app.spawn(app.call("printer.emergency_stop")))
        app.listeners.append(self._watch)
        app.sink("dim=%d" % app.settings["brightness"])
        self.app = app
        app.set_klippy(*self.pending)
        app.go(HomePage)
        self.link.on_touch = app.touch
        self.link.on_restart = self._display_restarted
        self.link.start(loop)
        app.spawn(app.run())

    # --- klipmi callbacks ------------------------------------------------------------

    def _klippy(self, state: str):
        self.pending = (state, "")
        if self.app is not None:
            self.app.set_klippy(state, self.app.klippy_message if state != "ready" else "")
            if state != "ready":
                self.app.spawn(self._message())

    async def _message(self):
        try:
            info = await self.state.printer.client.call_method("printer.info")
            self.app.set_klippy(info.get("state", self.app.klippy) if self.app.klippy != "disconnected" else "disconnected",
                                info.get("state_message", ""))
        except Exception:
            pass

    def onNotReady(self):
        self._klippy("startup")

    def onReady(self):
        self._klippy("ready")

    def onStopped(self):
        self._klippy("disconnected")

    def onMoonrakerError(self):
        self._klippy("disconnected")

    def onKlipperError(self):
        self._klippy("error")

    async def onPrinterStatusUpdate(self, data: dict):
        if self.app is not None:
            self.app.update(data)

    async def onFileListUpdate(self, data: dict):
        if self.app is not None and isinstance(self.app.page, FilesPage):
            self.app.spawn(self.app.page.load())

    def onGcodeResponse(self, line: str):
        app = self.app
        if app is None:
            return
        if line.startswith("// action:prompt_"):
            self._prompt(line[len("// action:prompt_"):])
        elif line.startswith("!! "):
            app.toast(line[3:], Theme.ERR, 8)

    def _prompt(self, cmd: str):
        app = self.app
        verb, _, arg = cmd.partition(" ")
        if verb == "begin":
            self.prompt = Prompt(app, arg)
        elif self.prompt is None:
            return
        elif verb == "text":
            self.prompt.lines.append(arg)
        elif verb in ("button", "footer_button"):
            parts = arg.split("|")
            self.prompt.buttons.append((parts[0], parts[1] if len(parts) > 1 else parts[0], parts[2] if len(parts) > 2 else ""))
        elif verb == "show":
            app.open_modal(self.prompt)
        elif verb == "end":
            if app.modal is self.prompt:
                app.close_modal()
            self.prompt = None

    def _watch(self, status: dict, old: dict):
        app = self.app
        new = app.print_state
        if new != old["print_state"]:
            if new == "printing" and old["print_state"] not in ("printing", "paused") and app.modal is None:
                app.go(PrintingPage)
            elif new == "complete":
                app.toast("Print complete", Theme.OK, 10)
            elif new == "error":
                app.toast("Print failed: %s" % (app.get("print_stats", "message", "") or "see Mainsail"), Theme.ERR, 10)
        probing = bool(app.get("manual_probe", "is_active", False))
        if probing and not isinstance(app.modal, ManualProbe):
            app.open_modal(ManualProbe(app))
        elif not probing and isinstance(app.modal, ManualProbe):
            app.close_modal()

    def _display_restarted(self):
        if self.reopening:
            return
        self.reopening = True

        async def reopen():
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.link.open)
                self.app.sink("dim=%d" % self.app.settings["brightness"])
                self.app.repaint = True
                self.app.invalidate()
            finally:
                self.reopening = False

        self.app.spawn(reopen())
