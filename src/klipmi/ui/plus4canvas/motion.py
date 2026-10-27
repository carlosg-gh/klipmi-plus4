# SPDX-License-Identifier: GPL-3.0-or-later
"""Move (jog pad, positions, extruder), Temperature (history chart, heaters, presets) and Fans."""

import logging
import time
from typing import Dict, List

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, Page
from klipmi.canvas.gfx import (CENTER, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, RIGHT, Rect, Theme, fill, icon,
                               line, mix, soft_disc, text)

from .common import (AUTO_FANS, CHART, HEATERS, PRESETS, apply_preset, cool_down, fans, heater_gcode, light_toggle,
                     temps_cmds)
from .home import heater_keypad
from .dialogs import keypad


class MovePage(Page):
    nav = "move"
    STEPS = [0.1, 1, 10, 50, 100]
    LENGTHS = [5, 10, 25, 50]

    def __init__(self, app):
        super().__init__(app)
        self.step = 2
        self.length = 1

    def draw(self, c):
        app = self.app
        homed = app.get("toolhead", "homed_axes", "") or ""
        pos = app.get("toolhead", "position", [0, 0, 0, 0]) or [0, 0, 0, 0]
        step = self.STEPS[self.step]

        def jog(axis, sign):
            if axis.lower() not in homed:
                app.toast("Home %s first" % axis, Theme.WARN)
                return
            app.gcode("G91\nG1 %s%g F%d\nG90" % (axis, sign * step, 600 if axis == "Z" else 6000))

        pad = Rect(CONTENT.x, CONTENT.y, 440, CONTENT.h)
        ui.card(c, "mv/pad", pad)
        x0, y0, s = pad.x + 12, pad.y + 12, 96
        cells = {(1, 0): ("up", "Y+", "Y", 1), (0, 1): ("left", "X-", "X", -1), (2, 1): ("right", "X+", "X", 1),
                 (1, 2): ("down", "Y-", "Y", -1)}
        for (cx, cy), (ic, cap, axis, sign) in cells.items():
            ui.button(c, "mv/pad/%s" % cap, Rect(x0 + cx * (s + 8), y0 + cy * (s + 8), s, s), cap,
                      (lambda a=axis, g=sign: jog(a, g)), icon_name=ic, vertical=True, font=FONT_XS, ink=Theme.MUTED,
                      icon_ink=Theme.TEXT)
        ui.button(c, "mv/pad/xy", Rect(x0 + s + 8, y0 + s + 8, s, s), "XY", lambda: app.gcode("G28 X Y"), style=ui.ACCENT,
                  icon_name="home", vertical=True, font=FONT_XS)
        zx = x0 + 3 * (s + 8) + 8
        for i, (ic, cap, act, style) in enumerate((("up", "Z+", lambda: jog("Z", 1), ui.NORMAL),
                                                   ("home", "Z", lambda: app.gcode("G28 Z"), ui.ACCENT),
                                                   ("down", "Z-", lambda: jog("Z", -1), ui.NORMAL))):
            ui.button(c, "mv/pad/z%d" % i, Rect(zx, y0 + i * (s + 8), s, s), cap, act, style=style, icon_name=ic,
                      vertical=True, font=FONT_XS, ink=Theme.MUTED if style == ui.NORMAL else None,
                      icon_ink=Theme.TEXT if style == ui.NORMAL else None)
        steps = Rect(pad.x + 12, pad.y + pad.h - 76, pad.w - 24, 64).split_h(len(self.STEPS), 8)
        for i, cell in enumerate(steps):
            ui.button(c, "mv/pad/s%d" % i, cell, "%g" % self.STEPS[i], (lambda i=i: self._step(i)), style=ui.OUTLINE,
                      selected=i == self.step)

        side = Rect(CONTENT.x + 448, CONTENT.y, CONTENT.w - 448, CONTENT.h)
        posr = Rect(side.x, side.y, side.w, 136)
        ui.card(c, "mv/pos", posr)
        for i, axis in enumerate("XYZ"):
            row = Rect(posr.x + 16, posr.y + 8 + i * 40, posr.w - 32, 40)
            ok = axis.lower() in homed
            c.op("mv/pos/%s" % axis, [fill(row, Theme.SURFACE), text(Rect(row.x, row.y, 40, row.h), axis, FONT_S, Theme.MUTED,
                                                                       Theme.SURFACE, LEFT),
                                      text(Rect(row.x + 40, row.y, row.w - 40, row.h), ("%.1f" % pos[i]) if ok else "?", FONT_MB,
                                           Theme.TEXT if ok else Theme.BORDER, Theme.SURFACE, RIGHT)])
        ui.button(c, "mv/all", Rect(side.x, side.y + 144, side.w, 60), "Home all", lambda: app.gcode("G28"),
                  style=ui.ACCENT, bg=Theme.BG, icon_name="home")
        row = Rect(side.x, side.y + 212, side.w, 60).split_h(2, 8)
        ui.button(c, "mv/tilt", row[0], "Z tilt", lambda: app.gcode("HOME_IF_NEEDED\nZ_TILT_ADJUST"), bg=Theme.BG,
                  icon_name="level", icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "mv/off", row[1], "Motors", lambda: app.gcode("M84"), bg=Theme.BG, icon_name="power",
                  icon_ink=Theme.MUTED, font=FONT_XSB)
        ext = Rect(side.x, side.y + 280, side.w, side.h - 280)
        ui.card(c, "mv/ext", ext)
        nozzle = app.get("extruder", "temperature", 0) or 0
        ok = nozzle >= 170 and not app.printing
        ui.icon_label(c, "mv/ext/l", Rect(ext.x + 14, ext.y + 10, ext.w - 110, 32), "nozzle", "Extruder")
        ui.value(c, "mv/ext/t", Rect(ext.x + ext.w - 100, ext.y + 10, 86, 32), "%d" % round(nozzle), FONT_XSB,
                 Theme.TEXT if ok else Theme.WARN, align=RIGHT, degree=True)
        length = self.LENGTHS[self.length]
        cells = Rect(ext.x + 12, ext.y + ext.h - 76, ext.w - 24, 64)
        ui.button(c, "mv/ext/r", Rect(cells.x, cells.y, 80, cells.h), "",
                  (lambda: app.gcode("M83\nG1 E-%d F1200" % length)) if ok else None, icon_name="retract")
        ui.button(c, "mv/ext/len", Rect(cells.x + 88, cells.y, cells.w - 176, cells.h), "%d" % length, self._length,
                  style=ui.OUTLINE)
        ui.button(c, "mv/ext/e", Rect(cells.x + cells.w - 80, cells.y, 80, cells.h), "",
                  (lambda: app.gcode("M83\nG1 E%d F300" % length)) if ok else None, icon_name="extrude")

    def _step(self, i):
        self.step = i
        self.app.invalidate()

    def _length(self):
        self.length = (self.length + 1) % len(self.LENGTHS)
        self.app.invalidate()


