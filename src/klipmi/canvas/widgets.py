# SPDX-License-Identifier: GPL-3.0-or-later
"""Widgets: functions that draw one thing onto a Canvas and register its touch area.

Every widget takes the colour it sits on (`bg`) so it can erase itself, and a key
that is unique on the page. Buttons look pressed while `canvas.pressed` is their key.
"""

from typing import Callable, Optional, Sequence

from .gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Canvas, Rect, Theme, big_font, big_width, clean,
                  disc, fill, icon, mix, rounded, text, text_width, wrap_px)

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


def button(c: Canvas, key: str, r: Rect, caption: str, action: Optional[Callable[[], None]],
           style: str = NORMAL, bg: int = Theme.SURFACE, font: int = FONT_M, radius: int = 6,
           active: bool = False, sub: str = "", icon_name: str = ""):
    """A rounded button. `active` draws it selected (accent); disabled when `action` is None.
    `icon_name` puts a 24 px icon left of the caption."""
    face, ink = _STYLE[ACCENT if active and style == NORMAL else style]
    if action is None:
        face, ink = mix(face, bg, 0.6), Theme.FAINT
    elif c.pressed == key:
        face = mix(face, Theme.TEXT, 0.25)
    inner = r.inset(min(radius // 2, 6), 2)
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


def big_text(c: Canvas, key: str, x: int, y: int, s: str, size: int, fg: int, bg: int, align: int = LEFT,
             width: int = 0, gap: int = 0):
    """Large digits (the SemiBold digit fonts); each character is its own part, so only changed ones redraw.

    `size` is the box height (the 48 px font shows ~35 px digits, the 96 px one ~70). With `width` the string
    is right- or centre-aligned in that width and the unused space is cleared.
    """
    font = big_font(size)
    s = clean(s)
    total = text_width(s, font)
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
        w = text_width(ch, font)
        box = Rect(x, y, w, size)
        c.op("%s/%d" % (key, i), [text(box, ch, font, fg, bg, LEFT)], [fill(box, bg)])
        x += w


def segmented(c: Canvas, key: str, r: Rect, options: Sequence[str], selected: int,
              on_select: Callable[[int], None], bg: int = Theme.SURFACE):
    """A row of mutually exclusive choices (tabs, step sizes)."""
    track = Theme.BG if bg != Theme.BG else Theme.SURFACE
    c.op(key, rounded(r, track, r.h // 2, bg), [fill(r, bg)])
    for i, cell in enumerate(r.inset(3).split_h(len(options), 3)):
        button(c, "%s/%d" % (key, i), cell, options[i], (lambda i=i: on_select(i)),
               style=ACCENT if i == selected else GHOST, bg=Theme.BG, font=FONT_S if cell.w < 90 else FONT_M,
               radius=cell.h // 2)
