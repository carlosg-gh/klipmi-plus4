# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the Plus 4 canvas UI: home, printing, control, files, system and the offline screen."""

import asyncio
import logging
import socket
import time
from typing import List, Optional

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Rect, Theme, disc, fill, heat_color, mix,
                               rounded, text)

from .dialogs import Choice, choose, confirm, keypad

HEATERS = [
    ("extruder", "Nozzle", 0, 300, 200.0),
    ("heater_bed", "Bed", 0, 120, 80.0),
    ("heater_generic chamber", "Chamber", 0, 65, 50.0),
]
PRESETS = [("PLA", 210, 60, 0), ("PETG", 240, 80, 0), ("ABS", 255, 100, 55), ("ASA", 260, 100, 60)]


def heater_gcode(obj: str, target: float) -> str:
    if obj == "extruder":
        return "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=%d" % target
    if obj == "heater_bed":
        return "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=%d" % target
    return "SET_HEATER_TEMPERATURE HEATER=%s TARGET=%d" % (obj.split(" ", 1)[1], target)


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--"
    seconds = int(seconds)
    h, m = seconds // 3600, (seconds % 3600) // 60
    return "%dh %02dm" % (h, m) if h else "%dm %02ds" % (m, seconds % 60)


def wrap(s: str, width_chars: int, max_lines: int) -> List[str]:
    out: List[str] = []
    for para in str(s).splitlines() or [""]:
        line = ""
        for word in para.split():
            if len(line) + len(word) + 1 > width_chars and line:
                out.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        out.append(line)
    return out[:max_lines]


def set_target(app: App, obj: str, name: str, lo: int, hi: int):
    current = app.get(obj, "target", 0) or 0
    presets = []
    for preset, nozzle, bed, chamber in PRESETS:
        value = {"extruder": nozzle, "heater_bed": bed}.get(obj, chamber)
        if value:
            presets.append((preset, value))
    presets.append(("Off", 0))
    keypad(app, "%s target" % name, current, lo, hi, lambda v: app.gcode(heater_gcode(obj, v)), unit="C",
           presets=presets)


def preheat(app: App):
    def apply(nozzle, bed, chamber):
        script = [heater_gcode("extruder", nozzle), heater_gcode("heater_bed", bed)]
        if chamber and app.has("heater_generic chamber"):
            script.append(heater_gcode("heater_generic chamber", chamber))
        app.gcode("\n".join(script))
        app.toast("Preheating")

    options = [(name, "%d / %d C" % (n, b), (lambda n=n, b=b, ch=ch: apply(n, b, ch))) for name, n, b, ch in PRESETS]
    options.append(("Cool down", "all heaters off", lambda: cool_down(app)))
    choose(app, "Preheat", options)


def cool_down(app: App):
    app.gcode("\n".join(heater_gcode(obj, 0) for obj, *_ in HEATERS if app.has(obj)))
    app.toast("Heaters off")


def heater_tile(app: App, c, key: str, r: Rect, obj: str, name: str, lo: int, hi: int, hot_at: float):
    temp = app.get(obj, "temperature", 0.0) or 0.0
    target = app.get(obj, "target", 0.0) or 0.0
    accent = heat_color(temp, hot_at)
    pressed = c.pressed == key
    face = mix(Theme.SURFACE, Theme.TEXT, 0.08) if pressed else Theme.SURFACE
    ui.card(c, key, r, face)
    c.op(key + "/strip", rounded(Rect(r.x, r.y + 14, 6, r.h - 28), accent, 3))
    c.op(key + "/name", [text(Rect(r.x + 20, r.y + 10, r.w - 70, 22), name.upper(), FONT_S, Theme.MUTED, face, LEFT)])
    ui.big_text(c, key + "/temp", r.x + 20, r.y + 38, "%d" % round(temp), 46, Theme.TEXT, face)
    heating = target > 0
    c.op(key + "/target", [text(Rect(r.x + r.w - 104, r.y + r.h - 34, 90, 26),
                                ("> %d C" % target) if heating else "off", FONT_M,
                                accent if heating else Theme.FAINT, face, RIGHT)])
    ui.dot(c, key + "/dot", r.x + r.w - 22, r.y + 21, 7, accent if heating else Theme.RAISED, face)
    c.hit(key, r, lambda: set_target(app, obj, name, lo, hi))


# --- Home ------------------------------------------------------------------------

