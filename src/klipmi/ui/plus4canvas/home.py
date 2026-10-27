# SPDX-License-Identifier: GPL-3.0-or-later
"""Home (heater tiles, gates, shortcuts), the printing dashboard and its Tune sheet."""

import asyncio
import logging
import os
import urllib.parse
import urllib.request
from typing import List, Optional

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_D48, FONT_D96, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, RIGHT,
                               Rect, Theme, fill, icon, rounded, text, text_width, wrap_px)
from klipmi.canvas.thumb import mosaic
from klipmi.features import mmu

from .common import (HEATERS, MOONRAKER, PRESETS, fans, fmt_duration, gate_color, heat_color, heater_gcode,
                     light_toggle, parts_cmds, strip_gcode)
from .dialogs import choose, confirm, keypad


def heater_keypad(app: App, obj: str, nav: Optional[str] = None):
    name, ic, hi = next(((n, i, h) for o, n, i, h, _ in HEATERS if o == obj), ("Heater", "temp", 300))
    presets = []
    for preset, nozzle, bed, chamber in PRESETS:
        v = {"extruder": nozzle, "heater_bed": bed}.get(obj, chamber)
        if v:
            presets.append((preset, v))
    keypad(app, name, app.get(obj, "target", 0) or 0, 0, hi, lambda v: app.gcode(heater_gcode(obj, v)), unit="C",
           icon_name=ic, current=app.get(obj, "temperature", None), presets=presets, nav=nav)


def thumbnail_png(meta: dict, path: str) -> Optional[bytes]:
    """The largest thumbnail Moonraker knows for a file, or None."""
    thumbs = sorted(meta.get("thumbnails") or [], key=lambda t: t.get("width", 0))
    if not thumbs:
        return None
    rel = thumbs[-1]["relative_path"]
    folder = os.path.dirname(path)
    url = "%s/server/files/gcodes/%s" % (MOONRAKER, urllib.parse.quote((folder + "/" + rel) if folder else rel))
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.read()
    except Exception as e:
        logging.info("thumbnail %s: %s", url, e)
        return None


# --- Home ----------------------------------------------------------------------------

