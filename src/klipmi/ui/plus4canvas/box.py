# SPDX-License-Identifier: GPL-3.0-or-later
"""The optional Box page: Happy Hare / Bunny-Box gates, box climate, load and unload."""

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Rect, Theme, fill, mix, rounded, text,
                               unrgb)
from klipmi.features import mmu

from .dialogs import choose, confirm, keypad

POSITIONS = {
    -1: "position unknown", 0: "parked in its gate", 1: "at the gate", 2: "entering the bowden", 3: "in the bowden",
    4: "at the end of the bowden", 5: "at the extruder entry", 6: "at the extruder", 7: "entering the extruder",
    8: "at the toolhead sensor", 9: "in the extruder", 10: "loaded to the nozzle",
}
STATUS = {
    mmu.GATE_UNKNOWN: ("Unknown", Theme.WARN), mmu.GATE_EMPTY: ("Empty", Theme.FAINT),
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
        return "not configured"
    ready = sum(1 for s in box.slots if s.available)
    if box.filament == "Loaded" and box.gate >= 0:
        return "gate %d loaded" % (box.gate + 1)
    return "%d of %d ready" % (ready, len(box.slots))


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
            ui.card(c, "box/none", Rect(12, 52, 776, 348))
            c.op("box/none/t", [text(Rect(40, 180, 720, 40), "No Happy Hare box is configured.", FONT_L, Theme.MUTED, Theme.SURFACE, CENTER)])
            return
        slots = Rect(12, 52, 580, 212).split_h(max(1, len(box.slots)), 10)
        for slot, r in zip(box.slots, slots):
            self.slot(c, box, slot, r)
        self.climate(c, box, Rect(604, 52, 184, 212))
        self.status(c, box, Rect(12, 274, 376, 126))
        self.actions(c, box, Rect(400, 274, 388, 126))

    def slot(self, c, box: mmu.Box, slot: mmu.Slot, r: Rect):
        app = self.app
        key = "box/s%d" % slot.index
        selected = self.selected == slot.index
        ring = Theme.ACCENT if selected else Theme.BG
        face = mix(Theme.SURFACE, Theme.TEXT, 0.06) if c.pressed == key else Theme.SURFACE
        c.op(key, rounded(r, ring, 16) + rounded(r.inset(3), face, 14))
        known = slot.available and slot.color
        swatch_color = mmu.rgb565(slot.color) if known else (Theme.SURFACE2 if slot.status != mmu.GATE_EMPTY else Theme.BG)
        sw = Rect(r.x + 14, r.y + 14, r.w - 28, 92)
        swatch = rounded(sw, swatch_color, 12)
        if slot.status == mmu.GATE_EMPTY:
            swatch = rounded(sw, Theme.RAISED, 12) + rounded(sw.inset(3), Theme.BG, 10)
        label = slot.material or ("?" if slot.status == mmu.GATE_UNKNOWN else ("" if slot.status == mmu.GATE_EMPTY else "--"))
        c.op(key + "/sw", swatch + [text(sw.inset(8), label, FONT_L, ink_for(swatch_color), swatch_color if slot.status != mmu.GATE_EMPTY else Theme.BG, CENTER)])
        status, color = STATUS.get(slot.status, ("?", Theme.MUTED))
        c.op(key + "/g", [text(Rect(r.x + 14, r.y + 114, r.w - 28, 22), "GATE %d" % (slot.index + 1), FONT_S, Theme.MUTED, face, LEFT)])
        c.op(key + "/st", [text(Rect(r.x + 14, r.y + 136, r.w - 28, 26), status, FONT_M, color, face, LEFT)])
        loaded = box.filament == "Loaded" and box.gate == slot.index
        if loaded:
            ui.chip(c, key + "/chip", Rect(r.x + 14, r.y + r.h - 38, r.w - 28, 26), "IN USE", Theme.ACCENT, face)
        else:
            c.op(key + "/chip", [text(Rect(r.x + 14, r.y + r.h - 40, r.w - 28, 28),
                                      slot.name or ("tap again to edit" if selected else ""), FONT_S, Theme.FAINT, face, LEFT)])
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
        c.op("box/clim/l", [text(Rect(r.x + 16, r.y + 10, r.w - 32, 22), "BOX CLIMATE", FONT_S, Theme.MUTED, Theme.SURFACE, LEFT)])
        temp = box.temperature if box.temperature is not None else 0
        ui.big_text(c, "box/clim/t", r.x + 16, r.y + 38, "%d" % round(temp), 40, Theme.TEXT, Theme.SURFACE)
        c.op("box/clim/u", [text(Rect(r.x + 110, r.y + 52, 60, 26), "C", FONT_L, Theme.MUTED, Theme.SURFACE, LEFT)])
        target = box.target or 0
        c.op("box/clim/tg", [text(Rect(r.x + 16, r.y + 86, r.w - 32, 22), ("heating to %d C" % target) if target else "heater off",
                                  FONT_S, Theme.WARN if target else Theme.FAINT, Theme.SURFACE, LEFT)])
        humid = "%d%% humidity" % round(box.humidity) if box.humidity is not None else "humidity n/a"
        c.op("box/clim/h", [text(Rect(r.x + 16, r.y + 110, r.w - 32, 24), humid, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.drying:
            ui.button(c, "box/clim/dry", Rect(r.x + 14, r.y + r.h - 64, r.w - 28, 50), "Stop drying",
                      lambda: app.gcode("MMU_HEATER STOP=1"), style=ui.DANGER, sub="drying now")
        else:
            ui.button(c, "box/clim/dry", Rect(r.x + 14, r.y + r.h - 64, r.w - 28, 50), "Dry filament", lambda: self.dry(),
                      style=ui.NORMAL, sub="choose material")

    def dry(self):
        app = self.app

        def start(temp, minutes):
            app.gcode("MMU_HEATER DRY=1 TEMP=%d TIMER=%d" % (temp, minutes))
            app.toast("Drying at %d C for %d h" % (temp, minutes // 60))

        options = [(name, "%d C, %d h" % (t, m // 60), (lambda t=t, m=m: start(t, m))) for name, t, m in DRYING]
        options.append(("Custom", "temperature, time", lambda: keypad(
            app, "Drying temperature", 45, 30, 65, lambda t: keypad(app, "Drying time (hours)", 4, 1, 24,
                                                                    lambda h: start(t, int(h * 60)), unit="h"), unit="C")))
        choose(app, "Dry filament", options, "The box heater runs with the lid closed; it stops by itself.")

    def status(self, c, box: mmu.Box, r: Rect):
        app = self.app
        key = "box/stat" + ("E" if box.errored else "N")
        if box.errored:
            ui.card(c, key, r, Theme.ERR_DIM)
            c.op(key + "/h", [text(Rect(r.x + 16, r.y + 10, r.w - 32, 26), "Box needs attention", FONT_M, Theme.TEXT, Theme.ERR_DIM, LEFT)])
            c.op(key + "/r", [text(Rect(r.x + 16, r.y + 38, r.w - 32, 22), box.reason or "Happy Hare paused the print", FONT_S, Theme.TEXT, Theme.ERR_DIM, LEFT)])
            row = Rect(r.x + 12, r.y + r.h - 58, r.w - 24, 46).split_h(3, 8)
            ui.button(c, key + "/u", row[0], "Unlock", lambda: app.gcode("MMU_UNLOCK"), bg=Theme.ERR_DIM)
            ui.button(c, key + "/rc", row[1], "Recover", lambda: app.gcode("MMU_RECOVER"), bg=Theme.ERR_DIM)
            ui.button(c, key + "/rs", row[2], "Resume", lambda: app.gcode("RESUME"), style=ui.ACCENT, bg=Theme.ERR_DIM)
            return
        ui.card(c, key, r)
        busy = box.busy
        c.op(key + "/a", [text(Rect(r.x + 16, r.y + 12, r.w - 32, 30), box.action if busy else "Idle", FONT_L,
                               Theme.ACCENT if busy else Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.filament == "Loaded" and box.gate >= 0:
            fil = "Gate %d is loaded" % (box.gate + 1)
        elif box.filament == "Unloaded":
            fil = "Nothing loaded"
        else:
            fil = "Filament state unknown"
        c.op(key + "/f", [text(Rect(r.x + 16, r.y + 50, r.w - 32, 26), fil, FONT_M, Theme.TEXT, Theme.SURFACE, LEFT)])
        if box.enabled:
            line, color = "Filament " + POSITIONS.get(box.filamentPos, "?"), Theme.MUTED
        else:
            line, color = "Happy Hare is disabled (More > Enable)", Theme.WARN
        c.op(key + "/p", [text(Rect(r.x + 16, r.y + 80, r.w - 32, 22), line, FONT_S, color, Theme.SURFACE, LEFT)])

    def actions(self, c, box: mmu.Box, r: Rect):
        app = self.app
        idle = not app.printing and not box.busy and box.enabled
        gate = self.selected
        rows = r.split_v(2, 10)
        top, bottom = rows[0].split_h(3, 10), rows[1].split_h(3, 10)

        def run(touch):
            script = mmu.gcode(touch, gate, box)
            if script:
                app.gcode(script)

        name = ("gate %d" % (gate + 1)) if gate >= 0 else "pick a gate"
        ui.button(c, "box/act/load", top[0], "Load", (lambda: run(mmu.LOAD)) if idle and gate >= 0 else None, style=ui.ACCENT, sub=name)
        ui.button(c, "box/act/unload", top[1], "Unload", (lambda: run(mmu.UNLOAD)) if idle and box.filament != "Unloaded" else None,
                  sub="back to its gate")
        ui.button(c, "box/act/eject", top[2], "Eject", (lambda: run(mmu.EJECT)) if idle and gate >= 0 else None, sub=name)
        ui.button(c, "box/act/check", bottom[0], "Check", (lambda: confirm(
            app, "Check gates", "Happy Hare checks every gate for filament. It may move each filament a short way.",
            "Check gates", lambda: app.gcode("MMU_CHECK_GATE ALL=1"), danger=False)) if idle else None, sub="all gates")
        ui.button(c, "box/act/preload", bottom[1], "Preload", (lambda: app.gcode("MMU_PRELOAD GATE=%d" % gate)) if idle and gate >= 0 else None,
                  sub=name)
        ui.button(c, "box/act/more", bottom[2], "More", lambda: self.more(box), style=ui.GHOST, sub="recover, enable")

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

    width, height = 640, 380

    def __init__(self, app: App, gate: int):
        super().__init__(app)
        self.gate = gate
        box = box_state(app)
        slot = box.slots[gate] if box and gate < len(box.slots) else mmu.Slot(gate)
        self.material = slot.material if slot.material in MATERIALS else "PLA"
        self.color = (slot.color or "ffffff")[:6].lower()

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 16, p.w - 48, 34), "Gate %d" % (self.gate + 1), FONT_L)
        ui.segmented(c, "modal/mat", Rect(p.x + 20, p.y + 60, p.w - 40, 48), MATERIALS,
                     MATERIALS.index(self.material), self._material)
        grid = Rect(p.x + 20, p.y + 122, p.w - 40, 150)
        for i, ((hexcolor, name), cell) in enumerate(zip(PALETTE, [r for row in grid.split_v(2, 10) for r in row.split_h(6, 10)])):
            color = mmu.rgb565(hexcolor)
            key = "modal/c%d" % i
            ring = Theme.ACCENT if hexcolor == self.color else Theme.SURFACE
            c.op(key, rounded(cell, ring, 12) + rounded(cell.inset(4), color, 10) +
                 [text(cell.inset(8), name, FONT_S, ink_for(color), color, CENTER)])
            c.hit(key, cell, lambda h=hexcolor: self._color(h))
        row = Rect(p.x + 20, p.y + p.h - 76, p.w - 40, 58).split_h(3, 12)
        ui.button(c, "modal/cancel", row[0], "Cancel", self.close)
        ui.button(c, "modal/clear", row[1], "Clear", self._clear, style=ui.GHOST, sub="forget filament")
        ui.button(c, "modal/save", row[2], "Save", self._save, style=ui.ACCENT, sub="%s, %s" % (self.material, self._name()))

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
