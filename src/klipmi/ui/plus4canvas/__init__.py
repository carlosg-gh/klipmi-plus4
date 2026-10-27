# SPDX-License-Identifier: GPL-3.0-or-later
"""QIDI Plus 4 UI drawn from the host (`ui = "plus4canvas"`).

The screen runs QIDI's stock HMI; its empty `logo` page is used as a canvas and
everything on it is drawn here. Needs no editor and no custom firmware.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

from klipmi.canvas.app import App, Modal
from klipmi.canvas.gfx import FONT_L, FONT_M, FONT_S, LEFT, Rect, Theme, text
from klipmi.canvas.link import SerialLink
from klipmi.canvas import widgets as ui
from klipmi.features import mmu
from klipmi.model.ui import BaseUi
from klipmi.utils import classproperty

from .box import BoxPage
from .pages import ControlPage, FilesPage, HomePage, OfflinePage, PrintingPage, SystemPage

OPTIONAL = ("fan_generic sidefan", "fan_generic filterfan", "output_pin caselight", "heater_generic chamber")


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
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 16, p.w - 48, 34), self.title_text or "Printer", FONT_L)
        for i, ln in enumerate(self.lines[:4]):
            ui.label(c, "modal/l%d" % i, Rect(p.x + 24, p.y + 58 + i * 26, p.w - 48, 24), ln, FONT_S, Theme.MUTED)
        buttons = self.buttons[:3] or [("Close", "", "")]
        for i, ((label, gcode, color), cell) in enumerate(zip(buttons, Rect(p.x + 24, p.y + p.h - 76, p.w - 48, 58).split_h(len(buttons), 12))):
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
            "output_pin caselight": ["value"],
            "idle_timeout": ["state"],
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
                  settings_path=os.path.expanduser("~/printer_data/config/klipmi-canvas.json"),
                  nav=[
                      ("home", "Home", lambda a: True),
                      ("control", "Control", lambda a: True),
                      ("files", "Files", lambda a: True),
                      ("box", "Box", lambda a: a.has("mmu")),
                      ("system", "System", lambda a: True),
                  ])
        app.available = getattr(self, "_available", [])
        for nav_id, page in (("home", HomePage), ("control", ControlPage), ("files", FilesPage), ("box", BoxPage),
                             ("system", SystemPage)):
            app.register(nav_id, page)
        app.offline_page = OfflinePage(app)
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
