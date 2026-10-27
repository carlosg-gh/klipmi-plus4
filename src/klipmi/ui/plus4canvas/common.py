# SPDX-License-Identifier: GPL-3.0-or-later
"""Things several pages share: heaters, fans, presets, formatting, little drawing helpers."""

import os
from typing import List, Optional, Sequence, Tuple

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import App
from klipmi.canvas.gfx import FONT_S, FONT_XS, LEFT, Rect, Theme, clean, fill, mix, soft_disc, text, text_width

MOONRAKER = os.environ.get("KLIPMI_MOONRAKER", "http://127.0.0.1:7125")

# object, name, icon, max target, "hot" reading for the colour scale
HEATERS = [
    ("extruder", "Nozzle", "nozzle", 300, 200.0),
    ("heater_bed", "Bed", "bed", 120, 80.0),
    ("heater_generic chamber", "Chamber", "chamber", 65, 50.0),
]
# the printer's own PRESET_MACRO_1..4 (freedi.cfg): name, nozzle, bed, chamber
PRESETS = [("PLA", 210, 60, 0), ("PETG", 240, 70, 0), ("ABS", 250, 95, 45), ("TPU", 250, 40, 0)]
CHART = {"extruder": Theme.HOT, "heater_bed": Theme.ACCENT, "heater_generic chamber": mix(Theme.ACCENT, Theme.ERR, 0.55)}


def heater_gcode(obj: str, target: float) -> str:
    name = {"extruder": "extruder", "heater_bed": "heater_bed"}.get(obj) or obj.split(" ", 1)[1]
    return "SET_HEATER_TEMPERATURE HEATER=%s TARGET=%d" % (name, target)


def heat_color(t: float, hot_at: float) -> int:
    from klipmi.canvas.gfx import heat_color as hc
    return hc(t, hot_at)


def apply_preset(app: App, nozzle: int, bed: int, chamber: int):
    script = [heater_gcode("extruder", nozzle), heater_gcode("heater_bed", bed)]
    if app.has("heater_generic chamber"):
        script.append(heater_gcode("heater_generic chamber", chamber))
    app.gcode("\n".join(script))


def cool_down(app: App):
    app.gcode("\n".join(heater_gcode(obj, 0) for obj, *_ in HEATERS if app.has(obj)))
    app.toast("Heaters off")


def fans(app: App):
    """(object, name, icon, gcode builder taking 0..1) for each fan the screen controls."""
    out = [("fan", "Part cooling", "part", lambda v: "M106 S%d" % round(v * 255))]
    for name, label, ic in (("sidefan", "Side", "side"), ("filterfan", "Exhaust", "exhaust")):
        if app.has("fan_generic " + name):
            out.append(("fan_generic " + name, label, ic, lambda v, n=name: "SET_FAN_SPEED FAN=%s SPEED=%.2f" % (n, v)))
    return out


AUTO_FANS = [("heater_fan hotend_fan", "Hotend"), ("heater_fan chamber_heater_fan", "Heater"),
             ("temperature_fan Mainboard_fan", "Board")]


def light_toggle(app: App):
    light = app.get("output_pin caselight", "value", None)
    if light is None:
        return None
    return lambda: app.gcode("SET_PIN PIN=caselight VALUE=%d" % (0 if light else 1))


def fmt_duration(seconds: Optional[float], clock: bool = False) -> str:
    """`1h 42m` / `22m`; with `clock`, `1:42` (hours:minutes)."""
    if seconds is None or seconds < 0:
        return "--"
    m = int(seconds) // 60
    if clock:
        return "%d:%02d" % (m // 60, m % 60)
    return "%dh %02dm" % (m // 60, m % 60) if m >= 60 else "%dm" % m


def strip_gcode(name: str) -> str:
    name = name.rsplit("/", 1)[-1]
    return name[:-6] if name.lower().endswith(".gcode") else name


def parts_cmds(r: Rect, parts: Sequence[str], font: int = FONT_XS, fg: int = Theme.MUTED, bg: int = Theme.SURFACE,
               x: Optional[int] = None) -> List[str]:
    """`a · b · c` with drawn middle dots (the fonts are ASCII only). Parts that do not fit are dropped."""
    cmds = [fill(r, bg)]
    x = r.x if x is None else x
    cy = r.y + r.h // 2 + 1
    for i, part in enumerate(p for p in parts if p):
        part = clean(part)
        w = text_width(part, font) + 2
        if i:
            if x + 22 + w > r.x + r.w:
                break
            cmds += soft_disc(x + 10, cy, 2, fg, bg)
            x += 22
        if x + w > r.x + r.w:
            w = r.x + r.w - x
        cmds.append(text(Rect(x, r.y, w, r.h), part, font, fg, bg, LEFT))
        x += w
    return cmds


def temps_cmds(r: Rect, values: Sequence[int], font: int, fg: int, bg: int) -> List[str]:
    """`210° · 60° · 45°` with drawn degree rings and dots."""
    cmds = [fill(r, bg)]
    x = r.x
    for i, v in enumerate(values):
        if i:
            cmds += soft_disc(x + 9, r.y + r.h // 2 + 1, 2, fg, bg)
            x += 20
        s = "%d" % v
        w = text_width(s, font) + 1 + ui.deg_width(font)
        cmds += ui.value_cmds(Rect(x, r.y, w, r.h), s, font, fg, bg, LEFT, True)[1:]
        x += w
    return cmds


def ink_for(color: int) -> int:
    from klipmi.canvas.gfx import unrgb
    r, g, b = unrgb(color)
    return Theme.BG if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else Theme.TEXT


def gate_color(slot) -> Optional[int]:
    from klipmi.features import mmu
    if slot is None or slot.status == mmu.GATE_EMPTY:
        return None
    if slot.color:
        return mmu.rgb565(slot.color)
    return Theme.MUTED if slot.available else None
