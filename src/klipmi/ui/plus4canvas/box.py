# SPDX-License-Identifier: GPL-3.0-or-later
"""Filament: the Happy Hare path diagram, tool map, FlowGuard and actions; the gate and dryer sheet."""

from typing import Optional

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, RIGHT, Rect, Theme, disc,
                               fill, icon, rounded, soft_disc, text, text_width)
from klipmi.features import mmu

from .common import gate_color, parts_cmds
from .dialogs import choose, confirm, keypad, wrapped

MATERIALS = ["PLA", "PETG", "ABS", "ASA", "TPU", "PA"]
PALETTE = [("ffffff", "White"), ("1a1a1a", "Black"), ("808080", "Grey"), ("e53935", "Red"), ("fb8c00", "Orange"),
           ("fdd835", "Yellow"), ("43a047", "Green"), ("1e88e5", "Blue"), ("8e24aa", "Purple"), ("f06292", "Pink")]
DRYING = [("PLA", 45, 240), ("PETG", 55, 240), ("ABS", 60, 240)]


def box_state(app: App) -> Optional[mmu.Box]:
    return mmu.parse(app.status)


def dryer_off(app: App):
    app.gcode("MMU_HEATER STOP=1")


def loaded_gate(box: mmu.Box) -> int:
    return box.gate if box.filament != "Unloaded" and box.gate >= 0 else -1