class TempPage(Page):
    """Heater rows with typed targets, the last ten minutes as a chart, material presets."""

    nav = "temp"
    bar_temps = False
    WINDOW = 600  # seconds shown
    POINTS = 48

    def __init__(self, app):
        super().__init__(app)
        self.history: Dict[str, List[float]] = {}
        self.fetched = 0.0

    async def _fetch(self):
        try:
            store = await self.app.call("server.temperature_store", include_monitors=False)
            self.history = {k: list(v.get("temperatures") or []) for k, v in (store or {}).items()}
        except Exception as e:
            logging.info("temperature store: %s", e)
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        if time.time() - self.fetched > 10:
            self.fetched = time.time()
            app.spawn(self._fetch())
        heaters = [h for h in HEATERS if app.has(h[0])]
        from klipmi.features import mmu
        box = mmu.parse(app.status)
        col = Rect(CONTENT.x, CONTENT.y, CONTENT.w - 248, CONTENT.h)
        rows = len(heaters) + (1 if box is not None and box.temperature is not None else 0)
        chart_h = col.h - rows * 68
        chart = Rect(col.x, col.y, col.w, chart_h)
        ui.card(c, "tp/chart", chart)
        self.chart(c, chart.inset(14, 12), heaters)
        cells = [Rect(col.x, col.y + chart_h + 8 + i * 68, col.w, 60) for i in range(rows)]
        for (obj, name, ic, hi, hot), r in zip(heaters, cells):
            temp = app.get(obj, "temperature", 0) or 0
            target = app.get(obj, "target", 0) or 0
            self.row(c, "tp/h/" + obj, r, CHART.get(obj, Theme.ACCENT), name, temp, target,
                     lambda o=obj: heater_keypad(app, o, nav="temp"),
                     (lambda o=obj: app.gcode(heater_gcode(o, 0))) if target else None)
        if rows > len(heaters):
            from .box import GateSheet, dryer_off
            r = cells[len(heaters)]
            self.row(c, "tp/dryer", r, Theme.OK, "Dryer", box.temperature or 0, box.target or 0,
                     lambda: app.open_modal(GateSheet(app, max(0, box.gate))), (lambda: dryer_off(app)) if box.target else None)
        presets = Rect(CONTENT.x + CONTENT.w - 240, CONTENT.y, 240, CONTENT.h)
        cells = presets.split_v(len(PRESETS) + 1, 8)
        for i, ((name, n, b, ch), cell) in enumerate(zip(PRESETS, cells)):
            key = "tp/pre/%d" % i
            ui.button(c, key, cell, "", lambda n=n, b=b, ch=ch: apply_preset(app, n, b, ch), bg=Theme.BG)
            values = [n, b] + ([ch] if ch and app.has("heater_generic chamber") else [])
            c.op(key + "/t", [text(Rect(cell.x + 16, cell.y + 10, cell.w - 32, 30), name, FONT_SB, Theme.TEXT, Theme.SURFACE2, LEFT)]
                 + temps_cmds(Rect(cell.x + 16, cell.y + 42, cell.w - 32, 26), values, FONT_XS, Theme.MUTED, Theme.SURFACE2))
        ui.button(c, "tp/cool", cells[-1], "Cool down", lambda: cool_down(app), style=ui.OUTLINE, bg=Theme.BG, icon_name="snow")

    def row(self, c, key, r, color, name, temp, target, on_set, on_off):
        ui.card(c, key, r)
        c.op(key + "/n", [fill(Rect(r.x + 12, r.y, 140, r.h), Theme.SURFACE)] + soft_disc(r.x + 20, r.y + r.h // 2, 5, color, Theme.SURFACE)
             + [text(Rect(r.x + 36, r.y, 112, r.h), name, FONT_S, Theme.TEXT, Theme.SURFACE, LEFT)])
        ui.value(c, key + "/v", Rect(r.x + 150, r.y, 92, r.h), "%d" % round(temp), FONT_MB, align=RIGHT, degree=True)
        c.op(key + "/a", [fill(Rect(r.x + 248, r.y, 28, r.h), Theme.SURFACE),
                          icon("arrow", r.x + 250, r.y + (r.h - 24) // 2, 24, Theme.SURFACE, Theme.MUTED)])
        tb = Rect(r.x + 282, r.y + 6, 110, r.h - 12)
        ui.button(c, key + "/t", tb, "", on_set, style=ui.OUTLINE)
        if target:
            c.op(key + "/t/v", ui.value_cmds(tb.inset(4), "%d" % round(target), FONT_SB, Theme.TEXT, Theme.SURFACE, CENTER, True)[1:])
        else:
            c.op(key + "/t/v", [text(tb.inset(4), "Off", FONT_S, Theme.MUTED, Theme.SURFACE, CENTER)])
        if on_off is not None:
            ui.button(c, key + "/off", Rect(r.x + r.w - 54, r.y + 6, r.h - 12, r.h - 12), "", on_off, icon_name="x")
        else:
            c.op(key + "/off", [fill(Rect(r.x + r.w - 54, r.y + 6, r.h - 12, r.h - 12), Theme.SURFACE)])
        c.hit(key, r, on_set)

    def chart(self, c, r: Rect, heaters):
        series = []
        top = 60.0
        for obj, *_ in heaters:
            temps = self.history.get(obj, [])[-self.WINDOW:]
            if temps:
                series.append((obj, temps))
                top = max(top, max(temps), self.app.get(obj, "target", 0) or 0)
        top = 50 * (int(top * 1.08) // 50 + 1)
        cmds = [fill(r, Theme.SURFACE)]
        for k in range(1, 5):
            y = r.y + r.h - int(r.h * k * 50 / top) if k * 50 < top else None
            if y is not None and y > r.y:
                cmds.append(fill(Rect(r.x, y, r.w, 1), Theme.SURFACE2))
        cmds.append(fill(Rect(r.x, r.y + r.h - 1, r.w, 1), Theme.BORDER))

        def ypos(t):
            return r.y + r.h - 2 - int((r.h - 4) * max(0.0, t) / top)

        for obj, temps in series:
            target = self.app.get(obj, "target", 0) or 0
            color = CHART.get(obj, Theme.ACCENT)
            if target:
                cmds.append(fill(Rect(r.x, ypos(target), r.w, 1), mix(color, Theme.SURFACE, 0.55)))
            n = len(temps)
            span = self.WINDOW
            pts = []
            for i in range(self.POINTS + 1):
                age = span - span * i / self.POINTS  # seconds ago
                idx = n - 1 - int(age)
                if idx < 0:
                    continue
                window = temps[max(0, idx - 6):idx + 1]
                pts.append((r.x + int(r.w * i / self.POINTS), ypos(sum(window) / len(window))))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                cmds += [line(x1, y1, x2, y2, color), line(x1, y1 - 1, x2, y2 - 1, color)]
        c.op("tp/chart/l", cmds)


class FansPage(Page):
    nav = "fans"

    def draw(self, c):
        app = self.app
        items = fans(app)
        area = Rect(CONTENT.x, CONTENT.y, CONTENT.w, CONTENT.h - 84)
        for i, ((obj, name, ic, build), r) in enumerate(zip(items, area.split_v(max(3, len(items)), 8))):
            speed = app.get(obj, "speed", 0.0) or 0.0
            key = "fn/%d" % i
            ui.card(c, key, r)
            ui.icon_label(c, key + "/n", Rect(r.x + 16, r.y + 10, 300, 36), ic, name, font=FONT_S, fg=Theme.TEXT)
            if speed > 0:
                ui.label(c, key + "/v", Rect(r.x + r.w - 140, r.y + 8, 124, 40), "%d%%" % round(speed * 100), FONT_MB,
                         Theme.TEXT, Theme.SURFACE, RIGHT)
            else:
                ui.label(c, key + "/v", Rect(r.x + r.w - 140, r.y + 8, 124, 40), "Off", FONT_S, Theme.MUTED, Theme.SURFACE, RIGHT)
            ctl = Rect(r.x + 16, r.y + r.h - 58, r.w - 28, 48)
            ui.slider(c, key + "/s", Rect(ctl.x, ctl.y, ctl.w - 176, ctl.h), speed,
                      lambda f, b=build: app.gcode(b(round(f * 20) / 20.0)))
            ui.button(c, key + "/off", Rect(ctl.x + ctl.w - 164, ctl.y, 76, ctl.h), "Off", lambda b=build: app.gcode(b(0.0)),
                      style=ui.OUTLINE, font=FONT_XSB)
            ui.button(c, key + "/max", Rect(ctl.x + ctl.w - 80, ctl.y, 76, ctl.h), "100", lambda b=build: app.gcode(b(1.0)),
                      style=ui.OUTLINE, font=FONT_XSB)
        foot = Rect(CONTENT.x, CONTENT.y + CONTENT.h - 76, CONTENT.w, 76)
        autos = [(obj, name) for obj, name in AUTO_FANS if app.has(obj)]
        light = app.get("output_pin caselight", "value", None)
        width = foot.w - (184 if light is not None else 0)
        for i, ((obj, name), r) in enumerate(zip(autos, Rect(foot.x, foot.y, width, foot.h).split_h(max(1, len(autos)), 8))):
            speed = app.get(obj, "speed", 0.0) or 0.0
            key = "fn/auto%d" % i
            ui.card(c, key, r, radius=10)
            c.op(key + "/t", soft_disc(r.x + 22, r.y + 24, 5, Theme.OK if speed > 0 else Theme.BORDER, Theme.SURFACE) +
                 [text(Rect(r.x + 36, r.y + 8, r.w - 44, 30), name, FONT_XSB, Theme.TEXT, Theme.SURFACE, LEFT),
                  text(Rect(r.x + 16, r.y + 40, r.w - 24, 28), ("%d%%" % round(speed * 100)) if 0 < speed < 1 else
                       ("on" if speed else "off"), FONT_XS, Theme.MUTED, Theme.SURFACE, LEFT)])
        if light is not None:
            ui.button(c, "fn/light", Rect(foot.x + foot.w - 176, foot.y, 176, foot.h), "Light", light_toggle(app),
                      style=ui.ACCENT if light else ui.NORMAL, bg=Theme.BG, icon_name="light")