class HomePage(Page):
    nav = "home"
    bar_temps = False

    def draw(self, c):
        app = self.app
        box = mmu.parse(app.status)
        tiles = [("h", obj) for obj, *_ in HEATERS if app.has(obj)]
        if box is not None and box.temperature is not None:
            tiles.append(("dryer", ""))
        top = Rect(CONTENT.x, CONTENT.y, CONTENT.w, 192)
        for (kind, obj), r in zip(tiles, top.split_h(len(tiles), 8)):
            if kind == "h":
                self.heater(c, r, obj)
            else:
                self.dryer(c, r, box)
        low = Rect(CONTENT.x, CONTENT.y + 200, CONTENT.w, CONTENT.h - 200)
        gates = Rect(low.x, low.y, low.w - 272, low.h)
        if box is not None:
            self.gates(c, gates, box)
        else:
            self.no_box(c, gates)
        self.quick(c, Rect(low.x + low.w - 264, low.y, 264, low.h))

    def heater(self, c, r: Rect, obj: str):
        app = self.app
        name, ic, hot = next((n, i, h) for o, n, i, _, h in HEATERS if o == obj)
        temp = app.get(obj, "temperature", 0.0) or 0.0
        target = app.get(obj, "target", 0.0) or 0.0
        key = "home/h/" + obj
        ui.card(c, key, r)
        ui.icon_label(c, key + "/l", Rect(r.x + 16, r.y + 12, r.w - 32, 28), ic, name)
        ui.value(c, key + "/v", Rect(r.x + 16, r.y + 70, r.w - 24, 58), ui.temp_str(temp), FONT_D48, degree=True)
        line = Rect(r.x + 16, r.y + 128, r.w - 24, 30)
        if target > 0:
            ui.value(c, key + "/t", line, "/ %d" % round(target), FONT_S, Theme.MUTED, degree=True)
        else:
            ui.label(c, key + "/t", line, "Off", FONT_S)
        frac = temp / target if target > 0 else 0.0
        ui.bar(c, key + "/b", Rect(r.x + 16, r.y + r.h - 24, r.w - 32, 8), frac, heat_color(temp, hot))
        c.hit(key, r, lambda: _keypad(app, obj))

    def dryer(self, c, r: Rect, box: mmu.Box):
        key = "home/dryer"
        ui.card(c, key, r)
        ui.icon_label(c, key + "/l", Rect(r.x + 16, r.y + 12, r.w - 80, 28), "drop", "Dryer")
        humid = "%d%%" % round(box.humidity) if box.humidity is not None else ""
        ui.label(c, key + "/rh", Rect(r.x + r.w - 76, r.y + 12, 60, 28), humid, FONT_XS, Theme.MUTED, Theme.SURFACE, RIGHT)
        ui.value(c, key + "/v", Rect(r.x + 16, r.y + 70, r.w - 24, 58), ui.temp_str(box.temperature), FONT_D48, degree=True)
        line = Rect(r.x + 16, r.y + 128, r.w - 24, 30)
        if box.target:
            ui.value(c, key + "/t", line, "/ %d" % round(box.target), FONT_S, Theme.MUTED, degree=True)
        else:
            ui.label(c, key + "/t", line, "Off", FONT_S)
        frac = (box.temperature or 0) / box.target if box.target else 0.0
        ui.bar(c, key + "/b", Rect(r.x + 16, r.y + r.h - 24, r.w - 32, 8), frac, Theme.OK)
        from .box import GateSheet
        c.hit(key, r, lambda: self.app.open_modal(GateSheet(self.app, box.gate if box.gate >= 0 else 0)))

    def gates(self, c, r: Rect, box: mmu.Box):
        from .box import GateSheet
        ui.card(c, "home/gates", r)
        n = max(1, len(box.slots))
        cols = r.inset(10).split_h(n, 8)
        loaded = box.gate if box.filament != "Unloaded" else -1
        for slot, col in zip(box.slots, cols):
            key = "home/gates/%d" % slot.index
            active = slot.index == loaded
            face = Theme.SURFACE2 if active else Theme.SURFACE
            if active:
                c.op(key, rounded(col, Theme.ACCENT, 10, Theme.SURFACE) + rounded(col.inset(2), face, 8, Theme.ACCENT))
            else:
                c.op(key, [fill(col, Theme.SURFACE)])
            cx, cy = col.x + col.w // 2, col.y + 14 + 42
            ui.spool(c, key + "/s", cx, cy, 42, gate_color(slot), face, face, erase_r=46)
            c.op(key + "/n", [text(Rect(col.x + 4, cy + 52, col.w - 8, 30), str(slot.index + 1), FONT_SB,
                                   Theme.ACCENT if active else (Theme.TEXT if slot.available else Theme.MUTED), face, CENTER)])
            mat = slot.material or ("Empty" if slot.status == mmu.GATE_EMPTY else "?")
            c.op(key + "/m", [text(Rect(col.x + 4, cy + 82, col.w - 8, 26), mat, FONT_XS, Theme.MUTED, face, CENTER)])
            c.hit(key, col, lambda g=slot.index: self.app.open_modal(GateSheet(self.app, g)))

    def no_box(self, c, r: Rect):
        app = self.app
        ui.card(c, "home/fil", r)
        ui.icon_label(c, "home/fil/l", Rect(r.x + 16, r.y + 12, r.w - 32, 28), "spool", "Filament")
        row = Rect(r.x + 12, r.y + r.h - 84, r.w - 24, 72).split_h(2, 8)
        ui.button(c, "home/fil/load", row[0], "Load", lambda: app.gcode("LOAD_FILAMENT"), icon_name="extrude")
        ui.button(c, "home/fil/unload", row[1], "Unload", lambda: app.gcode("UNLOAD_FILAMENT"), icon_name="retract")

    def quick(self, c, r: Rect):
        app = self.app
        cells = [cell for row in r.split_v(2, 8) for cell in row.split_h(2, 8)]
        light = app.get("output_pin caselight", "value", None)
        ui.button(c, "home/q/light", cells[0], "Light", light_toggle(app), style=ui.ACCENT if light else ui.NORMAL,
                  bg=Theme.BG, icon_name="light", vertical=True, font=FONT_XSB)
        fan = app.get("fan", "speed", 0.0) or 0.0
        ui.button(c, "home/q/fan", cells[1], "%d%%" % round(fan * 100), lambda: app.go_nav("fans"), bg=Theme.BG,
                  icon_name="fan", vertical=True, font=FONT_XSB)
        ui.button(c, "home/q/home", cells[2], "Home", lambda: app.gcode("G28"), bg=Theme.BG, icon_name="home",
                  vertical=True, font=FONT_XSB)
        ui.button(c, "home/q/print", cells[3], "Print", lambda: app.go_nav("files"), style=ui.ACCENT, bg=Theme.BG,
                  icon_name="play", vertical=True, font=FONT_XSB)


