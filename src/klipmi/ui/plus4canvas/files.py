# SPDX-License-Identifier: GPL-3.0-or-later
"""Files: folders and G-code files with thumbnails, a page per screenful; the file page with Print and Delete."""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Page
from klipmi.canvas.gfx import (CENTER, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, Rect, Theme, fill, icon, text,
                               wrap_px)
from klipmi.canvas.thumb import mosaic
from klipmi.features import mmu

from .common import fmt_duration, gate_color, parts_cmds, strip_gcode
from .dialogs import confirm
from .home import thumbnail_png

_PNG: Dict[str, Optional[bytes]] = {}  # path -> thumbnail png (None: has none)


def _unique(value) -> List[str]:
    """Slicer metadata keeps per-extruder lists as JSON text; each value once."""
    if isinstance(value, str) and value.startswith("["):
        try:
            value = json.loads(value)
        except ValueError:
            return [value]
    if isinstance(value, list):
        out = []
        for v in value:
            if v and v not in out:
                out.append(str(v))
        return out
    return [str(value)] if value else []


class FilesPage(Page):
    nav = "files"
    per_page = 5

    def __init__(self, app):
        super().__init__(app)
        self.folder = ""
        self.entries: List[dict] = []  # {"dir": bool, "path", "name", "modified", "size", "meta"}
        self.offset = 0
        self.loading = True
        self.by_name = False
        self.thumbs: Dict[Tuple[str, int], List[str]] = {}

    def enter(self):
        self.app.spawn(self.load())

    async def load(self):
        self.loading = True
        self.app.invalidate()
        try:
            listing = await self.app.call("server.files.get_directory", path="gcodes/" + self.folder if self.folder else "gcodes",
                                          extended=True)
        except Exception as e:
            logging.warning("file list failed: %s", e)
            self.app.toast("Could not read the file list", Theme.ERR)
            listing = {}
        entries = []
        for d in listing.get("dirs", []):
            if not d.get("dirname", "").startswith("."):
                entries.append({"dir": True, "name": d["dirname"], "path": self._join(d["dirname"]),
                                "modified": d.get("modified", 0), "size": d.get("size", 0)})
        for f in listing.get("files", []):
            name = f.get("filename", "")
            if name.lower().endswith((".gcode", ".g", ".gco")):
                entries.append({"dir": False, "name": name, "path": self._join(name), "modified": f.get("modified", 0),
                                "size": f.get("size", 0), "meta": f})
        self.entries = entries
        self._sort()
        self.loading = False
        self.thumbs = {}
        self.app.invalidate()

    def _join(self, name: str) -> str:
        return (self.folder + "/" + name) if self.folder else name

    def _sort(self):
        key = (lambda e: (not e["dir"], e["name"].lower())) if self.by_name else (lambda e: (not e["dir"], -e["modified"]))
        self.entries.sort(key=key)

    def draw(self, c):
        app = self.app
        head = Rect(CONTENT.x, CONTENT.y, CONTENT.w - 72, 52)
        ui.button(c, "fs/up", Rect(head.x, head.y, 56, 52), "", self._up if self.folder else None, bg=Theme.BG, icon_name="back")
        ui.label(c, "fs/path", Rect(head.x + 70, head.y, head.w - 260, 52),
                 "Loading..." if self.loading else ("gcodes" + ("/" + self.folder if self.folder else "")), FONT_S,
                 Theme.TEXT, Theme.BG)
        ui.button(c, "fs/sort", Rect(head.x + head.w - 168, head.y, 168, 52), "Name" if self.by_name else "Newest",
                  self._toggle_sort, bg=Theme.BG, icon_name="sort", icon_ink=Theme.MUTED, font=FONT_XSB)
        count = len(self.entries)
        rows = Rect(CONTENT.x, CONTENT.y + 58, CONTENT.w - 72, CONTENT.h - 58).split_v(self.per_page, 6)
        for i, r in enumerate(rows):
            index = self.offset + i
            key = "fs/r%d" % i
            if index >= count:
                c.op(key, [fill(r, Theme.BG)])
                continue
            e = self.entries[index]
            ui.card(c, key, r)
            frame = Rect(r.x + 7, r.y + 7, r.h - 14, r.h - 14)
            ui.card(c, key + "/f", frame, Theme.SURFACE2, Theme.SURFACE, 8)
            if e["dir"]:
                c.op(key + "/f/i", [icon("folder", frame.x + (frame.w - 32) // 2, frame.y + (frame.h - 32) // 2, 32,
                                         Theme.SURFACE2, Theme.MUTED)])
            else:
                c.op(key + "/f/i", self._thumb(e["path"], e.get("meta") or {}, i, frame))
            tx = frame.x + frame.w + 14
            c.op(key + "/n", [text(Rect(tx, r.y + 6, r.x + r.w - tx - 44, 30), strip_gcode(e["name"]), FONT_S, Theme.TEXT,
                                   Theme.SURFACE, LEFT)])
            when = time.strftime("%d %b", time.localtime(e["modified"])) if e["modified"] else ""
            if e["dir"]:
                parts = [when]
            else:
                m = e.get("meta") or {}
                grams = m.get("filament_weight_total")
                parts = [fmt_duration(m.get("estimated_time")) if m.get("estimated_time") else "",
                         ("%.1f g" % grams) if grams else "", when]
            c.op(key + "/m", parts_cmds(Rect(tx, r.y + 36, r.x + r.w - tx - 44, 24), parts))
            c.op(key + "/go", [icon("right", r.x + r.w - 36, r.y + (r.h - 24) // 2, 24, Theme.SURFACE, Theme.MUTED)])
            c.hit(key, r, lambda e=e: self._open(e))
        side = Rect(CONTENT.x + CONTENT.w - 64, CONTENT.y, 64, CONTENT.h)
        pages = max(1, (count + self.per_page - 1) // self.per_page)
        page = self.offset // self.per_page + 1
        ui.button(c, "fs/prev", Rect(side.x, side.y, side.w, (side.h - 64) // 2), "", self._prev if self.offset else None,
                  bg=Theme.BG, icon_name="up", icon_size=32)
        mid = Rect(side.x, side.y + (side.h - 64) // 2 + 4, side.w, 56)
        c.op("fs/pg", [fill(mid, Theme.BG), text(Rect(mid.x, mid.y, mid.w, 28), str(page), FONT_XSB, Theme.TEXT, Theme.BG, CENTER),
                       text(Rect(mid.x, mid.y + 26, mid.w, 28), "/ %d" % pages, FONT_XS, Theme.MUTED, Theme.BG, CENTER)])
        ui.button(c, "fs/next", Rect(side.x, side.y + side.h - (side.h - 64) // 2, side.w, (side.h - 64) // 2), "",
                  self._next if self.offset + self.per_page < count else None, bg=Theme.BG, icon_name="down", icon_size=32)

    def _thumb(self, path: str, meta: dict, row: int, frame: Rect) -> List[str]:
        key = (path, row)
        if key in self.thumbs:
            return self.thumbs[key]
        if path in _PNG:
            png = _PNG[path]
            cells = 24
            cmds = mosaic(png, frame.x + (frame.w - cells * 2) // 2, frame.y + (frame.h - cells * 2) // 2, cells, 2,
                          Theme.SURFACE2, colors=24) if png else []
            if not cmds:
                cmds = [icon("files", frame.x + (frame.w - 32) // 2, frame.y + (frame.h - 32) // 2, 32, Theme.SURFACE2, Theme.MUTED)]
            self.thumbs[key] = cmds
            return cmds
        _PNG[path] = None
        self.app.spawn(self._fetch(path, meta))
        return [fill(frame.inset(6), Theme.SURFACE2)]

    async def _fetch(self, path: str, meta: dict):
        png = await asyncio.get_running_loop().run_in_executor(None, thumbnail_png, meta, path)
        _PNG[path] = png
        for k in [k for k in self.thumbs if k[0] == path]:
            del self.thumbs[k]
        self.app.invalidate()

    def _open(self, e: dict):
        if e["dir"]:
            self.folder, self.offset = e["path"], 0
            self.app.clear_content = True
            self.app.spawn(self.load())
        else:
            self.app.go(FilePage(self.app, e["path"], self))

    def _up(self):
        self.folder, self.offset = self.folder.rpartition("/")[0], 0
        self.app.clear_content = True
        self.app.spawn(self.load())

    def _toggle_sort(self):
        self.by_name = not self.by_name
        self._sort()
        self.offset = 0
        self.thumbs = {}
        self.app.invalidate()

    def _prev(self):
        self.offset = max(0, self.offset - self.per_page)
        self.thumbs = {}
        self.app.invalidate()

    def _next(self):
        self.offset += self.per_page
        self.thumbs = {}
        self.app.invalidate()


class FilePage(Page):
    """A G-code file: big thumbnail, time, weight, layers, date, whether the loaded filament matches; Print."""

    nav = "files"
    CELLS, CELL = 72, 4

    def __init__(self, app: App, path: str, back: Optional[FilesPage] = None):
        super().__init__(app)
        self.path = path
        self.back = back
        self.meta: dict = {}
        self.thumb: Optional[List[str]] = None

    def enter(self):
        self.app.spawn(self._load())

    async def _load(self):
        try:
            self.meta = await self.app.call("server.files.metadata", filename=self.path)
        except Exception as e:
            logging.info("no metadata for %s: %s", self.path, e)
        self.app.invalidate()
        png = _PNG.get(self.path)
        if png is None:
            png = await asyncio.get_running_loop().run_in_executor(None, thumbnail_png, self.meta, self.path)
            _PNG[self.path] = png
        frame = self._frame()
        size = self.CELLS * self.CELL
        self.thumb = mosaic(png, frame.x + (frame.w - size) // 2, frame.y + (frame.h - size) // 2, self.CELLS, self.CELL,
                            Theme.SURFACE2) if png else []
        self.app.invalidate()

    def _frame(self) -> Rect:
        return Rect(CONTENT.x + 12, CONTENT.y + 12, 300, CONTENT.h - 24)

    def draw(self, c):
        app = self.app
        m = self.meta
        left = Rect(CONTENT.x, CONTENT.y, 324, CONTENT.h)
        ui.card(c, "fp/l", left)
        frame = self._frame()
        ui.card(c, "fp/l/f", frame, Theme.SURFACE2, Theme.SURFACE, 10)
        if self.thumb:
            c.op("fp/l/f/i", self.thumb)
        else:
            c.op("fp/l/f/i", [text(frame, "Loading..." if self.thumb is None else "No preview", FONT_XS, Theme.MUTED,
                                   Theme.SURFACE2, CENTER)])
        right = Rect(CONTENT.x + 332, CONTENT.y, CONTENT.w - 332, CONTENT.h)
        name = Rect(right.x, right.y, right.w, 76)
        ui.card(c, "fp/n", name)
        lines = wrap_px(strip_gcode(self.path), name.w - 32, FONT_SB, 2)
        for i in range(2):
            ui.label(c, "fp/n/%d" % i, Rect(name.x + 16, name.y + 8 + i * 30, name.w - 32, 30), lines[i] if i < len(lines) else "",
                     FONT_SB, Theme.TEXT)
        stats = Rect(right.x, right.y + 84, right.w, 120)
        ui.card(c, "fp/s", stats)
        grams = m.get("filament_weight_total")
        layer = m.get("layer_height")
        count = m.get("layer_count")
        modified = m.get("modified")
        cells = [
            ("clock", fmt_duration(m.get("estimated_time")) if m.get("estimated_time") else "--", ""),
            ("weight", ("%.1f g" % grams) if grams else "--", ""),
            ("layers", ("%.2f" % layer) if layer else "--", ("x %d" % count) if count else ""),
            ("cal", time.strftime("%d %b", time.localtime(modified)) if modified else "--", ""),
        ]
        for i, (ic, v, sub) in enumerate(cells):
            cell = Rect(stats.x + 14 + (i % 2) * (stats.w // 2), stats.y + 6 + (i // 2) * 54, stats.w // 2 - 20, 54)
            c.op("fp/s/%d" % i, [fill(cell, Theme.SURFACE), icon(ic, cell.x, cell.y + 15, 24, Theme.SURFACE, Theme.MUTED)] +
                 ui.value_cmds(Rect(cell.x + 34, cell.y, cell.w - 34, cell.h), v, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT,
                               False, sub, FONT_XS)[1:])
        check = Rect(right.x, right.y + 212, right.w, 56)
        ui.card(c, "fp/c", check)
        c.op("fp/c/t", self._filament(check))
        foot = Rect(right.x, right.y + right.h - 76, right.w, 76)
        ui.button(c, "fp/back", Rect(foot.x, foot.y, 76, foot.h), "", self._back, bg=Theme.BG, icon_name="back")
        ui.button(c, "fp/del", Rect(foot.x + 84, foot.y, 76, foot.h), "", self._delete if not app.printing else None,
                  style=ui.DANGER, bg=Theme.BG, icon_name="trash")
        ui.button(c, "fp/print", Rect(foot.x + 168, foot.y, foot.w - 168, foot.h), "Print" if not app.printing else "Busy",
                  self._print if not app.printing else None, style=ui.ACCENT, bg=Theme.BG, font=FONT_MB, icon_name="play",
                  icon_size=32)

    def _filament(self, r: Rect) -> List[str]:
        """Which loaded gate matches the file's material, with a check (or a warning when none does)."""
        mats = _unique(self.meta.get("filament_type"))
        box = mmu.parse(self.app.status)
        cmds = [fill(r.inset(8), Theme.SURFACE)]
        x = r.x + 16
        if not mats:
            return cmds + [text(Rect(x, r.y, r.w - 32, r.h), "Material not in the file", FONT_XS, Theme.MUTED, Theme.SURFACE, LEFT)]
        parts, ok = [], True
        if box is not None:
            for mat in mats[:2]:
                gate = next((s for s in box.slots if s.available and s.material.upper() == mat.upper()), None)
                if gate is None:
                    ok = False
                    parts.append("%s: no gate" % mat)
                else:
                    color = gate_color(gate)
                    if color is not None and not parts:
                        ui.swatch(cmds, x + 10, r.y + r.h // 2, 10, color, Theme.SURFACE)
                        x += 30
                    parts.append("%s  Gate %d" % (mat, gate.index + 1))
        else:
            parts = mats[:2]
        cmds += parts_cmds(Rect(x, r.y, r.x + r.w - x - 50, r.h), parts, FONT_S, Theme.TEXT, Theme.SURFACE)[1:]
        if box is not None:
            cmds.append(icon("check" if ok else "warn", r.x + r.w - 42, r.y + (r.h - 24) // 2, 24, Theme.SURFACE,
                             Theme.OK if ok else Theme.MUTED))
        return cmds

    def _back(self):
        self.app.go(self.back or FilesPage)

    def _print(self):
        self.app.printer.startPrint(self.path)
        self.app.toast("Starting " + strip_gcode(self.path))

    def _delete(self):
        app = self.app

        async def delete():
            try:
                await app.call("server.files.delete_file", path="gcodes/" + self.path)
                app.toast("Deleted " + strip_gcode(self.path), Theme.OK)
            except Exception as e:
                app.toast("Could not delete: %s" % e, Theme.ERR)
            if self.back is not None:
                await self.back.load()
            self._back()

        confirm(app, "Delete file", "Delete %s from the printer? This cannot be undone." % strip_gcode(self.path), "Delete",
                lambda: app.spawn(delete()))