class FilamentPage(Page):
    nav = "filament"

    def draw(self, c):
        app = self.app
        box = box_state(app)
        if box is None:
            ui.card(c, "fl/none", CONTENT)
            ui.label(c, "fl/none/t", Rect(CONTENT.x, CONTENT.y + 180, CONTENT.w, 40), "No Happy Hare unit found", FONT_S,
                     Theme.MUTED, Theme.SURFACE, CENTER)
            return
        self.diagram(c, Rect(CONTENT.x, CONTENT.y, 456, CONTENT.h), box)
        self.side(c, Rect(CONTENT.x + 464, CONTENT.y, CONTENT.w - 464, CONTENT.h), box)

    def diagram(self, c, r: Rect, box: mmu.Box):
        app = self.app
        ui.card(c, "fl/d", r)
        mm = app.status.get("mmu", {}) or {}
        sensors = mm.get("sensors", {}) or {}
        n = max(1, len(box.slots))
        loaded = loaded_gate(box)
        pitch = (r.w - 24) // n
        xs = [r.x + 12 + pitch * i + pitch // 2 for i in range(n)]
        trunk = r.x + r.w // 2
        y_spool, y_pre, y_bus, y_gate, y_ext, y_noz = r.y + 60, r.y + 136, r.y + 176, r.y + 236, r.y + 312, r.y + 352
        live = None
        if loaded >= 0:
            live = gate_color(box.slots[loaded]) or Theme.ACCENT
        # wiring: thin grey for every gate, then the loaded path on top in the filament's colour
        cmds = [fill(Rect(r.x + 8, y_pre - 12, r.w - 16, y_noz - y_pre + 52), Theme.SURFACE)]
        for x in xs:
            cmds.append(fill(Rect(x - 2, y_pre, 4, y_bus - y_pre), Theme.BORDER))
        cmds.append(fill(Rect(min(xs) - 2, y_bus - 2, max(xs) - min(xs) + 4, 4), Theme.BORDER))
        cmds.append(fill(Rect(trunk - 2, y_bus, 4, y_noz - y_bus - 14), Theme.BORDER))
        if live is not None:
            x = xs[loaded]
            cmds.append(fill(Rect(x - 3, y_pre, 6, y_bus - y_pre + 3), live))
            cmds.append(fill(Rect(min(x, trunk) - 3, y_bus - 3, abs(trunk - x) + 6, 6), live))
            reach = y_noz - 14 if box.filamentPos >= 7 else (y_ext if box.filamentPos >= 5 else y_gate)
            cmds.append(fill(Rect(trunk - 3, y_bus, 6, reach - y_bus), live))
        for i, x in enumerate(xs):
            pre = mm.get("sensors", {}).get("mmu_pre_gate_%d" % i)
            if pre is None:
                pre = box.slots[i].available
            cmds += soft_disc(x, y_pre, 8, Theme.OK if pre else Theme.BORDER, Theme.SURFACE)
        for y, label, sname in ((y_gate, "Gate", "mmu_gate"), (y_ext, "Extruder", "extruder")):
            on = bool(sensors.get(sname))
            cmds += [disc(trunk, y, 14, Theme.SURFACE)] + soft_disc(trunk, y, 11, Theme.OK if on else Theme.BORDER, Theme.SURFACE)
            cmds.append(text(Rect(trunk + 24, y - 15, 160, 30), label, FONT_XS, Theme.MUTED, Theme.SURFACE, LEFT))
        cmds.append(icon("nozzle", trunk - 16, y_noz - 4, 32, Theme.SURFACE, Theme.TEXT))
        tool = ("T%d" % box.tool) if box.tool >= 0 else ("Bypass" if box.tool == mmu.BYPASS else "")
        cmds.append(text(Rect(trunk + 24, y_noz - 4, 160, 32), tool, FONT_XSB, Theme.TEXT, Theme.SURFACE, LEFT))
        c.op("fl/d/wire", cmds)
        for slot, x in zip(box.slots, xs):
            key = "fl/d/g%d" % slot.index
            color = gate_color(slot)
            ui.spool(c, key, x, y_spool, min(44, pitch // 2 - 10), color, Theme.SURFACE, Theme.SURFACE,
                     ring_color=Theme.ACCENT if slot.index == loaded else None, erase_r=min(52, pitch // 2 - 2))
            num_fg = Theme.ACCENT if slot.index == loaded else (Theme.TEXT if color is not None else Theme.MUTED)
            hub = Theme.SURFACE
            c.op(key + "/n", [text(Rect(x - 12, y_spool - 13, 24, 26), str(slot.index + 1), FONT_XSB, num_fg, hub, CENTER)])
            c.hit(key, Rect(x - pitch // 2, r.y, pitch, y_pre - r.y + 14), lambda g=slot.index: app.open_modal(GateSheet(app, g)))

    def side(self, c, r: Rect, box: mmu.Box):
        app = self.app
        mm = app.status.get("mmu", {}) or {}
        idle = not app.printing and not box.busy and box.enabled
        loaded = loaded_gate(box)
        top = Rect(r.x, r.y, r.w, 76 if not box.errored else 160)
        if box.errored:  # the reason gets the room the FlowGuard card has otherwise
            ui.card(c, "fl/st", top, Theme.ERR_DIM)
            wrapped(c, "fl/st/r", Rect(top.x + 14, top.y + 10, top.w - 28, 140), box.reason or "Happy Hare paused",
                    FONT_XS, Theme.ERR_INK, Theme.ERR_DIM, 5, 28)
        else:
            ui.card(c, "fl/st", top)
            cmds = [fill(top.inset(10), Theme.SURFACE)]
            x = top.x + 16
            if loaded >= 0:
                slot = box.slots[loaded]
                color = gate_color(slot)
                if color is not None:
                    ui.swatch(cmds, x + 14, top.y + 38, 14, color, Theme.SURFACE)
                    x += 40
                head = ["T%d" % box.tool if box.tool >= 0 else "", slot.material]
                sub = ["Gate %d" % (loaded + 1), box.action if box.busy else ("Loaded" if box.filamentPos >= 10 else "Partly loaded")]
            else:
                head, sub = ["Nothing loaded"], [box.action if box.busy else ("Disabled" if not box.enabled else "Idle")]
            cmds += parts_cmds(Rect(x, top.y + 8, top.x + top.w - x - 12, 32), head, FONT_SB, Theme.TEXT, Theme.SURFACE)[1:]
            cmds += parts_cmds(Rect(x, top.y + 40, top.x + top.w - x - 12, 28), sub, FONT_XS, Theme.MUTED, Theme.SURFACE)[1:]
            c.op("fl/st/t", cmds)
        ttg = mm.get("ttg_map") or list(range(len(box.slots)))
        tmap = Rect(r.x, top.y + top.h + 8, r.w, 84)
        ui.card(c, "fl/tm", tmap)
        chips = tmap.inset(8).split_h(max(1, min(len(ttg), 4)), 6)
        for t, cell in enumerate(chips):
            gate = ttg[t] if t < len(ttg) else t
            slot = box.slots[gate] if 0 <= gate < len(box.slots) else None
            current = box.tool == t
            key = "fl/tm/%d" % t
            if current:
                cmds = rounded(cell, Theme.ACCENT, 8, Theme.SURFACE) + rounded(cell.inset(2), Theme.SURFACE2, 6, Theme.ACCENT)
            else:
                cmds = rounded(cell, Theme.SURFACE2, 8, Theme.SURFACE)
            cmds.append(text(Rect(cell.x, cell.y + 4, cell.w, 26), "T%d" % t, FONT_XS, Theme.MUTED, Theme.SURFACE2, CENTER))
            color = gate_color(slot)
            label = str(gate + 1)
            lw = text_width(label, FONT_XSB) + 2
            x0 = cell.x + (cell.w - lw - 20) // 2
            if color is not None:
                ui.swatch(cmds, x0 + 6, cell.y + 48, 6, color, Theme.SURFACE2)
            cmds.append(text(Rect(x0 + 18, cell.y + 34, lw + 2, 28), label, FONT_XSB,
                             Theme.TEXT if color is not None else Theme.MUTED, Theme.SURFACE2, LEFT))
            c.op(key, cmds)
        fg = mm.get("flowguard", {}) or {}
        level = float(fg.get("level", 0.0) or 0.0)
        frac = level / 100.0 if level > 1 else level
        trigger = str(fg.get("trigger") or "")
        if not box.errored:
            self.flowguard(c, Rect(r.x, r.y + 176, r.w, 68), frac, trigger, fg)
        y = tmap.y + tmap.h + 8 if box.errored else r.y + 252
        self.actions(c, Rect(r.x, y, r.w, r.y + r.h - y), box, idle, loaded)

    def flowguard(self, c, guard, frac, trigger, fg):
        ui.card(c, "fl/fg", guard)
        ui.icon_label(c, "fl/fg/l", Rect(guard.x + 14, guard.y + 8, guard.w - 100, 30), "guard", "FlowGuard")
        state = trigger.capitalize() if trigger else ("%d%%" % round(frac * 100) if fg.get("enabled") else "Off")
        ui.label(c, "fl/fg/v", Rect(guard.x + guard.w - 100, guard.y + 8, 86, 30), state, FONT_XSB,
                 Theme.ERR if trigger else Theme.TEXT, Theme.SURFACE, RIGHT)
        ui.bar(c, "fl/fg/b", Rect(guard.x + 14, guard.y + 46, guard.w - 28, 10), frac,
               Theme.ERR if trigger else (Theme.WARN if frac > 0.6 else Theme.OK))

    def actions(self, c, grid, box, idle, loaded):
        app = self.app
        cells = [cell for row in grid.split_v(2, 8) for cell in row.split_h(2, 8)]
        if box.errored:
            ui.button(c, "fl/a0", cells[0], "Unlock", lambda: app.gcode("MMU_UNLOCK"), bg=Theme.BG, icon_name="lock",
                      icon_ink=Theme.MUTED, font=FONT_XSB)
            ui.button(c, "fl/a1", cells[1], "Recover", lambda: app.gcode("MMU_RECOVER"), bg=Theme.BG, icon_name="wrench",
                      icon_ink=Theme.MUTED, font=FONT_XSB)
            ui.button(c, "fl/a2", cells[2], "Resume", lambda: app.gcode("RESUME"), style=ui.ACCENT, bg=Theme.BG,
                      icon_name="play", font=FONT_XSB)
            ui.button(c, "fl/a3", cells[3], "More", lambda: self.more(box), bg=Theme.BG, icon_name="sys",
                      icon_ink=Theme.MUTED, font=FONT_XSB)
            return
        ui.button(c, "fl/a0", cells[0], "Unload", (lambda: app.gcode("MMU_UNLOAD")) if idle and loaded >= 0 else None,
                  bg=Theme.BG, icon_name="eject", icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "fl/a1", cells[1], "Check", (lambda: confirm(
            app, "Check gates", "Happy Hare checks every gate for filament and may move each one a short way.",
            "Check gates", lambda: app.gcode("MMU_CHECK_GATE ALL=1"), danger=False)) if idle else None,
            bg=Theme.BG, icon_name="refresh", icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "fl/a2", cells[2], "Recover", lambda: app.gcode("MMU_RECOVER"), bg=Theme.BG, icon_name="wrench",
                  icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "fl/a3", cells[3], "More", lambda: self.more(box), bg=Theme.BG, icon_name="sys",
                  icon_ink=Theme.MUTED, font=FONT_XSB)

    def more(self, box: mmu.Box):
        app = self.app
        mm = app.status.get("mmu", {}) or {}
        endless = bool(mm.get("endless_spool_enabled"))
        choose(app, "Happy Hare", [
            ("Unlock", "after an error", lambda: app.gcode("MMU_UNLOCK")),
            ("Bypass", "select the bypass", lambda: app.gcode("MMU_SELECT_BYPASS")),
            ("Endless spool", "now %s" % ("on" if endless else "off"),
             lambda: app.gcode("MMU_ENDLESS_SPOOL ENABLE=%d" % (0 if endless else 1))),
            ("Motors off", "release the gears", lambda: app.gcode("MMU_MOTORS_OFF")),
            ("Disable" if box.enabled else "Enable", "Happy Hare", lambda: app.gcode("MMU ENABLE=%d" % (0 if box.enabled else 1))),
            ("Home", "the selector", lambda: app.gcode("MMU_HOME")),
        ])


class GateSheet(Modal):
    """One gate: big spool, material and colour (MMU_GATE_MAP), load and eject; the box dryer underneath."""

    sheet = True
    nav = "filament"

    def __init__(self, app: App, gate: int):
        super().__init__(app)
        self.gate = gate
        box = box_state(app)
        slot = box.slots[gate] if box and 0 <= gate < len(box.slots) else mmu.Slot(gate)
        self.material = slot.material if slot.material in MATERIALS else ""
        self.color = (slot.color or "")[:6].lower()
        self.edited = False

    def draw(self, c):
        app = self.app
        box = box_state(app)
        if box is None or self.gate >= len(box.slots):
            self.close()
            return
        slot = box.slots[self.gate]
        idle = not app.printing and not box.busy and box.enabled
        top = Rect(CONTENT.x, CONTENT.y, CONTENT.w, CONTENT.h - 84)
        ui.card(c, "modal/g", top)
        color = mmu.rgb565(self.color) if self.color else gate_color(slot)
        ui.spool(c, "modal/g/spool", top.x + 112, top.y + 128, 92, color, Theme.SURFACE, Theme.SURFACE, erase_r=100)
        c.op("modal/g/name", [text(Rect(top.x + 12, top.y + 236, 200, 40), "Gate %d" % (self.gate + 1), FONT_MB, Theme.TEXT,
                                   Theme.SURFACE, CENTER)])
        status = {mmu.GATE_EMPTY: "Empty", mmu.GATE_AVAILABLE: "Ready", mmu.GATE_BUFFER: "Ready (buffer)"}.get(slot.status, "Unknown")
        c.op("modal/g/st", [text(Rect(top.x + 12, top.y + 276, 200, 28), status, FONT_XS, Theme.MUTED, Theme.SURFACE, CENTER)])
        right = Rect(top.x + 228, top.y + 14, top.w - 242, top.h - 28)
        name = dict(PALETTE).get(self.color, "")
        head = Rect(right.x, right.y, right.w - 64, 48)
        c.op("modal/g/head", parts_cmds(head, [self.material or slot.material or "No material", name], FONT_SB, Theme.TEXT, Theme.SURFACE))
        ui.button(c, "modal/close", Rect(right.x + right.w - 56, right.y, 56, 48), "", self.close, icon_name="x")
        mats = Rect(right.x, right.y + 60, right.w, 52).split_h(len(MATERIALS), 6)
        for i, (m, cell) in enumerate(zip(MATERIALS, mats)):
            ui.button(c, "modal/m%d" % i, cell, m, (lambda m=m: self._material(m)), style=ui.OUTLINE, font=FONT_XSB,
                      selected=m == (self.material or slot.material))
        sw = Rect(right.x, right.y + 124, right.w, 52)
        pitch = sw.w // len(PALETTE)
        for i, (hexcolor, cname) in enumerate(PALETTE):
            key = "modal/c%d" % i
            cx = sw.x + pitch * i + pitch // 2
            cmds = [fill(Rect(sw.x + pitch * i, sw.y, pitch, sw.h), Theme.SURFACE)]
            if hexcolor == self.color:
                cmds += [disc(cx, sw.y + 26, 25, Theme.ACCENT), disc(cx, sw.y + 26, 22, Theme.SURFACE)]
            ui.swatch(cmds, cx, sw.y + 26, 18, mmu.rgb565(hexcolor), Theme.SURFACE)
            c.op(key, cmds)
            c.hit(key, Rect(sw.x + pitch * i, sw.y, pitch, sw.h), lambda h=hexcolor: self._color(h))
        acts = Rect(right.x, right.y + right.h - 60, right.w, 60).split_h(3, 8)
        ui.button(c, "modal/load", acts[0], "Load", (lambda: self._run("MMU_CHANGE_TOOL GATE=%d STANDALONE=1" % self.gate))
                  if idle and slot.status != mmu.GATE_EMPTY else None, style=ui.ACCENT, icon_name="extrude")
        ui.button(c, "modal/eject", acts[1], "Eject", (lambda: self._run("MMU_EJECT GATE=%d" % self.gate)) if idle else None,
                  icon_name="eject", icon_ink=Theme.MUTED)
        ui.button(c, "modal/save", acts[2], "Save", self._save if self.edited else None, icon_name="check", icon_ink=Theme.MUTED)
        self.dryer(c, Rect(CONTENT.x, CONTENT.y + CONTENT.h - 76, CONTENT.w, 76), box)

    def dryer(self, c, r: Rect, box: mmu.Box):
        app = self.app
        ui.card(c, "modal/dry", r)
        if box.temperature is None:
            ui.label(c, "modal/dry/t", r.inset(16, 0), "No dryer sensor", FONT_XS)
            return
        cmds = [fill(Rect(r.x + 10, r.y + 10, 330, r.h - 20), Theme.SURFACE),
                icon("drop", r.x + 16, r.y + 22, 32, Theme.SURFACE, Theme.OK if box.target else Theme.MUTED)]
        cmds += ui.value_cmds(Rect(r.x + 58, r.y + 18, 150, 40), "%d" % round(box.temperature), FONT_SB, Theme.TEXT,
                              Theme.SURFACE, LEFT, True, ("/ %d" % round(box.target)) if box.target else "", FONT_XS,
                              bool(box.target))[1:]
        if box.humidity is not None:
            cmds.append(text(Rect(r.x + 230, r.y + 18, 100, 40), "%d%% RH" % round(box.humidity), FONT_XSB, Theme.TEXT,
                             Theme.SURFACE, LEFT))
        c.op("modal/dry/t", cmds)
        x = r.x + r.w - 10
        if box.target:
            x -= 96
            ui.button(c, "modal/dry/stop", Rect(x, r.y + 10, 96, r.h - 20), "Stop", lambda: dryer_off(app), style=ui.DANGER,
                      font=FONT_XSB)
        for i, (name, t, minutes) in reversed(list(enumerate(DRYING))):
            x -= 88
            ui.button(c, "modal/dry/%d" % i, Rect(x, r.y + 10, 80, r.h - 20), name,
                      lambda t=t, m=minutes: self._dry(t, m), style=ui.OUTLINE, font=FONT_XSB,
                      selected=bool(box.target) and round(box.target) == t)

    def _dry(self, temp: int, minutes: int):
        self.app.gcode("MMU_HEATER DRY=1 TEMP=%d TIMER=%d" % (temp, minutes))
        self.app.toast("Drying at %d C for %d h" % (temp, minutes // 60))

    def _material(self, m: str):
        self.material, self.edited = m, True
        self.app.invalidate()

    def _color(self, h: str):
        self.color, self.edited = h, True
        self.app.invalidate()

    def _save(self):
        args = ["GATE=%d" % self.gate]
        if self.material:
            args.append("MATERIAL=%s" % self.material)
        if self.color:
            args.append("COLOR=%s" % self.color)
        self.app.gcode("MMU_GATE_MAP %s QUIET=1" % " ".join(args))
        self.edited = False
        self.app.toast("Gate %d saved" % (self.gate + 1), Theme.OK)

    def _run(self, script: str):
        self.close()
        self.app.gcode(script)
