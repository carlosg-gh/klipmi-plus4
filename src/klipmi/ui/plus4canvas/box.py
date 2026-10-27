# SPDX-License-Identifier: GPL-3.0-or-later
"""The optional Box page: Happy Hare / Bunny-Box gates, box climate, load and unload."""

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_M, FONT_S, LEFT, RIGHT, Rect, Theme, disc, fill, mix, rounded, text,
                               unrgb)
from klipmi.features import mmu

from .dialogs import choose, confirm, keypad

POSITIONS = {
    -1: "position unknown", 0: "parked in its gate", 1: "at the gate", 2: "entering the bowden", 3: "in the bowden",
    4: "at the end of the bowden", 5: "at the extruder entry", 6: "at the extruder", 7: "entering the extruder",
    8: "at the toolhead sensor", 9: "in the extruder", 10: "loaded to the nozzle",
}
STATUS = {
    mmu.GATE_UNKNOWN: ("Not set", Theme.WARN), mmu.GATE_EMPTY: ("Empty", Theme.FAINT),
    mmu.GATE_AVAILABLE: ("Ready", Theme.OK), mmu.GATE_BUFFER: ("Buffer", Theme.ACCENT),
}
MATERIALS = ["PLA", "PETG", "ABS", "ASA", "TPU", "PA"]
PALETTE = [("ffffff", "White"), ("1a1a1a", "Black"), ("808080", "Grey"), ("e53935", "Red"), ("fb8c00", "Orange"),
           ("fdd835", "Yellow"), ("43a047", "Green"), ("1e88e5", "Blue"), ("8e24aa", "Purple"), ("f06292", "Pink"),
           ("8d6e63", "Brown"), ("00acc1", "Teal")]
DRYING = [("PLA", 45, 240), ("PETG", 55, 240), ("ABS / ASA", 60, 240), ("TPU", 50, 240), ("Nylon", 65, 360)]


def box_state(app: App):
    return mmu.parse(app.status)


def mmu_summary(app: App) -> str:
    box = box_state(app)
    if box is None:
        return "none"
    ready = sum(1 for s in box.slots if s.available)
    if box.filament == "Loaded" and box.gate >= 0:
        return "gate %d" % (box.gate + 1)
    return "%d/%d ready" % (ready, len(box.slots))


def ink_for(color: int) -> int:
    r, g, b = unrgb(color)
    return Theme.BG if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else Theme.TEXT