def _keypad(app: App, obj: str):
    heater_keypad(app, obj)


# --- Printing ---------------------------------------------------------------------------

class PrintingPage(Page):
    nav = "home"
    THUMB = 248

    def __init__(self, app):
        super().__init__(app)
        self.meta: dict = {}
        self.file = ""
        self.thumb: Optional[List[str]] = None

    def enter(self):
        self.file = ""

    async def _load(self, name: str):
        try:
            self.meta = await self.app.call("server.files.metadata", filename=name)
        except Exception as e:
            logging.info("no metadata for %s: %s", name, e)
            self.meta = {}
        png = await asyncio.get_running_loop().run_in_executor(None, thumbnail_png, self.meta, name)
        cells = 62
        self.thumb = mosaic(png, CONTENT.x + 12 + (self.THUMB - cells * 4) // 2, CONTENT.y + 12 + (self.THUMB - cells * 4) // 2,
                            cells, 4, Theme.SURFACE2) if png else []
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        name = app.get("print_stats", "filename", "") or ""
        if name != self.file:
            self.file, self.thumb, self.meta = name, None, {}
            if name:
                app.spawn(self._load(name))
        state = app.print_state
        left = Rect(CONTENT.x, CONTENT.y, 272, CONTENT.h)
        ui.card(c, "pr/l", left)
        frame = Rect(left.x + 12, left.y + 12, self.THUMB, self.THUMB)
        ui.card(c, "pr/l/frame", frame, Theme.SURFACE2, Theme.SURFACE, 10)
        if self.thumb:
            c.op("pr/l/frame/img", self.thumb)
        else:
            c.op("pr/l/frame/img", [icon("cube", frame.x + (frame.w - 32) // 2, frame.y + (frame.h - 32) // 2, 32,
                                         Theme.SURFACE2, Theme.MUTED)])
        lines = wrap_px(strip_gcode(name) or "--", left.w - 32, FONT_S, 2)
        for i in range(2):
            ui.label(c, "pr/l/n%d" % i, Rect(left.x + 16, frame.y + frame.h + 10 + i * 30, left.w - 32, 30),
                     lines[i] if i < len(lines) else "", FONT_S, Theme.TEXT)
        box = mmu.parse(app.status)
        foot = Rect(left.x + 16, left.y + left.h - 40, left.w - 32, 28)
        grams = self.meta.get("filament_weight_total")
        parts = []
        cmds = [fill(foot, Theme.SURFACE)]
        x = foot.x
        if box is not None and 0 <= box.gate < len(box.slots):
            slot = box.slots[box.gate]
            color = gate_color(slot)
            if color is not None:
                ui.swatch(cmds, foot.x + 8, foot.y + 14, 8, color, Theme.SURFACE)
                x += 24
            parts += ["Gate %d" % (box.gate + 1), slot.material]
        if grams:
            parts.append("%.1f g" % grams)
        c.op("pr/l/foot", cmds + parts_cmds(Rect(x, foot.y, foot.x + foot.w - x, foot.h), parts)[1:])

        right = Rect(CONTENT.x + 280, CONTENT.y, CONTENT.w - 280, CONTENT.h)
        prog = Rect(right.x, right.y, right.w, right.h - 160)
        ui.card(c, "pr/p", prog)
        progress = app.get("display_status", "progress", 0.0) or 0.0
        color = Theme.WARN if state == "paused" else Theme.ACCENT
        ui.value(c, "pr/p/pct", Rect(prog.x + 20, prog.y + 14, 250, 104), "%d" % int(progress * 100), FONT_D96,
                 suffix="%", suffix_font=FONT_D48, suffix_fg=Theme.MUTED, suffix_gap=2)
        info = app.get("print_stats", "info", {}) or {}
        layer, total = info.get("current_layer"), info.get("total_layer")
        lay = Rect(prog.x + prog.w - 170, prog.y + 72, 154, 36)
        cmds = [fill(lay, Theme.SURFACE)]
        s_cur, s_tot = "%s" % (layer if layer is not None else "-"), "/ %s" % (total if total is not None else "-")
        w_tot = text_width(s_tot, FONT_S) + 2
        w_cur = text_width(s_cur, FONT_SB) + 2
        x = lay.x + lay.w - w_tot
        cmds += [text(Rect(x, lay.y, w_tot, lay.h), s_tot, FONT_S, Theme.MUTED, Theme.SURFACE, LEFT),
                 text(Rect(x - 6 - w_cur, lay.y, w_cur, lay.h), s_cur, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT),
                 icon("layers", x - 6 - w_cur - 34, lay.y + 6, 24, Theme.SURFACE, Theme.MUTED)]
        c.op("pr/p/layer", cmds)
        ui.bar(c, "pr/p/bar", Rect(prog.x + 20, prog.y + 136, prog.w - 40, 12), progress, color)
        duration = app.get("print_stats", "print_duration", 0.0) or 0.0
        slicer = self.meta.get("estimated_time")
        left_s = duration / progress - duration if progress > 0.02 else (slicer - duration if slicer else None)
        import time as _t
        eta = _t.strftime("%H:%M", _t.localtime(_t.time() + left_s)) if left_s is not None else "--"
        for i, (ic, v) in enumerate((("clock", fmt_duration(duration, True)), ("hour", fmt_duration(left_s, True)),
                                     ("flag", eta))):
            cell = Rect(prog.x + 20 + i * ((prog.w - 40) // 3), prog.y + prog.h - 56, (prog.w - 40) // 3, 40)
            c.op("pr/p/t%d" % i, [fill(cell, Theme.SURFACE), icon(ic, cell.x, cell.y + 8, 24, Theme.SURFACE, Theme.MUTED),
                                   text(Rect(cell.x + 34, cell.y, cell.w - 34, cell.h), v, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT)])

        speed = round((app.get("gcode_move", "speed_factor", 1.0) or 1.0) * 100)
        flow = round((app.get("gcode_move", "extrude_factor", 1.0) or 1.0) * 100)
        zoff = (app.get("gcode_move", "homing_origin", [0, 0, 0]) or [0, 0, 0])[2]
        fan = round((app.get("fan", "speed", 0.0) or 0.0) * 100)
        chips = Rect(right.x, right.y + right.h - 152, right.w, 72).split_h(4, 8)
        for i, (ic, v) in enumerate((("gauge", "%d%%" % speed), ("flow", "%d%%" % flow),
                                     ("z", ("%+.2f" % zoff).replace("0.", ".")), ("fan", "%d%%" % fan))):
            ui.button(c, "pr/c%d" % i, chips[i], v, lambda: app.open_modal(Tune(app)), bg=Theme.BG, icon_name=ic,
                      icon_ink=Theme.MUTED, font=FONT_XSB)
        row = Rect(right.x, right.y + right.h - 72, right.w, 72)
        half = (row.w - 72 - 16) // 2
        if state == "paused":
            ui.button(c, "pr/pause", Rect(row.x, row.y, half, row.h), "Resume", lambda: app.gcode("RESUME"),
                      style=ui.ACCENT, bg=Theme.BG, icon_name="play")
        else:
            ui.button(c, "pr/pause", Rect(row.x, row.y, half, row.h), "Pause",
                      (lambda: app.gcode("PAUSE")) if state == "printing" else None, bg=Theme.BG, icon_name="pause")
        ui.button(c, "pr/cancel", Rect(row.x + half + 8, row.y, half, row.h), "Cancel", (lambda: confirm(
            app, "Cancel print", "Stop this print? It cannot be resumed.", "Cancel print",
            lambda: app.gcode("CANCEL_PRINT"))) if app.printing else None, style=ui.DANGER, bg=Theme.BG, icon_name="x")
        light = app.get("output_pin caselight", "value", None)
        ui.button(c, "pr/light", Rect(row.x + row.w - 72, row.y, 72, row.h), "", light_toggle(app),
                  style=ui.ACCENT if light else ui.NORMAL, bg=Theme.BG, icon_name="light")


class Tune(Modal):
    """Speed, flow, Z offset and part fan while printing: -/+ by a step you pick, reset, skip an object."""

    sheet = True
    nav = "home"
    ROWS = [
        ("gauge", "Speed", [1, 5, 10, 25], 1),
        ("flow", "Flow", [1, 2, 5], 0),
        ("z", "Z offset", [0.005, 0.01, 0.025, 0.05], 1),
        ("fan", "Part fan", [5, 10, 25], 1),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.steps = [r[3] for r in self.ROWS]

    def draw(self, c):
        app = self.app
        r = CONTENT
        ui.card(c, "modal/card", r)
        speed = round((app.get("gcode_move", "speed_factor", 1.0) or 1.0) * 100)
        flow = round((app.get("gcode_move", "extrude_factor", 1.0) or 1.0) * 100)
        zoff = (app.get("gcode_move", "homing_origin", [0, 0, 0]) or [0, 0, 0])[2]
        fan = round((app.get("fan", "speed", 0.0) or 0.0) * 100)
        values = ["%d%%" % speed, "%d%%" % flow, "%+.3f" % zoff, "%d%%" % fan]
        for i, (ic, name, steps, _) in enumerate(self.ROWS):
            step = steps[self.steps[i]]
            row = Rect(r.x + 16, r.y + 12 + i * 80, r.w - 28, 72)
            ui.icon_label(c, "modal/card/n%d" % i, Rect(row.x, row.y + 20, 176, 32), ic, name, font=FONT_S, fg=Theme.TEXT, size=24)
            x = row.x + 184
            ui.button(c, "modal/m%d" % i, Rect(x, row.y + 4, 72, 64), "", (lambda i=i, s=step: self._adjust(i, -s)),
                      icon_name="minus")
            ui.label(c, "modal/card/v%d" % i, Rect(x + 80, row.y + 4, 176, 64), values[i], FONT_MB, Theme.TEXT, Theme.SURFACE, CENTER)
            ui.button(c, "modal/p%d" % i, Rect(x + 264, row.y + 4, 72, 64), "", (lambda i=i, s=step: self._adjust(i, s)),
                      icon_name="plus")
            ui.button(c, "modal/s%d" % i, Rect(x + 344, row.y + 4, 88, 64), "%g" % step, (lambda i=i: self._step(i)),
                      style=ui.OUTLINE, font=FONT_XSB)
            ui.button(c, "modal/r%d" % i, Rect(row.x + row.w - 64, row.y + 4, 64, 64), "", (lambda i=i: self._reset(i)),
                      style=ui.OUTLINE, icon_name="reset", icon_ink=Theme.MUTED)
        foot = Rect(r.x + 16, r.y + r.h - 76, r.w - 32, 60)
        objects = [o.get("name") for o in (app.get("exclude_object", "objects", []) or []) if o.get("name")]
        excluded = set(app.get("exclude_object", "excluded_objects", []) or [])
        open_ = [o for o in objects if o not in excluded]
        ui.button(c, "modal/skip", Rect(foot.x, foot.y, 250, foot.h), "Skip object",
                  (lambda: self._skip(open_)) if len(open_) > 1 else None, icon_name="cube", icon_ink=Theme.MUTED)
        ui.button(c, "modal/done", Rect(foot.x + foot.w - 180, foot.y, 180, foot.h), "Done", self.close, style=ui.ACCENT,
                  icon_name="check")

    def _step(self, i):
        self.steps[i] = (self.steps[i] + 1) % len(self.ROWS[i][2])
        self.app.invalidate()

    def _adjust(self, i: int, delta: float):
        app = self.app
        if i == 0:
            v = round((app.get("gcode_move", "speed_factor", 1.0) or 1.0) * 100)
            app.gcode("M220 S%d" % max(10, v + delta))
        elif i == 1:
            v = round((app.get("gcode_move", "extrude_factor", 1.0) or 1.0) * 100)
            app.gcode("M221 S%d" % max(50, v + delta))
        elif i == 2:
            app.gcode("SET_GCODE_OFFSET Z_ADJUST=%+.3f MOVE=1" % delta)
        else:
            v = round((app.get("fan", "speed", 0.0) or 0.0) * 100)
            app.gcode("M106 S%d" % round(max(0, min(100, v + delta)) * 2.55))

    def _reset(self, i: int):
        app = self.app
        if i == 0:
            app.gcode("M220 S100")
        elif i == 1:
            app.gcode("M221 S100")
        elif i == 2:
            confirm(app, "Reset Z offset", "Sets the Z offset back to 0 while printing.", "Reset",
                    lambda: app.gcode("SET_GCODE_OFFSET Z=0 MOVE=1"), danger=False)
        else:
            app.gcode("M106 S0")

    def _skip(self, names: List[str]):
        app = self.app

        def go(n):
            confirm(app, "Skip object", "Stop printing %s for the rest of this print?" % n, "Skip",
                    lambda: app.gcode("EXCLUDE_OBJECT NAME=%s" % n))

        choose(app, "Skip object", [(n[:18], "", (lambda n=n: go(n))) for n in names[:8]])
