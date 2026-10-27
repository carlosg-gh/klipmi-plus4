# SPDX-License-Identifier: GPL-3.0-or-later
"""Widgets: functions that draw one thing onto a Canvas and register its touch area.

Every widget takes the colour it sits on (`bg`) so it can erase itself, and a key
that is unique on the page. Buttons look pressed while `canvas.pressed` is their key.
"""

from typing import Callable, Optional, Sequence

from .gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Canvas, Rect, Theme, big_font, big_width, clean,
                  disc, fill, icon, mix, ring, rounded, text, text_width, wrap_px)

NORMAL, ACCENT, DANGER, GHOST, OK = "normal", "accent", "danger", "ghost", "ok"

_STYLE = {
    NORMAL: (Theme.SURFACE2, Theme.TEXT),
    ACCENT: (Theme.ACCENT, Theme.BG),
    DANGER: (Theme.ERR, Theme.TEXT),
    GHOST: (Theme.SURFACE, Theme.MUTED),
    OK: (Theme.OK, Theme.BG),
}


def card(c: Canvas, key: str, r: Rect, color: int = Theme.SURFACE, bg: int = Theme.BG, radius: int = 8,
         erase: bool = False):
    c.op(key, rounded(r, color, radius, bg), [fill(r, bg)] if erase else ())


def label(c: Canvas, key: str, r: Rect, s: str, font: int = FONT_M, fg: int = Theme.TEXT, bg: int = Theme.SURFACE,
          align: int = LEFT):
    c.op(key, [text(r, s, font, fg, bg, align)], [fill(r, bg)])


BORDER = mix(Theme.RAISED, Theme.TEXT, 0.22)


