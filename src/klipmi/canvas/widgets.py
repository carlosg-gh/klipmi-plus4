# SPDX-License-Identifier: GPL-3.0-or-later
"""Widgets: functions that draw one thing onto a Canvas and register its touch area.

Every widget takes the colour it sits on (`bg`) so it can erase itself, and a key that is unique on the
page. A pressed button keeps its face (so its baked icon still matches) and gets a light outline instead.

Type: labels are Light 20/24 px in MUTED, values and button captions SemiBold 24/32 px, big readings the
48/96 px digit fonts. Temperatures get a drawn degree ring (the fonts are ASCII only).
"""

from typing import Callable, List, Optional, Sequence

from .gfx import (CENTER, FONT_D48, FONT_D96, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, RIGHT, Canvas, Rect,
                  Theme, clean, disc, fill, icon, mix, ring, rounded, soft_disc, text, text_width)

NORMAL, ACCENT, DANGER, OUTLINE, QUIET = "normal", "accent", "danger", "outline", "quiet"

_STYLE = {  # face, ink, icon ink (None: the face is the backdrop's colour, see button())
    NORMAL: (Theme.SURFACE2, Theme.TEXT, Theme.TEXT),
    ACCENT: (Theme.ACCENT, Theme.BG, Theme.BG),
    DANGER: (Theme.ERR_DIM, Theme.ERR_INK, Theme.ERR_INK),
    OUTLINE: (None, Theme.TEXT, Theme.TEXT),
    QUIET: (None, Theme.MUTED, Theme.MUTED),  # no face, no outline: an icon or caption on the backdrop
}
RADIUS = 10
LINE = {FONT_XS: 26, FONT_XSB: 26, FONT_S: 30, FONT_SB: 30, FONT_MB: 40, FONT_D48: 56, FONT_D96: 104}
CAP = {FONT_XS: 15, FONT_XSB: 15, FONT_S: 18, FONT_SB: 18, FONT_MB: 24, 9: 24, FONT_D48: 35, FONT_D96: 70}
DEG = {FONT_XS: (3, 1), FONT_XSB: (3, 2), FONT_S: (3, 2), FONT_SB: (4, 2), FONT_MB: (5, 2), 9: (5, 2),
       FONT_D48: (7, 3), FONT_D96: (11, 4)}  # degree ring (radius, thickness)


def card(c: Canvas, key: str, r: Rect, color: int = Theme.SURFACE, bg: int = Theme.BG, radius: int = 12,
         erase: bool = True):
    c.op(key, rounded(r, color, radius, bg), [fill(r, bg)] if erase else ())


def label(c: Canvas, key: str, r: Rect, s: str, font: int = FONT_XS, fg: int = Theme.MUTED, bg: int = Theme.SURFACE,
          align: int = LEFT):
    c.op(key, [text(r, s, font, fg, bg, align)], [fill(r, bg)])


def icon_label(c: Canvas, key: str, r: Rect, icon_name: str, s: str, bg: int = Theme.SURFACE, font: int = FONT_XS,
               fg: int = Theme.MUTED, size: int = 24):
    """A muted icon followed by a caption: the heading of a tile or row."""
    y = r.y + (r.h - size) // 2
    c.op(key, [fill(r, bg), icon(icon_name, r.x, y, size, bg, Theme.MUTED),
               text(Rect(r.x + size + 10, r.y, r.w - size - 10, r.h), s, font, fg, bg, LEFT)], [fill(r, bg)])


def _deg(x: int, cy: int, font: int, fg: int) -> List[str]:
    """A degree ring whose left edge is at `x`, aligned with the cap height around `cy`."""
    radius, thick = DEG.get(font, (3, 2))
    top = cy - CAP.get(font, 18) // 2
    cx, cyy = x + radius, top + radius
    return [ring(cx, cyy, radius - i, fg) for i in range(thick)]


def deg_width(font: int) -> int:
    radius, _ = DEG.get(font, (3, 2))
    return 2 * radius + 3


