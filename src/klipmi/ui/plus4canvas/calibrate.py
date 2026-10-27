# SPDX-License-Identifier: GPL-3.0-or-later
"""Calibrate: the bed mesh as a height map, the printer's calibration macros, saving the config."""

import logging
from typing import List, Optional

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, Page
from klipmi.canvas.gfx import CENTER, FONT_XS, FONT_XSB, LEFT, Rect, Theme, fill, icon, mix, rgb, text, text_width

from .dialogs import confirm

LOW, MID, HIGH = rgb(58, 123, 255), rgb(107, 113, 124), rgb(255, 128, 48)
MAX_CELLS = 26


def mesh_points(app) -> Optional[List[List[float]]]:
    """The mesh in use, else the saved `default` profile (rows front to back)."""
    bm = app.status.get("bed_mesh", {}) or {}
    pts = bm.get("probed_matrix") or []
    if not pts or not pts[0]:
        prof = (bm.get("profiles") or {}).get(bm.get("profile_name") or "default") or (bm.get("profiles") or {}).get("default")
        pts = (prof or {}).get("points") or []
    return pts if pts and pts[0] else None


def downsample(pts: List[List[float]], limit: int = MAX_CELLS) -> List[List[float]]:
    rows, cols = len(pts), len(pts[0])
    if rows <= limit and cols <= limit:
        return pts
    ry, rx = max(1, -(-rows // limit)), max(1, -(-cols // limit))
    out = []
    for y in range(0, rows, ry):
        line = []
        for x in range(0, cols, rx):
            block = [pts[j][i] for j in range(y, min(rows, y + ry)) for i in range(x, min(cols, x + rx))]
            line.append(sum(block) / len(block))
        out.append(line)
    return out


def height_color(v: float, span: float) -> int:
    t = max(-1.0, min(1.0, v / span)) if span > 0 else 0.0
    return mix(MID, HIGH, t) if t >= 0 else mix(MID, LOW, -t)


class CalibratePage(Page):
    nav = "calibrate"

    def __init__(self, app):
        super().__init__(app)
        self.config: dict = {}

    def enter(self):
        self.app.spawn(self._load())

    async def _load(self):
        try:
            res = await self.app.call("printer.objects.query", objects={"configfile": ["settings"]})
            self.config = res.get("status", {}).get("configfile", {}).get("settings", {}) or {}
        except Exception as e:
            logging.info("configfile: %s", e)
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        left =Rect(CONTENT.x, CONTENT.y, 298, CONTENT.h)
        ui.card(c, "cb/m", left)
        area = Rect(left.x + 16, left.y + 16, 266, 266)
        pts = mesh_points(app)
        if pts is None:
            c.op("cb/m/map", [fill(area, Theme.SURFACE2), text(area, "No mesh yet", FONT_XS, Theme.MUTED, Theme.SURFACE2, CENTER)])
            lo = hi = None
        else:
            grid = downsample(pts)
            rows, cols = len(grid), len(grid[0])
            flat = [v for row in grid for v in row]
            lo, hi = min(flat), max(flat)
            span = max(abs(lo), abs(hi), 0.02)
            cell = min(area.w // cols, area.h // rows)
            gap = 1 if cell >= 8 else 0
            ox = area.x + (area.w - cell * cols) // 2
            oy = area.y + (area.h - cell * rows) // 2
            cmds = [fill(area, Theme.SURFACE)]
            for j, row in enumerate(grid):  # row 0 is the front: draw it at the bottom
                y = oy + (rows - 1 - j) * cell
                for i, v in enumerate(row):
                    cmds.append(fill(Rect(ox + i * cell, y, cell - gap, cell - gap), height_color(v, span)))
            c.op("cb/m/map", cmds)
        legend = Rect(area.x, area.y + area.h + 10, area.w, 30)
        if lo is None:
            c.op("cb/m/leg", [fill(legend, Theme.SURFACE)])
        else:
            s_lo, s_hi = "%+.3f" % lo, "%+.3f" % hi
            w_hi = text_width(s_hi, FONT_XSB) + 2
            c.op("cb/m/leg", [fill(legend, Theme.SURFACE), fill(Rect(legend.x, legend.y + 8, 14, 14), LOW),
                              text(Rect(legend.x + 22, legend.y, 100, legend.h), s_lo, FONT_XSB, Theme.TEXT, Theme.SURFACE, LEFT),
                              text(Rect(legend.x + legend.w - 22 - w_hi, legend.y, w_hi, legend.h), s_hi, FONT_XSB, Theme.TEXT,
                                   Theme.SURFACE, LEFT),
                              fill(Rect(legend.x + legend.w - 14, legend.y + 8, 14, 14), HIGH)])
        busy = app.printing
        ui.button(c, "cb/m/run", Rect(area.x, left.y + left.h - 72, area.w, 56), "Mesh", (lambda: confirm(
            app, "Bed mesh", "Homes if needed and probes the whole bed. Save config afterwards to keep it.", "Start",
            lambda: app.gcode("HOME_IF_NEEDED\nBED_MESH_CLEAR\nBED_MESH_CALIBRATE"), danger=False)) if not busy else None,
            style=ui.ACCENT, icon_name="refresh")

        right = Rect(CONTENT.x + 306, CONTENT.y, CONTENT.w - 306, CONTENT.h)
        cfg = self.config
        shaper = cfg.get("input_shaper", {})
        sh = ""
        if shaper.get("shaper_type_x"):
            sh = "%s %d / %d Hz" % (str(shaper.get("shaper_type_x")).upper(), round(shaper.get("shaper_freq_x", 0)),
                                    round(shaper.get("shaper_freq_y", 0)))
        probe = cfg.get("cartographer", cfg.get("probe", {})) or {}
        zoff = probe.get("z_offset")
        tiles = [
            ("z", "Z offset", ("%+.3f mm" % zoff) if zoff is not None else "paper test", "CALIBRATE_Z_OFFSET",
             "Homes, moves to the bed centre and starts a paper test. Raise or lower until the paper drags, then Accept."),
            ("wave", "Input shaper", sh or "not tuned", "INPUT_SHAPING_CALIBRATE",
             "Shakes the toolhead to measure resonances, then saves the config and restarts Klipper."),
            ("pid", "PID nozzle", "at 220", "NOZZLE_PID_TUNE", "Heats the nozzle to 220 and tunes its heater. Save config afterwards."),
            ("pid", "PID bed", "at 80", "BED_PID_TUNE", "Heats the bed to 80 and tunes its heater. Save config afterwards."),
            ("screw", "Bed screws", "", "LEVEL_BED", "Homes and measures the bed; the screw turns appear in the console."),
            ("level", "Z tilt", "", "HOME_IF_NEEDED\nZ_TILT_ADJUST", "Levels the gantry with both Z motors."),
        ]
        grid = Rect(right.x, right.y, right.w, right.h - 64)
        cells = [cell for row in grid.split_v(3, 8) for cell in row.split_h(2, 8)]
        for i, ((ic, name, sub, gcode, body), cell) in enumerate(zip(tiles, cells)):
            key = "cb/t%d" % i
            ui.button(c, key, cell, "", (lambda n=name, g=gcode, b=body: confirm(app, n, b, "Start", lambda: app.gcode(g),
                                                                               danger=False)) if not busy else None,
                      bg=Theme.BG)
            c.op(key + "/c", [icon(ic, cell.x + 16, cell.y + 14, 32, Theme.SURFACE2, Theme.MUTED),
                              text(Rect(cell.x + 16, cell.y + 52, cell.w - 24, 30), name, FONT_XSB, Theme.TEXT, Theme.SURFACE2, LEFT),
                              text(Rect(cell.x + 16, cell.y + 80, cell.w - 24, 26), sub, FONT_XS, Theme.MUTED, Theme.SURFACE2, LEFT)])
        foot = Rect(right.x, right.y + right.h - 56, right.w, 56).split_h(2, 8)
        ui.button(c, "cb/save", foot[0], "Save config", (lambda: confirm(
            app, "Save config", "Writes calibration results to printer.cfg and restarts Klipper.", "Save",
            lambda: app.gcode("SAVE_CONFIG"), danger=False)) if not busy else None, bg=Theme.BG, icon_name="check",
            icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "cb/clear", foot[1], "Clear mesh", lambda: app.gcode("BED_MESH_CLEAR"), bg=Theme.BG, icon_name="x",
                  icon_ink=Theme.MUTED, font=FONT_XSB)