def button(c: Canvas, key: str, r: Rect, caption: str, action: Optional[Callable[[], None]],
           style: str = NORMAL, bg: int = Theme.SURFACE, font: int = FONT_M, radius: int = 8,
           active: bool = False, sub: str = "", icon_name: str = "", border: bool = False):
    """A rounded button. `active` draws it selected (accent); disabled when `action` is None.
    `icon_name` puts a 24 px icon left of the caption. `border` outlines it (for buttons on the page background)."""
    face, ink = _STYLE[ACCENT if active and style == NORMAL else style]
    edge = BORDER if border and not (active and style == NORMAL) and style != ACCENT else None
    if action is None:
        face, ink = mix(face, bg, 0.5), mix(Theme.MUTED, face, 0.45)
        edge = mix(edge, bg, 0.6) if edge is not None else None
    elif c.pressed == key:
        face = mix(face, Theme.TEXT, 0.25)
    inner = r.inset(min(radius // 2, 6), 2)
    if edge is not None:
        cmds = rounded(r, edge, radius, bg) + rounded(r.inset(2), face, max(2, radius - 2), edge)
    else:
        cmds = rounded(r, face, radius, bg)
    if icon_name and not caption:  # icon-only button (the sidebar)
        size = 32 if min(r.w, r.h) >= 44 else 24
        cmds.append(icon(icon_name, r.x + (r.w - size) // 2, r.y + (r.h - size) // 2, size, face))
    elif icon_name:
        cw = text_width(caption, font)
        x0 = inner.x + max(0, (inner.w - cw - 32) // 2)
        cmds.append(icon(icon_name, x0, r.y + (r.h - 24) // 2, 24, face))
        inner = Rect(x0 + 32, inner.y, max(0, inner.w - (x0 - inner.x) - 32), inner.h)
        cmds.append(text(inner, caption, font, ink, face, LEFT))
    elif sub:
        top, bottom = Rect(inner.x, inner.y + 2, inner.w, inner.h // 2), Rect(inner.x, inner.y + inner.h // 2, inner.w, inner.h // 2 - 2)
        cmds += [text(top, caption, font, ink, face, CENTER), text(bottom, sub, FONT_S, mix(ink, face, 0.35), face, CENTER)]
    else:
        cmds.append(text(inner, caption, font, ink, face, CENTER))
    c.op(key, cmds, [fill(r, bg)])
    if action is not None:
        c.hit(key, r, action)


def wrapped(c: Canvas, key: str, r: Rect, s: str, font: int = FONT_S, fg: int = Theme.MUTED, bg: int = Theme.SURFACE,
            max_lines: int = 3, line_h: int = 0, align: int = LEFT):
    """A paragraph: one part per line, word-wrapped to the width of `r`."""
    line_h = line_h or (34 if font == FONT_M else 30)
    lines = wrap_px(s, r.w, font, max_lines)
    for i in range(max_lines):
        box = Rect(r.x, r.y + i * line_h, r.w, line_h)
        c.op("%s/%d" % (key, i), [text(box, lines[i] if i < len(lines) else "", font, fg, bg, align)], [fill(box, bg)])


def chip(c: Canvas, key: str, r: Rect, s: str, color: int, bg: int = Theme.SURFACE, ink: int = Theme.BG):
    c.op(key, rounded(r, color, r.h // 2, bg) + [text(r.inset(r.h // 3, 0), s, FONT_S, ink, color, CENTER)], [fill(r, bg)])


def dot(c: Canvas, key: str, x: int, y: int, radius: int, color: int, bg: int):
    c.op(key, [disc(x, y, radius, color)], [disc(x, y, radius, bg)])


def bar(c: Canvas, key: str, r: Rect, frac: float, color: int = Theme.ACCENT, track: int = Theme.SURFACE2,
        bg: int = Theme.SURFACE):
    """Progress bar with rounded ends; only the cut point moves between frames."""
    frac = max(0.0, min(1.0, frac))
    filled = int(r.w * frac)
    radius = r.h // 2
    cmds = rounded(r, track, radius, bg)
    if filled > 0:
        cmds += rounded(Rect(r.x, r.y, max(filled, 2 * radius), r.h), color, radius, track)
    c.op(key, cmds, [fill(r, bg)])


def toggle(c: Canvas, key: str, r: Rect, on: bool, action: Optional[Callable[[], None]], bg: int = Theme.SURFACE):
    """A switch: pill track with a knob."""
    track = Theme.ACCENT if on else Theme.RAISED
    if c.pressed == key:
        track = mix(track, Theme.TEXT, 0.2)
    radius = r.h // 2
    knob_x = r.x + r.w - radius if on else r.x + radius
    c.op(key, rounded(r, track, radius, bg) + [disc(knob_x, r.y + radius, radius - 4, Theme.TEXT)], [fill(r, bg)])
    if action is not None:
        c.hit(key, r.inset(-8), action)


def _cell(ch: str, font: int) -> int:
    """Width of one big character's box: every digit gets the widest digit's cell (tabular figures), padded so
    the glyph is never clipped."""
    if ch.isdigit():
        return max(text_width(d, font) for d in "0123456789") + 4
    return text_width(ch, font) + 4


def big_text(c: Canvas, key: str, x: int, y: int, s: str, size: int, fg: int, bg: int, align: int = LEFT,
             width: int = 0, gap: int = 0) -> int:
    """Large digits (the SemiBold digit fonts); each character is its own part, so only changed ones redraw.

    `size` is the box height (the 48 px font shows ~35 px digits, the 96 px one ~70). With `width` the string
    is right- or centre-aligned in that width and the unused space is cleared. Returns the drawn width.
    """
    font = big_font(size)
    s = clean(s)
    total = sum(_cell(ch, font) for ch in s)
    if width:
        if align == RIGHT:
            x0 = x + width - total
        elif align == CENTER:
            x0 = x + (width - total) // 2
        else:
            x0 = x
        c.op(key + "/pad", [fill(Rect(x, y, max(0, x0 - x), size), bg),
                            fill(Rect(x0 + total, y, max(0, x + width - x0 - total), size), bg)])
        x = x0
    for i, ch in enumerate(s):
        w = _cell(ch, font)
        box = Rect(x, y, w, size)
        c.op("%s/%d" % (key, i), [text(box, ch, font, fg, bg, CENTER)], [fill(box, bg)])
        x += w
    return total


def temp_big(c: Canvas, key: str, x: int, y: int, value: float, size: int, fg: int, bg: int, unit_font: int = FONT_M):
    """A temperature as big digits followed by a degree ring and C (the fonts have no degree sign)."""
    n = big_text(c, key, x, y, "%d" % round(value), size, fg, bg)
    rx = x + n + 3
    top = y + size // 6
    cw = text_width("C", unit_font)
    zone = Rect(rx - 2, y, cw + 60, size)  # also wipes digits that vanished when the number got shorter
    box = Rect(rx + 12, y + size // 6 + 2, cw + 6, size // 2 + 8)
    c.op(key + "/unit", [fill(zone, bg), ring(rx + 4, top + 5, 4, fg), ring(rx + 4, top + 5, 3, fg),
                         text(box, "C", unit_font, fg, bg, LEFT, 0)], [fill(zone, bg)])


def temp_text(c: Canvas, key: str, r: Rect, value: float, font: int, fg: int, bg: int, align: int = LEFT,
              prefix: str = ""):
    """Small temperature text such as `210 °C` (ring drawn, since the fonts are ASCII)."""
    num = "%s%d" % (prefix, round(value))
    w_num, w_c = text_width(num, font), text_width("C", font)
    total = w_num + 14 + w_c
    x0 = r.x if align == LEFT else (r.x + r.w - total if align == RIGHT else r.x + (r.w - total) // 2)
    cy = r.y + r.h // 2
    cap = {7: 15, 8: 18, 9: 24}.get(font, 18)
    ringy = cy - cap // 2 + 4
    c.op(key, [fill(r, bg), text(Rect(x0, r.y, w_num + 2, r.h), num, font, fg, bg, LEFT),
               ring(x0 + w_num + 6, ringy, 3, fg),
               text(Rect(x0 + w_num + 12, r.y, w_c + 4, r.h), "C", font, fg, bg, LEFT)],
         [fill(r, bg)])


def segmented(c: Canvas, key: str, r: Rect, options: Sequence[str], selected: int,
              on_select: Callable[[int], None], bg: int = Theme.SURFACE, gap: int = 8):
    """A row of mutually exclusive choices (tabs, step sizes): separate rounded buttons, the chosen one in accent."""
    c.op(key, [fill(r, bg)], [fill(r, bg)])
    for i, cell in enumerate(r.split_h(len(options), gap)):
        button(c, "%s/%d" % (key, i), cell, options[i], (lambda i=i: on_select(i)),
               style=ACCENT if i == selected else NORMAL, bg=bg, font=FONT_S if cell.w < 90 else FONT_M, radius=8)