def value_cmds(r: Rect, s: str, font: int, fg: int, bg: int, align: int = LEFT, degree: bool = False,
               suffix: str = "", suffix_font: int = FONT_XS, suffix_degree: bool = False,
               suffix_fg: int = Theme.MUTED, suffix_gap: int = 8) -> List[str]:
    """Commands for a reading such as `182°` or `42%` (one string, natural spacing), plus an optional
    smaller muted suffix on the same baseline, such as `/ 215°`. Laid out from measured glyph widths."""
    s, suffix = clean(s), clean(suffix)
    w_main = text_width(s, font) + 1
    w_deg = deg_width(font) if degree else 0
    w_suf = (text_width(suffix, suffix_font) + suffix_gap + (deg_width(suffix_font) if suffix_degree else 0)) if suffix else 0
    total = w_main + w_deg + w_suf
    x0 = r.x if align == LEFT else (r.x + r.w - total if align == RIGHT else r.x + (r.w - total) // 2)
    cy = r.y + r.h // 2
    cmds = [fill(r, bg), text(Rect(x0, r.y, w_main + 1, r.h), s, font, fg, bg, LEFT)]
    if degree:
        cmds += _deg(x0 + w_main + 1, cy, font, fg)
    if suffix:
        sx = x0 + w_main + w_deg + suffix_gap
        sw = text_width(suffix, suffix_font) + 1
        base = cy + CAP.get(font, 18) // 2  # shared baseline
        box_h = LINE.get(suffix_font, 26)
        sy = base - box_h // 2 - CAP.get(suffix_font, 15) // 2
        cmds.append(text(Rect(sx, sy, sw + 1, box_h), suffix, suffix_font, suffix_fg, bg, LEFT))
        if suffix_degree:
            cmds += _deg(sx + sw + 1, sy + box_h // 2, suffix_font, suffix_fg)
    return cmds


def value(c: Canvas, key: str, r: Rect, s: str, font: int, fg: int = Theme.TEXT, bg: int = Theme.SURFACE,
          align: int = LEFT, degree: bool = False, suffix: str = "", suffix_font: int = FONT_XS,
          suffix_degree: bool = False, suffix_fg: int = Theme.MUTED, suffix_gap: int = 8):
    c.op(key, value_cmds(r, s, font, fg, bg, align, degree, suffix, suffix_font, suffix_degree, suffix_fg, suffix_gap),
         [fill(r, bg)])


def temp_str(t: Optional[float]) -> str:
    return "--" if t is None else "%d" % round(t)


def button(c: Canvas, key: str, r: Rect, caption: str = "", action: Optional[Callable[[], None]] = None,
           style: str = NORMAL, bg: int = Theme.SURFACE, font: int = FONT_SB, icon_name: str = "", icon_size: int = 0,
           vertical: bool = False, sub: str = "", radius: int = RADIUS, icon_ink: Optional[int] = None,
           ink: Optional[int] = None, align: int = CENTER, selected: bool = False, face: Optional[int] = None):
    """A rounded button: icon only, icon + caption (side by side or `vertical`), or caption over a muted `sub`.

    OUTLINE buttons are a border ring on the backdrop; `selected` turns any NORMAL/OUTLINE button into ACCENT.
    Disabled when `action` is None (muted ink). `face` overrides the style's face colour."""
    if selected and style in (NORMAL, OUTLINE):
        style = ACCENT
    style_face, fg, ifg = _STYLE[style]
    face = face if face is not None else style_face
    fg, ifg = ink if ink is not None else fg, icon_ink if icon_ink is not None else (ink if ink is not None else ifg)
    edge = Theme.BORDER if style == OUTLINE else None
    if face is None:
        face = bg
    if action is None:
        fg = ifg = Theme.MUTED if style != ACCENT else mix(Theme.BG, face, 0.3)
    pressed = c.pressed == key and action is not None
    if pressed:  # a light ring around the unchanged face
        cmds = rounded(r, Theme.TEXT, radius, bg) + rounded(r.inset(2), face, max(2, radius - 2), Theme.TEXT)
    elif edge is not None:
        cmds = rounded(r, edge, radius, bg) + rounded(r.inset(2), face, max(2, radius - 2), edge)
    elif face != bg:
        cmds = rounded(r, face, radius, bg)
    else:
        cmds = [fill(r, bg)]
    size = icon_size or (32 if (vertical or not caption) and min(r.w, r.h) >= 56 else 24)
    if icon_name and not caption:
        cmds.append(icon(icon_name, r.x + (r.w - size) // 2, r.y + (r.h - size) // 2, size, face, ifg))
    elif icon_name and vertical:
        line = LINE.get(font, 30)
        top = r.y + (r.h - size - 4 - line) // 2
        cmds.append(icon(icon_name, r.x + (r.w - size) // 2, top, size, face, ifg))
        cmds.append(text(Rect(r.x + 4, top + size + 4, r.w - 8, line), caption, font, fg, face, CENTER))
    elif icon_name:
        cw = text_width(caption, font) + 2
        x0 = r.x + max(4, (r.w - cw - size - 10) // 2) if align == CENTER else r.x + 16
        cmds.append(icon(icon_name, x0, r.y + (r.h - size) // 2, size, face, ifg))
        cmds.append(text(Rect(x0 + size + 10, r.y + 2, r.x + r.w - x0 - size - 12, r.h - 4), caption, font, fg, face, LEFT))
    elif sub:
        line, sline = LINE.get(font, 30), 26
        top = r.y + (r.h - line - sline) // 2
        inner = r.inset(12, 0)
        cmds += [text(Rect(inner.x, top, inner.w, line), caption, font, fg, face, align),
                 text(Rect(inner.x, top + line, inner.w, sline), sub, FONT_XS, Theme.MUTED if style != ACCENT else
                      mix(Theme.BG, face, 0.3), face, align)]
    else:
        cmds.append(text(r.inset(6, 2), caption, font, fg, face, align))
    c.op(key, cmds, [fill(r, bg)])
    if action is not None:
        c.hit(key, r, action)


def chip(c: Canvas, key: str, r: Rect, s: str, color: int, bg: int = Theme.SURFACE, ink: int = Theme.BG,
         font: int = FONT_XSB):
    c.op(key, rounded(r, color, min(r.h // 2, 12), bg) + [text(r.inset(8, 0), s, font, ink, color, CENTER)], [fill(r, bg)])


def dot(c: Canvas, key: str, x: int, y: int, radius: int, color: int, bg: int):
    c.op(key, soft_disc(x, y, radius, color, bg), [disc(x, y, radius + 1, bg)])


def bar(c: Canvas, key: str, r: Rect, frac: float, color: int = Theme.ACCENT, track: int = Theme.SURFACE2,
        bg: int = Theme.SURFACE):
    """Progress bar with rounded ends."""
    frac = max(0.0, min(1.0, frac))
    radius = r.h // 2
    filled = int(r.w * frac)
    cmds = rounded(r, track, radius, bg)
    if filled > 0:
        cmds += rounded(Rect(r.x, r.y, max(filled, 2 * radius), r.h), color, radius, bg if filled >= r.w - radius else track)
    c.op(key, cmds, [fill(r, bg)])


def slider(c: Canvas, key: str, r: Rect, frac: float, on_set: Optional[Callable[[float], None]],
           bg: int = Theme.SURFACE, color: int = Theme.ACCENT):
    """A 16 px track with a handle; touching anywhere on it sets the value (0..1) at that point."""
    frac = max(0.0, min(1.0, frac))
    track = Rect(r.x, r.y + (r.h - 16) // 2, r.w, 16)
    hx = track.x + 5 + int((track.w - 10) * frac)
    cmds = [fill(r, bg)] + rounded(track, Theme.SURFACE2, 8, bg)
    if frac > 0:  # the fill's right end hides under the handle
        cmds += rounded(Rect(track.x, track.y, max(16, hx + 5 - track.x), 16), color, 8, bg)
    knob = Rect(hx - 5, r.y + (r.h - 32) // 2, 10, 32)
    cmds += rounded(knob, Theme.TEXT if on_set else Theme.MUTED, 4, bg)
    c.op(key, cmds, [fill(r, bg)])
    if on_set is not None:
        c.hit(key, r, lambda x, y: on_set(max(0.0, min(1.0, (x - track.x - 5) / max(1, track.w - 10)))), wants_xy=True)


def toggle(c: Canvas, key: str, r: Rect, on: bool, action: Optional[Callable[[], None]], bg: int = Theme.SURFACE):
    """A switch: 40 px pill with a 32 px knob."""
    track = Theme.ACCENT if on else Theme.SURFACE2
    knob = Theme.TEXT if on else Theme.MUTED
    pill = Rect(r.x, r.y + (r.h - 40) // 2, r.w, 40)
    kx = pill.x + pill.w - 36 if on else pill.x + 4
    cmds = [fill(r, bg)] + rounded(pill, track, 20, bg) + rounded(Rect(kx, pill.y + 4, 32, 32), knob, 16, track)
    if c.pressed == key:
        cmds += [ring(kx + 16, pill.y + 20, 17, Theme.TEXT)]
    c.op(key, cmds, [fill(r, bg)])
    if action is not None:
        c.hit(key, r.inset(-8), action)


def swatch(cmds: List[str], x: int, y: int, radius: int, color: int, bg: int):
    """A colour dot; colours close to the backdrop get a ring so they stay visible."""
    cmds += soft_disc(x, y, radius, color, bg)
    if _close(color, bg):
        cmds += [ring(x, y, radius, Theme.MUTED), ring(x, y, radius - 1, mix(Theme.MUTED, color, 0.5))]


def _close(a: int, b: int) -> bool:
    from .gfx import unrgb
    return sum((p - q) ** 2 for p, q in zip(unrgb(a), unrgb(b))) < 40 ** 2


def spool(c: Canvas, key: str, cx: int, cy: int, radius: int, color: Optional[int], bg: int, hub: int,
          ring_color: Optional[int] = None, erase_r: int = 0):
    """A filament spool seen from the side: coloured disc, hub hole. `color` None draws an empty gate."""
    cmds = [disc(cx, cy, erase_r or radius + 6, bg)]
    if ring_color is not None:
        cmds += [ring(cx, cy, radius + 5 - i, ring_color) for i in range(3)]
    if color is None:
        cmds += [ring(cx, cy, radius - i, Theme.BORDER) for i in range(3)]
        cmds += [ring(cx, cy, radius * 4 // 10 - i, Theme.BORDER) for i in range(3)]
    else:
        swatch(cmds, cx, cy, radius, color, bg)
        cmds += soft_disc(cx, cy, radius * 45 // 100, hub, color)
    c.op(key, cmds, [disc(cx, cy, erase_r or radius + 6, bg)])