class BoxPage(Page):
    title = "Box"
    nav = "box"

    def __init__(self, app):
        super().__init__(app)
        self.selected = mmu.UNKNOWN

    def enter(self):
        box = box_state(self.app)
        if box is not None and box.gate >= 0:
            self.selected = box.gate

    def draw(self, c):
        app = self.app
        box = box_state(app)
        if box is None:
            ui.card(c, "box/none", CONTENT)
            c.op("box/none/t", [text(Rect(CONTENT.x + 20, CONTENT.y + 170, CONTENT.w - 40, 50), "No Happy Hare box is configured.",
                                     FONT_M, Theme.MUTED, Theme.SURFACE, CENTER)])
            return
        slots = Rect(CONTENT.x, CONTENT.y, 536, 196).split_h(max(1, len(box.slots)), 8)
        for slot, r in zip(box.slots, slots):
            self.slot(c, box, slot, r)
        self.climate(c, box, Rect(CONTENT.x + 544, CONTENT.y, 160, 196))
        self.status(c, box, Rect(CONTENT.x, CONTENT.y + 206, 344, 210))
        self.actions(c, box, Rect(CONTENT.x + 356, CONTENT.y + 206, 348, 210))

    def slot(self, c, box: mmu.Box, slot: mmu.Slot, r: Rect):
        key = "box/s%d" % slot.index
        selected = self.selected == slot.index
        ring = Theme.ACCENT if selected else Theme.BG
        face = mix(Theme.SURFACE, Theme.TEXT, 0.06) if c.pressed == key else Theme.SURFACE
        c.op(key, rounded(r, ring, 12) + rounded(r.inset(3), face, 10))
        known = slot.available and slot.color
        swatch_color = mmu.rgb565(slot.color) if known else (Theme.SURFACE2 if slot.status != mmu.GATE_EMPTY else Theme.BG)
        sw = Rect(r.x + 10, r.y + 10, r.w - 20, 84)
        swatch = rounded(sw, swatch_color, 8)
        if slot.status == mmu.GATE_EMPTY:
            swatch = rounded(sw, Theme.RAISED, 8) + rounded(sw.inset(3), Theme.BG, 6)
        label = slot.material or ("?" if slot.status == mmu.GATE_UNKNOWN else ("" if slot.status == mmu.GATE_EMPTY else "--"))
        c.op(key + "/sw", swatch + [text(sw.inset(4), label, FONT_M, ink_for(swatch_color),
                                         swatch_color if slot.status != mmu.GATE_EMPTY else Theme.BG, CENTER)])
        status, color = STATUS.get(slot.status, ("?", Theme.MUTED))
        c.op(key + "/g", [text(Rect(r.x + 12, r.y + 98, r.w - 24, 30), "GATE %d" % (slot.index + 1), FONT_S, Theme.MUTED, face, LEFT)])
        c.op(key + "/st", [text(Rect(r.x + 12, r.y + 126, r.w - 24, 30), status, FONT_S, color, face, LEFT)])
        loaded = box.filament == "Loaded" and box.gate == slot.index
        if loaded:
            ui.chip(c, key + "/chip", Rect(r.x + 12, r.y + r.h - 40, r.w - 24, 30), "IN USE", Theme.ACCENT, face)
        else:
            c.op(key + "/chip", [text(Rect(r.x + 12, r.y + r.h - 42, r.w - 24, 32),
                                      slot.name or ("edit..." if selected else ""), FONT_S, Theme.FAINT, face, LEFT)])
        c.hit(key, r, lambda i=slot.index: self.tap(i))

    def tap(self, gate: int):
        if self.selected == gate:
            self.app.open_modal(SlotEditor(self.app, gate))
        else:
            self.selected = gate
            self.app.invalidate()

    def climate(self, c, box: mmu.Box, r: Rect):
        app = self.app
        ui.card(c, "box/clim", r)
        c.op("box/clim/l", [text(Rect(r.x + 14, r.y + 4, r.w - 28, 28), "CLIMATE", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        temp = box.temperature if box.temperature is not None else 0
        ui.temp_big(c, "box/clim/t", r.x + 14, r.y + 32, temp, 52, Theme.TEXT, Theme.SURFACE)
        target = box.target or 0
        c.op("box/clim/tg", [text(Rect(r.x + 14, r.y + 86, r.w - 28, 26), ("target %d" % target) if target else "heater off",
                                  FONT_S, Theme.WARN if target else Theme.FAINT, Theme.SURFACE, LEFT)])
        humid = "%d%% RH" % round(box.humidity) if box.humidity is not None else "RH n/a"
        c.op("box/clim/h", [text(Rect(r.x + 14, r.y + 112, r.w - 28, 26), humid, FONT_S, Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.drying:
            ui.button(c, "box/clim/dry", Rect(r.x + 10, r.y + r.h - 54, r.w - 20, 46), "Stop",
                      lambda: app.gcode("MMU_HEATER STOP=1"), style=ui.DANGER, font=FONT_S)
        else:
            ui.button(c, "box/clim/dry", Rect(r.x + 10, r.y + r.h - 54, r.w - 20, 46), "Dry", lambda: self.dry(),
                      style=ui.NORMAL, font=FONT_S)

    def dry(self):
        app = self.app

        def start(temp, minutes):
            app.gcode("MMU_HEATER DRY=1 TEMP=%d TIMER=%d" % (temp, minutes))
            app.toast("Drying at %d C for %d h" % (temp, minutes // 60))

        options = [(name, "%d C, %d h" % (t, m // 60), (lambda t=t, m=m: start(t, m))) for name, t, m in DRYING]
        options.append(("Custom", "temp and time", lambda: keypad(
            app, "Drying temperature", 45, 30, 65, lambda t: keypad(app, "Drying time (hours)", 4, 1, 24,
                                                                    lambda h: start(t, int(h * 60)), unit="h"), unit="C")))
        choose(app, "Dry filament", options, "The box heater runs with the lid closed; it stops by itself.")

    def status(self, c, box: mmu.Box, r: Rect):
        app = self.app
        key = "box/stat" + ("E" if box.errored else "N")
        if box.errored:
            ui.card(c, key, r, Theme.ERR_DIM)
            c.op(key + "/h", [text(Rect(r.x + 16, r.y + 8, r.w - 32, 40), "Box needs attention", FONT_S, Theme.TEXT, Theme.ERR_DIM, LEFT)])
            ui.wrapped(c, key + "/r", Rect(r.x + 16, r.y + 50, r.w - 32, 90), box.reason or "Happy Hare paused the print",
                       FONT_S, Theme.TEXT, Theme.ERR_DIM, 3, 30)
            row = Rect(r.x + 10, r.y + r.h - 62, r.w - 20, 52).split_h(3, 8)
            ui.button(c, key + "/u", row[0], "Unlock", lambda: app.gcode("MMU_UNLOCK"), bg=Theme.ERR_DIM, font=FONT_S)
            ui.button(c, key + "/rc", row[1], "Recover", lambda: app.gcode("MMU_RECOVER"), bg=Theme.ERR_DIM, font=FONT_S)
            ui.button(c, key + "/rs", row[2], "Resume", lambda: app.gcode("RESUME"), style=ui.ACCENT, bg=Theme.ERR_DIM, font=FONT_S)
            return
        ui.card(c, key, r)
        busy = box.busy
        c.op(key + "/a", [text(Rect(r.x + 16, r.y + 8, r.w - 32, 44), box.action if busy else "Idle", FONT_M,
                               Theme.ACCENT if busy else Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.filament == "Loaded" and box.gate >= 0:
            fil = "Gate %d is loaded" % (box.gate + 1)
        elif box.filament == "Unloaded":
            fil = "Nothing loaded"
        else:
            fil = "Filament state unknown"
        c.op(key + "/f", [text(Rect(r.x + 16, r.y + 56, r.w - 32, 32), fil, FONT_S, Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.enabled:
            line, color = POSITIONS.get(box.filamentPos, "?"), Theme.MUTED
        else:
            line, color = "Happy Hare is disabled", Theme.WARN
        c.op(key + "/p", [text(Rect(r.x + 16, r.y + 90, r.w - 32, 32), line, FONT_S, color, Theme.SURFACE, LEFT)])
        gate = self.selected
        c.op(key + "/sel", [text(Rect(r.x + 16, r.y + r.h - 54, r.w - 170, 40),
                                 ("Gate %d" % (gate + 1)) if gate >= 0 else "Pick a gate", FONT_S,
                                 Theme.ACCENT if gate >= 0 else Theme.MUTED, Theme.SURFACE, LEFT)])
        ui.button(c, key + "/info", Rect(r.x + r.w - 142, r.y + r.h - 56, 130, 46), "Details",
                  lambda: app.open_modal(BoxStatus(app)), font=FONT_S, icon_name="info")

    def actions(self, c, box: mmu.Box, r: Rect):
        app = self.app
        idle = not app.printing and not box.busy and box.enabled
        gate = self.selected
        rows = r.split_v(2, 10)
        top, bottom = rows[0].split_h(3, 8), rows[1].split_h(3, 8)

        def run(touch):
            script = mmu.gcode(touch, gate, box)
            if script:
                app.gcode(script)

        ui.button(c, "box/act/load", top[0], "Load", (lambda: run(mmu.LOAD)) if idle and gate >= 0 else None, style=ui.ACCENT, font=FONT_S)
        ui.button(c, "box/act/unload", top[1], "Unload", (lambda: run(mmu.UNLOAD)) if idle and box.filament != "Unloaded" else None,
                  font=FONT_S)
        ui.button(c, "box/act/eject", top[2], "Eject", (lambda: run(mmu.EJECT)) if idle and gate >= 0 else None, font=FONT_S)
        ui.button(c, "box/act/check", bottom[0], "Check", (lambda: confirm(
            app, "Check gates", "Happy Hare checks every gate for filament. It may move each filament a short way.",
            "Check gates", lambda: app.gcode("MMU_CHECK_GATE ALL=1"), danger=False)) if idle else None, font=FONT_S)
        ui.button(c, "box/act/preload", bottom[1], "Preload", (lambda: app.gcode("MMU_PRELOAD GATE=%d" % gate)) if idle and gate >= 0 else None,
                  font=FONT_S)
        ui.button(c, "box/act/more", bottom[2], "More", lambda: self.more(box), style=ui.GHOST, font=FONT_S)

    def more(self, box: mmu.Box):
        app = self.app
        choose(app, "Box", [
            ("Recover", "re-sync state", lambda: app.gcode("MMU_RECOVER")),
            ("Unlock", "after an error", lambda: app.gcode("MMU_UNLOCK")),
            ("Disable" if box.enabled else "Enable", "Happy Hare", lambda: app.gcode("MMU ENABLE=%d" % (0 if box.enabled else 1))),
            ("Motors off", "release gears", lambda: app.gcode("MMU_MOTORS_OFF")),
        ])


class SlotEditor(Modal):
    """Set a gate's material and colour (MMU_GATE_MAP)."""

    width, height = 680, 420

    def __init__(self, app: App, gate: int):
        super().__init__(app)
        self.gate = gate
        box = box_state(app)
        slot = box.slots[gate] if box and gate < len(box.slots) else mmu.Slot(gate)
        self.material = slot.material if slot.material in MATERIALS else "PLA"
        self.color = (slot.color or "ffffff")[:6].lower()

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 10, p.w - 48, 44),
                 "Gate %d: %s, %s" % (self.gate + 1, self.material, self._name()), FONT_M)
        ui.segmented(c, "modal/mat", Rect(p.x + 20, p.y + 62, p.w - 40, 56), MATERIALS,
                     MATERIALS.index(self.material), self._material)
        grid = Rect(p.x + 20, p.y + 130, p.w - 40, 190)
        for i, ((hexcolor, name), cell) in enumerate(zip(PALETTE, [r for row in grid.split_v(2, 10) for r in row.split_h(6, 10)])):
            color = mmu.rgb565(hexcolor)
            key = "modal/c%d" % i
            ring = Theme.ACCENT if hexcolor == self.color else Theme.SURFACE
            c.op(key, rounded(cell, ring, 10) + rounded(cell.inset(4), color, 7) +
                 [text(cell.inset(6), name, FONT_S, ink_for(color), color, CENTER)])
            c.hit(key, cell, lambda h=hexcolor: self._color(h))
        row = Rect(p.x + 20, p.y + p.h - 84, p.w - 40, 64).split_h(3, 12)
        ui.button(c, "modal/cancel", row[0], "Cancel", self.close)
        ui.button(c, "modal/clear", row[1], "Clear", self._clear, style=ui.GHOST)
        ui.button(c, "modal/save", row[2], "Save", self._save, style=ui.ACCENT)

    def _name(self):
        return dict(PALETTE).get(self.color, "#" + self.color)

    def _material(self, i):
        self.material = MATERIALS[i]
        self.app.invalidate()

    def _color(self, hexcolor):
        self.color = hexcolor
        self.app.invalidate()

    def _save(self):
        self.close()
        self.app.gcode("MMU_GATE_MAP GATE=%d MATERIAL=%s COLOR=%s QUIET=1" % (self.gate, self.material, self.color))
        self.app.toast("Gate %d: %s %s" % (self.gate + 1, self._name(), self.material), Theme.OK)

    def _clear(self):
        self.close()
        self.app.gcode("MMU_GATE_MAP GATE=%d MATERIAL= COLOR= NAME= QUIET=1" % self.gate)


class BoxStatus(Modal):
    """Happy Hare details: sensors on the filament path, tool to gate map, clog/tangle protection and counters."""

    width, height = 720, 440
    SENSORS = [("Pre-gate", "mmu_pre_gate"), ("Gate", "mmu_gate"), ("Extruder", "extruder"), ("Toolhead", "toolhead")]

    @property
    def panel(self) -> Rect:
        return Rect(40, 20, self.width, self.height)

    def draw(self, c):
        app, p = self.app, self.panel
        mm = app.status.get("mmu", {}) or {}
        box = box_state(app)
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 8, 260, 44), "Box status", FONT_M)
        pos = POSITIONS.get(box.filamentPos, "?") if box and box.enabled else "Happy Hare is disabled"
        c.op("modal/pos", [text(Rect(p.x + 260, p.y + 8, p.w - 284, 44), pos, FONT_S, Theme.MUTED, Theme.SURFACE, RIGHT)])

        # filament path: sensors as dots on a line
        sensors = mm.get("sensors", {}) or {}
        nodes = [(label, bool(sensors[name])) for label, name in self.SENSORS if name in sensors]
        nodes.append(("Nozzle", bool(box and box.filament == "Loaded" and box.filamentPos >= 10)))
        area = Rect(p.x + 24, p.y + 58, p.w - 48, 96)
        c.op("modal/pathbg", [fill(area, Theme.SURFACE)])
        step = area.w // len(nodes)
        cy = area.y + 30
        for i, (label, on) in enumerate(nodes):
            cx = area.x + step * i + step // 2
            if i + 1 < len(nodes):
                nx = area.x + step * (i + 1) + step // 2
                c.op("modal/seg%d" % i, [fill(Rect(cx + 14, cy - 2, nx - cx - 28, 4), Theme.ACCENT if on else Theme.RAISED)])
            color = Theme.OK if on else Theme.RAISED
            c.op("modal/dot%d" % i, [disc(cx, cy, 14, color)] + ([] if on else [disc(cx, cy, 9, Theme.SURFACE)]))
            c.op("modal/lab%d" % i, [text(Rect(cx - step // 2, area.y + 54, step, 34), label, FONT_S,
                                          Theme.TEXT if on else Theme.MUTED, Theme.SURFACE, CENTER)])

        # tool to gate map
        c.op("modal/tl", [text(Rect(p.x + 24, p.y + 160, 300, 28), "TOOL TO GATE", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        ttg = mm.get("ttg_map") or []
        count = max(1, len(ttg) or int(mm.get("num_gates", 4) or 4))
        chips = Rect(p.x + 24, p.y + 190, p.w - 48, 50).split_h(min(count, 8), 8)
        for t, cell in enumerate(chips):
            gate = ttg[t] if t < len(ttg) else t
            current = box is not None and box.tool == t
            face = Theme.ACCENT if current else Theme.SURFACE2
            ink = Theme.BG if current else Theme.TEXT
            c.op("modal/ttg%d" % t, rounded(cell, face, 8, Theme.SURFACE) + [text(cell, "T%d > %d" % (t, gate + 1), FONT_S, ink, face, CENTER)])

        # protection and counters
        fg = mm.get("flowguard", {}) or {}
        trigger = str(fg.get("trigger") or "")
        if trigger:
            guard, gcolor = trigger.capitalize(), Theme.ERR
        elif fg.get("enabled"):
            guard, gcolor = "Watching", Theme.OK
        else:
            guard, gcolor = "Off", Theme.MUTED
        cells = [
            ("CLOG / TANGLE", guard, gcolor),
            ("ENDLESS SPOOL", "On" if mm.get("endless_spool_enabled") else "Off", Theme.TEXT),
            ("TOOLCHANGES", str(mm.get("num_toolchanges", 0)), Theme.TEXT),
        ]
        for i, ((k, v, color), cell) in enumerate(zip(cells, Rect(p.x + 24, p.y + 252, p.w - 48, 70).split_h(3, 12))):
            c.op("modal/pk%d" % i, [fill(cell, Theme.SURFACE), text(cell.row(0, 28), k, FONT_S, Theme.MUTED, Theme.SURFACE, LEFT),
                                    text(cell.row(30, 38), v, FONT_M, color, Theme.SURFACE, LEFT)])
        level = float(fg.get("level", 0.0) or 0.0)
        frac = level / 100.0 if level > 1 else level
        ui.bar(c, "modal/level", Rect(p.x + 24, p.y + 330, p.w - 48, 10), frac, Theme.ERR if trigger else Theme.ACCENT)
        extra = []
        if mm.get("sync_feedback_state") and mm.get("sync_feedback_enabled"):
            extra.append("Sync " + str(mm["sync_feedback_state"]))
        remaining = mm.get("extruder_filament_remaining")
        if remaining is not None:
            extra.append("%d mm left in extruder" % round(float(remaining)))
        if mm.get("spoolman_support") not in (None, "off"):
            extra.append("Spoolman " + str(mm["spoolman_support"]))
        c.op("modal/extra", [fill(Rect(p.x + 24, p.y + 342, p.w - 48, 30), Theme.SURFACE),
                             text(Rect(p.x + 24, p.y + 342, p.w - 48, 30), "   ".join(extra), FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        ui.button(c, "modal/close", Rect(p.x + 24, p.y + p.h - 64, p.w - 48, 52), "Close", self.close, style=ui.ACCENT, font=FONT_S)