class HomePage(Page):
    title = "Plus 4"
    nav = "home"

    def draw(self, c):
        app = self.app
        tiles = [h for h in HEATERS if app.has(h[0])]
        for (obj, name, lo, hi, hot), r in zip(tiles, Rect(12, 52, 250, 348).split_v(3, 12)):
            heater_tile(app, c, "home/h/" + obj, r, obj, name, lo, hi, hot)
        self.job(c, Rect(274, 52, 514, 228))
        self.quick(c, Rect(274, 292, 514, 108))

    def job(self, c, r: Rect):
        app = self.app
        state = app.print_state
        k = "home/job" + ("P" if app.printing else "I")  # a new key per mode repaints the whole card
        ui.card(c, k, r)
        filename = app.get("print_stats", "filename", "") or ""
        inner = r.inset(20, 16)
        if app.printing:
            progress = app.get("display_status", "progress", 0.0) or 0.0
            c.op(k + "/name", [text(inner.row(0, 26), filename or "Printing", FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
            ui.big_text(c, k + "/pct", inner.x, inner.y + 40, "%d%%" % int(progress * 100), 64,
                        Theme.ACCENT if state == "printing" else Theme.WARN, Theme.SURFACE)
            duration = app.get("print_stats", "print_duration", 0.0) or 0.0
            left = duration / progress - duration if progress > 0.02 else None
            info = app.get("print_stats", "info", {}) or {}
            layer = "%s / %s" % (info.get("current_layer") or "-", info.get("total_layer") or "-")
            stats = Rect(inner.x + 250, inner.y + 40, inner.w - 250, 70)
            c.op(k + "/s1", [text(stats.row(0, 22), "Remaining  " + fmt_duration(left), FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
            c.op(k + "/s2", [text(stats.row(26, 22), "Layer  " + layer, FONT_M, Theme.MUTED, Theme.SURFACE, LEFT)])
            c.op(k + "/s3", [text(stats.row(52, 22), "Elapsed  " + fmt_duration(duration), FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
            ui.bar(c, k + "/bar", Rect(inner.x, inner.y + 120, inner.w, 14), progress,
                   Theme.ACCENT if state == "printing" else Theme.WARN)
            row = Rect(inner.x, inner.y + inner.h - 50, inner.w, 50).split_h(2, 12)
            ui.button(c, k + "/open", row[0], "Details", lambda: self.app.go(PrintingPage), style=ui.ACCENT)
            if state == "paused":
                ui.button(c, k + "/pr", row[1], "Resume", lambda: app.gcode("RESUME"))
            else:
                ui.button(c, k + "/pr", row[1], "Pause", lambda: app.gcode("PAUSE"))
        else:
            headline = {"complete": "Print complete", "cancelled": "Print cancelled", "error": "Print failed"}.get(state, "Ready")
            color = {"complete": Theme.OK, "error": Theme.ERR}.get(state, Theme.TEXT)
            c.op(k + "/name", [text(inner.row(0, 34), headline, FONT_L, color, Theme.SURFACE, LEFT)])
            message = app.get("display_status", "message", "") or ""
            sub = filename if state in ("complete", "cancelled", "error") and filename else (message or "Pick a file to start printing.")
            c.op(k + "/sub", [text(inner.row(44, 24), sub, FONT_M, Theme.MUTED, Theme.SURFACE, LEFT)])
            temps = []
            for obj, name, *_ in HEATERS:
                if app.has(obj) and (app.get(obj, "target", 0) or 0) > 0:
                    temps.append("%s %d C" % (name.lower(), app.get(obj, "target")))
            c.op(k + "/heat", [text(inner.row(76, 24), ("Heating: " + ", ".join(temps)) if temps else "All heaters off",
                                        FONT_S, Theme.WARN if temps else Theme.FAINT, Theme.SURFACE, LEFT)])
            row = Rect(inner.x, inner.y + inner.h - 60, inner.w, 60).split_h(3, 12)
            ui.button(c, k + "/files", row[0], "Print", lambda: app.go_nav("files"), style=ui.ACCENT)
            ui.button(c, k + "/pre", row[1], "Preheat", lambda: preheat(app))
            ui.button(c, k + "/cool", row[2], "Cool down", lambda: cool_down(app))

    def quick(self, c, r: Rect):
        app = self.app
        cells = r.split_h(4, 12)
        light = app.get("output_pin caselight", "value", None)
        ui.card(c, "home/q/light", cells[0])
        c.op("home/q/light/t", [text(Rect(cells[0].x + 16, cells[0].y + 12, cells[0].w - 32, 22), "Light", FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        if light is not None:
            ui.toggle(c, "home/q/light/sw", Rect(cells[0].x + 16, cells[0].y + 56, 72, 36), light > 0,
                      lambda: app.gcode("SET_PIN PIN=caselight VALUE=%d" % (0 if light > 0 else 1)))
        else:
            c.op("home/q/light/na", [text(Rect(cells[0].x + 16, cells[0].y + 56, 90, 30), "n/a", FONT_S, Theme.FAINT, Theme.SURFACE, LEFT)])
        fan = app.get("fan", "speed", 0.0) or 0.0
        ui.button(c, "home/q/fans", cells[1], "Fans", lambda: app.go(ControlPage.tab(app, 2)), style=ui.NORMAL,
                  sub="part %d%%" % round(fan * 100))
        if app.has("mmu"):
            from .box import mmu_summary
            ui.button(c, "home/q/box", cells[2], "Box", lambda: app.go_nav("box"), sub=mmu_summary(app))
        else:
            ui.button(c, "home/q/box", cells[2], "Motors", lambda: app.gcode("M84"), sub="turn off")
        ui.button(c, "home/q/stop", cells[3], "STOP", lambda: confirm(
            app, "Emergency stop", "Stops all motors and heaters at once. Klipper needs a firmware restart afterwards.",
            "Stop now", lambda: app.spawn(app.call("printer.emergency_stop"))), style=ui.DANGER)


# --- Printing ----------------------------------------------------------------------

class PrintingPage(Page):
    title = "Printing"
    nav = "home"

    def __init__(self, app):
        super().__init__(app)
        self.estimate = {}

    def enter(self):
        self.app.spawn(self._metadata())

    async def _metadata(self):
        name = self.app.get("print_stats", "filename", "")
        if name:
            try:
                self.estimate = await self.app.call("server.files.metadata", filename=name)
            except Exception as e:
                logging.info("no metadata for %s: %s", name, e)
            self.app.invalidate()

    def draw(self, c):
        app = self.app
        state = app.print_state
        r = Rect(12, 52, 776, 348)
        ui.card(c, "pr/card", r)
        name = app.get("print_stats", "filename", "") or "No file"
        c.op("pr/card/name", [text(Rect(32, 66, 600, 30), name, FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
        ui.chip(c, "pr/card/state", Rect(660, 70, 110, 26), state.capitalize(),
                {"printing": Theme.ACCENT, "paused": Theme.WARN, "complete": Theme.OK, "error": Theme.ERR}.get(state, Theme.RAISED),
                Theme.SURFACE, Theme.BG if state in ("printing", "paused", "complete") else Theme.TEXT)
        progress = app.get("display_status", "progress", 0.0) or 0.0
        color = Theme.WARN if state == "paused" else Theme.ACCENT
        ui.big_text(c, "pr/card/pct", 32, 112, "%d%%" % int(progress * 100), 80, color, Theme.SURFACE)
        ui.bar(c, "pr/card/bar", Rect(32, 212, 736, 18), progress, color)
        duration = app.get("print_stats", "print_duration", 0.0) or 0.0
        slicer = self.estimate.get("estimated_time")
        left = duration / progress - duration if progress > 0.02 else (slicer - duration if slicer else None)
        info = app.get("print_stats", "info", {}) or {}
        speed = app.get("gcode_move", "speed_factor", 1.0) or 1.0
        flow = app.get("gcode_move", "extrude_factor", 1.0) or 1.0
        zoff = (app.get("gcode_move", "homing_origin", [0, 0, 0, 0]) or [0, 0, 0])[2]
        stats = [
            ("Remaining", fmt_duration(left)), ("Elapsed", fmt_duration(duration)),
            ("Layer", "%s / %s" % (info.get("current_layer") or "-", info.get("total_layer") or "-")),
            ("Speed", "%d%%" % round(speed * 100)), ("Flow", "%d%%" % round(flow * 100)), ("Z offset", "%+.3f" % zoff),
        ]
        grid = Rect(372, 108, 396, 96)
        for i, (k, v) in enumerate(stats):
            cell = Rect(grid.x + (i % 3) * 132, grid.y + (i // 3) * 48, 128, 46)
            c.op("pr/card/k%d" % i, [text(cell.row(0, 20), k, FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
            c.op("pr/card/v%d" % i, [text(cell.row(20, 24), v, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        row = Rect(32, 300, 736, 80).split_h(4, 14)
        if state == "paused":
            ui.button(c, "pr/pr", row[0], "Resume", lambda: app.gcode("RESUME"), style=ui.ACCENT)
        else:
            ui.button(c, "pr/pr", row[0], "Pause", (lambda: app.gcode("PAUSE")) if state == "printing" else None)
        ui.button(c, "pr/tune", row[1], "Tune", lambda: app.open_modal(Tune(app)))
        light = app.get("output_pin caselight", "value", None)
        ui.button(c, "pr/light", row[2], "Light", (lambda: app.gcode("SET_PIN PIN=caselight VALUE=%d" % (0 if light else 1)))
                  if light is not None else None, sub="on" if light else "off", active=bool(light))
        def cancel():
            confirm(app, "Cancel print", "Stop this print? It cannot be resumed.", "Cancel print",
                    lambda: app.gcode("CANCEL_PRINT"))

        ui.button(c, "pr/cancel", row[3], "Cancel", cancel if app.printing else None, style=ui.DANGER)


class Tune(Modal):
    width, height = 600, 330

    def draw(self, c):
        app, p = self.app, self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 18, 300, 34), "Tune print", FONT_L)
        speed = round((app.get("gcode_move", "speed_factor", 1.0) or 1.0) * 100)
        flow = round((app.get("gcode_move", "extrude_factor", 1.0) or 1.0) * 100)
        zoff = (app.get("gcode_move", "homing_origin", [0, 0, 0]) or [0, 0, 0])[2]
        rows = [
            ("Speed", "%d%%" % speed, [("-10", lambda: app.gcode("M220 S%d" % max(10, speed - 10))),
                                       ("+10", lambda: app.gcode("M220 S%d" % (speed + 10))), ("100", lambda: app.gcode("M220 S100"))]),
            ("Flow", "%d%%" % flow, [("-1", lambda: app.gcode("M221 S%d" % max(50, flow - 1))),
                                     ("+1", lambda: app.gcode("M221 S%d" % (flow + 1))), ("100", lambda: app.gcode("M221 S100"))]),
            ("Z offset", "%+.3f" % zoff, [("-0.01", lambda: app.gcode("SET_GCODE_OFFSET Z_ADJUST=-0.01 MOVE=1")),
                                          ("+0.01", lambda: app.gcode("SET_GCODE_OFFSET Z_ADJUST=0.01 MOVE=1")),
                                          ("-0.05", lambda: app.gcode("SET_GCODE_OFFSET Z_ADJUST=-0.05 MOVE=1"))]),
        ]
        for i, (name, value, buttons) in enumerate(rows):
            y = p.y + 68 + i * 68
            c.op("modal/n%d" % i, [text(Rect(p.x + 24, y, 120, 56), name, FONT_M, Theme.MUTED, Theme.SURFACE, LEFT)])
            c.op("modal/v%d" % i, [text(Rect(p.x + 140, y, 110, 56), value, FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
            for j, ((cap, act), cell) in enumerate(zip(buttons, Rect(p.x + 260, y + 4, p.w - 284, 50).split_h(3, 10))):
                ui.button(c, "modal/b%d%d" % (i, j), cell, cap, act)
        ui.button(c, "modal/close", Rect(p.x + 24, p.y + p.h - 50, p.w - 48, 40), "Done", self.close, style=ui.ACCENT)


# --- Control -------------------------------------------------------------------------

class ControlPage(Page):
    title = "Control"
    nav = "control"
    tabs = ["Move", "Temperature", "Fans & light"]
    steps = [0.1, 1, 10, 50]

    def __init__(self, app, tab: int = 0):
        super().__init__(app)
        self.current = tab
        self.step = 2

    @classmethod
    def tab(cls, app, tab: int) -> "ControlPage":
        return cls(app, tab)

    def _select(self, i: int):
        self.current = i
        self.app.clear_content = True
        self.app.invalidate()

    def draw(self, c):
        ui.segmented(c, "ctl/tabs", Rect(12, 52, 776, 48), self.tabs, self.current, self._select, bg=Theme.BG)
        [self.move, self.temperature, self.fans][self.current](c)

    # Move
    def move(self, c):
        app = self.app
        homed = app.get("toolhead", "homed_axes", "") or ""
        pos = app.get("toolhead", "position", [0, 0, 0, 0]) or [0, 0, 0, 0]
        step = self.steps[self.step]

        def jog(axis, sign):
            if axis.lower() not in homed:
                app.toast("Home %s first" % axis, Theme.WARN)
                return
            feed = 600 if axis == "Z" else 6000
            app.gcode("G91\nG1 %s%s F%d\nG90" % (axis, ("%g" % (sign * step)), feed))

        pad = Rect(12, 112, 300, 288)
        ui.card(c, "ctl/pad", pad)
        cells = [[None, ("Y+", "Y", 1), None], [("X-", "X", -1), ("home", None, 0), ("X+", "X", 1)], [None, ("Y-", "Y", -1), None]]
        for r_i, row in enumerate(cells):
            for c_i, cell in enumerate(row):
                if cell is None:
                    continue
                rr = Rect(pad.x + 14 + c_i * 94, pad.y + 14 + r_i * 88, 84, 80)
                cap, axis, sign = cell
                if axis is None:
                    ui.button(c, "ctl/pad/home", rr, "Home", lambda: app.gcode("G28 X Y"), style=ui.ACCENT, sub="X Y", bg=Theme.SURFACE)
                else:
                    ui.button(c, "ctl/pad/" + cap, rr, cap, (lambda a=axis, s=sign: jog(a, s)), font=FONT_L, bg=Theme.SURFACE)
        zcol = Rect(324, 112, 116, 288)
        ui.card(c, "ctl/z", zcol)
        ui.button(c, "ctl/z/up", Rect(zcol.x + 14, zcol.y + 14, 88, 80), "Z+", lambda: jog("Z", 1), font=FONT_L, sub="bed down")
        ui.button(c, "ctl/z/home", Rect(zcol.x + 14, zcol.y + 102, 88, 80), "Home", lambda: app.gcode("G28 Z"), style=ui.ACCENT, sub="Z")
        ui.button(c, "ctl/z/down", Rect(zcol.x + 14, zcol.y + 190, 88, 80), "Z-", lambda: jog("Z", -1), font=FONT_L, sub="bed up")
        side = Rect(452, 112, 336, 288)
        ui.card(c, "ctl/side", side)
        c.op("ctl/side/stepl", [text(Rect(side.x + 18, side.y + 12, 200, 22), "STEP (mm)", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        ui.segmented(c, "ctl/side/step", Rect(side.x + 14, side.y + 36, side.w - 28, 46), ["%g" % s for s in self.steps],
                     self.step, self._set_step)
        for i, axis in enumerate("XYZ"):
            cell = Rect(side.x + 18 + i * 104, side.y + 96, 96, 60)
            ok = axis.lower() in homed
            c.op("ctl/side/a%s" % axis, [text(cell.row(0, 22), axis + (" homed" if ok else " not homed"), FONT_S,
                                             Theme.OK if ok else Theme.WARN, Theme.SURFACE, LEFT),
                                        text(cell.row(24, 30), "%.1f" % pos["XYZ".index(axis)], FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
        nozzle = app.get("extruder", "temperature", 0) or 0
        can_extrude = nozzle >= 170
        row1 = Rect(side.x + 14, side.y + 168, side.w - 28, 52).split_h(2, 10)
        ui.button(c, "ctl/side/all", row1[0], "Home all", lambda: app.gcode("G28"), style=ui.ACCENT)
        ui.button(c, "ctl/side/off", row1[1], "Motors off", lambda: app.gcode("M84"))
        row2 = Rect(side.x + 14, side.y + 226, side.w - 28, 52).split_h(2, 10)
        ui.button(c, "ctl/side/ext", row2[0], "Extrude", (lambda: app.gcode("M83\nG1 E10 F300")) if can_extrude else None,
                  sub="10 mm" if can_extrude else "heat to 170 C")
        ui.button(c, "ctl/side/ret", row2[1], "Retract", (lambda: app.gcode("M83\nG1 E-10 F1200")) if can_extrude else None,
                  sub="10 mm" if can_extrude else "heat to 170 C")

    def _set_step(self, i):
        self.step = i
        self.app.invalidate()

    # Temperature
    def temperature(self, c):
        app = self.app
        rows = [h for h in HEATERS if app.has(h[0])]
        area = Rect(12, 112, 776, 216)
        for i, ((obj, name, lo, hi, hot), r) in enumerate(zip(rows, area.split_v(3, 10))):
            temp = app.get(obj, "temperature", 0) or 0
            target = app.get(obj, "target", 0) or 0
            key = "ctl/t/%d" % i
            ui.card(c, key, r)
            c.op(key + "/strip", rounded(Rect(r.x, r.y + 10, 6, r.h - 20), heat_color(temp, hot), 3))
            c.op(key + "/n", [text(Rect(r.x + 20, r.y, 120, r.h), name, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
            c.op(key + "/v", [text(Rect(r.x + 130, r.y, 110, r.h), "%d C" % round(temp), FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
            bt = Rect(r.x + 250, r.y + 8, r.w - 258, r.h - 16).split_h(4, 8)
            ui.button(c, key + "/m", bt[0], "-5", lambda o=obj, t=target: app.gcode(heater_gcode(o, max(0, t - 5))))
            ui.button(c, key + "/t", bt[1], ("%d C" % target) if target else "Off",
                      lambda o=obj, n=name, l=lo, h=hi: set_target(app, o, n, l, h), active=target > 0)
            ui.button(c, key + "/p", bt[2], "+5", lambda o=obj, t=target, h=hi: app.gcode(heater_gcode(o, min(h, t + 5))))
            ui.button(c, key + "/o", bt[3], "Off", (lambda o=obj: app.gcode(heater_gcode(o, 0))) if target else None)
        presets = Rect(12, 338, 776, 62).split_h(len(PRESETS) + 1, 10)
        for i, (name, n, b, ch) in enumerate(PRESETS):
            ui.button(c, "ctl/pre/%d" % i, presets[i], name, lambda n=n, b=b, ch=ch: self._preset(n, b, ch),
                      sub="%d / %d" % (n, b), bg=Theme.BG)
        ui.button(c, "ctl/pre/cool", presets[-1], "Cool down", lambda: cool_down(app), style=ui.GHOST, bg=Theme.BG)

    def _preset(self, nozzle, bed, chamber):
        app = self.app
        script = [heater_gcode("extruder", nozzle), heater_gcode("heater_bed", bed)]
        if chamber and app.has("heater_generic chamber"):
            script.append(heater_gcode("heater_generic chamber", chamber))
        app.gcode("\n".join(script))

    # Fans & light
    def fans(self, c):
        app = self.app
        fans = [("fan", "Part cooling", lambda v: "M106 P0 S%d" % round(v * 255))]
        for name, label in (("sidefan", "Side fan"), ("filterfan", "Filter fan")):
            if app.has("fan_generic " + name):
                fans.append(("fan_generic " + name, label, lambda v, n=name: "SET_FAN_SPEED FAN=%s SPEED=%.2f" % (n, v)))
        area = Rect(12, 112, 776, 70 * len(fans) + 10 * (len(fans) - 1))
        for i, ((obj, name, cmd), r) in enumerate(zip(fans, area.split_v(len(fans), 10))):
            speed = app.get(obj, "speed", 0.0) or 0.0
            key = "ctl/f/%d" % i
            ui.card(c, key, r)
            c.op(key + "/n", [text(Rect(r.x + 20, r.y, 150, r.h), name, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
            c.op(key + "/v", [text(Rect(r.x + 170, r.y, 70, r.h), "%d%%" % round(speed * 100), FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
            ui.bar(c, key + "/bar", Rect(r.x + 246, r.y + r.h // 2 - 6, 170, 12), speed, Theme.ACCENT)
            bt = Rect(r.x + 430, r.y + 8, r.w - 438, r.h - 16).split_h(4, 8)
            ui.button(c, key + "/m", bt[0], "-10", lambda s=speed, f=cmd: app.gcode(f(max(0.0, round(s - 0.1, 2)))))
            ui.button(c, key + "/p", bt[1], "+10", lambda s=speed, f=cmd: app.gcode(f(min(1.0, round(s + 0.1, 2)))))
            ui.button(c, key + "/x", bt[2], "Max", lambda f=cmd: app.gcode(f(1.0)))
            ui.button(c, key + "/o", bt[3], "Off", lambda f=cmd: app.gcode(f(0.0)))
        light = app.get("output_pin caselight", "value", None)
        if light is not None:
            r = Rect(12, area.y + area.h + 10, 776, 70)
            ui.card(c, "ctl/light", r)
            c.op("ctl/light/n", [text(Rect(r.x + 20, r.y, 300, r.h), "Case light", FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
            ui.toggle(c, "ctl/light/sw", Rect(r.x + r.w - 100, r.y + 17, 76, 36), light > 0,
                      lambda: app.gcode("SET_PIN PIN=caselight VALUE=%d" % (0 if light > 0 else 1)))


# --- Files ------------------------------------------------------------------------------

class FilesPage(Page):
    title = "Files"
    nav = "files"
    per_page = 5

    def __init__(self, app):
        super().__init__(app)
        self.files: List[dict] = []
        self.offset = 0
        self.loading = True

    def enter(self):
        self.app.spawn(self.load())

    async def load(self):
        self.loading = True
        self.app.invalidate()
        try:
            files = await self.app.call("server.files.list", root="gcodes")
            self.files = sorted(files, key=lambda f: f.get("modified", 0), reverse=True)
        except Exception as e:
            logging.warning("file list failed: %s", e)
            self.app.toast("Could not read the file list", Theme.ERR)
        self.loading = False
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        header = Rect(12, 52, 776, 48)
        count = len(self.files)
        pages = max(1, (count + self.per_page - 1) // self.per_page)
        page = self.offset // self.per_page + 1
        c.op("files/h", [text(Rect(16, 52, 360, 48), ("Loading..." if self.loading else "%d files, newest first" % count),
                              FONT_M, Theme.MUTED, Theme.BG, LEFT)])
        nav = Rect(456, 52, 332, 48).split_h(3, 10)
        ui.button(c, "files/prev", nav[0], "Prev", (lambda: self._page(-1)) if self.offset > 0 else None, bg=Theme.BG)
        c.op("files/pg", [text(nav[1], "%d / %d" % (page, pages), FONT_M, Theme.TEXT, Theme.BG, CENTER)])
        ui.button(c, "files/next", nav[2], "Next", (lambda: self._page(1)) if self.offset + self.per_page < count else None,
                  bg=Theme.BG)
        rows = Rect(12, 108, 776, 292).split_v(self.per_page, 8)
        for i, r in enumerate(rows):
            index = self.offset + i
            key = "files/r%d" % i
            if index >= count:
                c.op(key, [fill(r, Theme.BG)])
                continue
            f = self.files[index]
            pressed = c.pressed == key
            face = Theme.SURFACE2 if pressed else Theme.SURFACE
            ui.card(c, key, r, face, radius=6)
            path = f.get("path", "")
            name = path.rsplit("/", 1)[-1]
            if name.lower().endswith(".gcode"):
                name = name[:-6]
            when = time.strftime("%d %b %H:%M", time.localtime(f.get("modified", 0)))
            size = f.get("size", 0) / 1e6
            c.op(key + "/n", [text(Rect(r.x + 18, r.y, r.w - 220, r.h), name, FONT_M, Theme.TEXT, face, LEFT)])
            c.op(key + "/m", [text(Rect(r.x + r.w - 200, r.y, 186, r.h), "%s  %.1f MB" % (when, size), FONT_S, Theme.MUTED, face, RIGHT)])
            c.hit(key, r, lambda p=path: self.app.open_modal(FileDetails(self.app, p)))

    def _page(self, delta: int):
        self.offset = max(0, self.offset + delta * self.per_page)
        self.app.invalidate()


class FileDetails(Modal):
    width, height = 600, 330

    def __init__(self, app, path: str):
        super().__init__(app)
        self.path = path
        self.meta = {}
        app.spawn(self._load())

    async def _load(self):
        try:
            self.meta = await self.app.call("server.files.metadata", filename=self.path)
        except Exception as e:
            logging.info("no metadata for %s: %s", self.path, e)
        self.app.invalidate()

    def draw(self, c):
        app, p, m = self.app, self.panel, self.meta
        name = self.path.rsplit("/", 1)[-1]
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 18, p.w - 48, 34), name, FONT_L)
        facts = [
            ("Print time", fmt_duration(m.get("estimated_time"))),
            ("Filament", ("%.1f m" % (m["filament_total"] / 1000)) if m.get("filament_total") else "--"),
            ("Layer height", ("%.2f mm" % m["layer_height"]) if m.get("layer_height") else "--"),
            ("Height", ("%.1f mm" % m["object_height"]) if m.get("object_height") else "--"),
            ("Material", m.get("filament_type") or "--"),
            ("Slicer", m.get("slicer") or "--"),
        ]
        for i, (k, v) in enumerate(facts):
            cell = Rect(p.x + 24 + (i % 3) * 186, p.y + 70 + (i // 3) * 64, 180, 56)
            c.op("modal/k%d" % i, [text(cell.row(0, 22), k, FONT_S, Theme.MUTED, Theme.SURFACE, LEFT),
                                   text(cell.row(24, 28), v, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        cancel, go = Rect(p.x + 24, p.y + p.h - 80, p.w - 48, 60).split_h(2, 16)
        ui.button(c, "modal/cancel", cancel, "Back", self.close)
        ui.button(c, "modal/print", go, "Print", self._print if not app.printing else None, style=ui.ACCENT,
                  sub="start now" if not app.printing else "printer busy")

    def _print(self):
        self.close()
        self.app.printer.startPrint(self.path)
        self.app.toast("Starting " + self.path.rsplit("/", 1)[-1])


# --- System -------------------------------------------------------------------------------

class SystemPage(Page):
    title = "System"
    nav = "system"
    allow_offline = True
    brightness = [25, 50, 75, 100]
    sleep = [0, 5, 10, 30]

    def __init__(self, app):
        super().__init__(app)
        self.info = {}
        self.host = ""

    def enter(self):
        self.app.spawn(self._load())

    async def _load(self):
        try:
            self.info = await self.app.call("printer.info")
        except Exception:
            self.info = {}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            self.host = "%s  %s" % (socket.gethostname(), s.getsockname()[0])
            s.close()
        except OSError:
            self.host = socket.gethostname()
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        left = Rect(12, 52, 380, 348)
        ui.card(c, "sys/info", left)
        rows = [
            ("Klipper", "%s  %s" % (app.klippy, (self.info.get("software_version") or "").split("-g")[0])),
            ("Host", self.host or "..."),
            ("Display", "TJC 800x480, canvas mode"),
            ("Box", "Happy Hare, %d gates" % (app.get("mmu", "num_gates", 0) or 0) if app.has("mmu") else "not configured"),
        ]
        for i, (k, v) in enumerate(rows):
            y = left.y + 18 + i * 56
            c.op("sys/info/k%d" % i, [text(Rect(left.x + 20, y, 340, 20), k.upper(), FONT_S, Theme.MUTED, Theme.SURFACE, LEFT),
                                      text(Rect(left.x + 20, y + 20, 340, 28), v, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        screen = Rect(404, 52, 384, 160)
        ui.card(c, "sys/screen", screen)
        c.op("sys/screen/b", [text(Rect(screen.x + 18, screen.y + 10, 200, 22), "BRIGHTNESS", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        b = app.settings["brightness"]
        ui.segmented(c, "sys/screen/bs", Rect(screen.x + 14, screen.y + 34, screen.w - 28, 42), ["%d%%" % v for v in self.brightness],
                     self.brightness.index(b) if b in self.brightness else 3, self._brightness)
        c.op("sys/screen/s", [text(Rect(screen.x + 18, screen.y + 84, 200, 22), "SCREEN OFF AFTER", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        s = app.settings["sleep_minutes"]
        ui.segmented(c, "sys/screen/ss", Rect(screen.x + 14, screen.y + 108, screen.w - 28, 42),
                     ["Never" if v == 0 else "%d min" % v for v in self.sleep], self.sleep.index(s) if s in self.sleep else 2,
                     self._sleep)
        actions = Rect(404, 224, 384, 176)
        grid = [r.split_h(2, 10) for r in actions.split_v(3, 10)]
        ui.button(c, "sys/restart", grid[0][0], "Restart", lambda: app.gcode("RESTART"))
        ui.button(c, "sys/fw", grid[0][1], "FW restart", lambda: app.spawn(app.call("printer.firmware_restart")))
        ui.button(c, "sys/motors", grid[1][0], "Motors off", lambda: app.gcode("M84"))
        ui.button(c, "sys/reboot", grid[1][1], "Reboot", lambda: confirm(
            app, "Reboot printer", "Restarts the printer's computer. Printing is not possible until it is back.",
            "Reboot", lambda: app.spawn(app.call("machine.reboot"))))
        ui.button(c, "sys/estop", grid[2][0], "E-stop", lambda: confirm(
            app, "Emergency stop", "Stops all motors and heaters at once.", "Stop now",
            lambda: app.spawn(app.call("printer.emergency_stop"))), style=ui.DANGER)
        ui.button(c, "sys/screenoff", grid[2][1], "Screen off", self._screen_off, style=ui.GHOST)

    def _brightness(self, i):
        self.app.settings["brightness"] = self.brightness[i]
        self.app.sink("dim=%d" % self.brightness[i])
        self.app.invalidate()

    def _sleep(self, i):
        self.app.settings["sleep_minutes"] = self.sleep[i]
        self.app.invalidate()

    def _screen_off(self):
        self.app.sleeping = True
        self.app.sink("dim=3")


# --- Offline ------------------------------------------------------------------------------

class OfflinePage(Page):
    title = "Printer"

    def draw(self, c):
        app = self.app
        r = Rect(12, 52, 776, 348)
        ui.card(c, "off/card", r)
        starting = app.klippy in ("startup", "connecting")
        headline = "Starting up..." if starting else ("Klipper is not ready" if app.klippy != "disconnected" else "Moonraker is not reachable")
        c.op("off/card/badge", [disc(r.x + 60, r.y + 60, 32, Theme.WARN if starting else Theme.ERR)] +
             [text(Rect(r.x + 28, r.y + 28, 64, 64), "..." if starting else "!", FONT_L, Theme.BG, Theme.WARN if starting else Theme.ERR, CENTER)])
        c.op("off/card/h", [text(Rect(r.x + 112, r.y + 30, 600, 34), headline, FONT_L, Theme.TEXT, Theme.SURFACE, LEFT)])
        c.op("off/card/s", [text(Rect(r.x + 112, r.y + 64, 600, 26), "State: %s" % app.klippy, FONT_M, Theme.MUTED, Theme.SURFACE, LEFT)])
        for i, ln in enumerate(wrap(app.klippy_message or "", 76, 5)):
            c.op("off/card/m%d" % i, [text(Rect(r.x + 28, r.y + 116 + i * 26, 720, 24), ln, FONT_S, Theme.TEXT, Theme.SURFACE, LEFT)],
                 [fill(Rect(r.x + 28, r.y + 116 + i * 26, 720, 24), Theme.SURFACE)])
        row = Rect(r.x + 28, r.y + r.h - 84, r.w - 56, 60).split_h(3, 14)
        ui.button(c, "off/restart", row[0], "Restart", lambda: app.spawn(app.call("printer.restart")), sub="Klipper")
        ui.button(c, "off/fw", row[1], "FW restart", lambda: app.spawn(app.call("printer.firmware_restart")), style=ui.ACCENT,
                  sub="all MCUs")
        ui.button(c, "off/sys", row[2], "System", lambda: app.go_nav("system"), style=ui.GHOST)
