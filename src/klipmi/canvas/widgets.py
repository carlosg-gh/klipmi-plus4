# SPDX-License-Identifier: GPL-3.0-or-later
"""Widgets: functions that draw one thing onto a Canvas and register its touch area.

Every widget takes the colour it sits on (`bg`) so it can erase itself, and a key
that is unique on the page. Buttons look pressed while `canvas.pressed` is their key.
"""

from typing import Callable, Optional, Sequence

from .gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Canvas, Rect, Theme, big_char,
                  big_char_width, big_width, disc, fill, mix, rounded, text)

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
    c.op(key, rounded(r, color, radius), [fill(r, bg)] if erase else ())


def label(c: Canvas, key: str, r: Rect, s: str, font: int = FONT_M, fg: int = Theme.TEXT, bg: int = Theme.SURFACE,
          align: int = LEFT):
    c.op(key, [text(r, s, font, fg, bg, align)], [fill(r, bg)])


def button(c: Canvas, key: str, r: Rect, caption: str, action: Optional[Callable[[], None]],
           style: str = NORMAL, bg: int = Theme.SURFACE, font: int = FONT_M, radius: int = 6,
           active: bool = False, sub: str = ""):
    """A rounded button. `active` draws it selected (accent); disabled when `action` is None."""
    face, ink = _STYLE[ACCENT if active and style == NORMAL else style]
    if action is None:
        face, ink = mix(face, bg, 0.6), Theme.FAINT
    elif c.pressed == key:
        face = mix(face, Theme.TEXT, 0.25)
    inner = r.inset(radius // 2, 2)
    cmds = rounded(r, face, radius)
    if sub:
        top, bottom = Rect(inner.x, inner.y + 2, inner.w, inner.h // 2), Rect(inner.x, inner.y + inner.h // 2, inner.w, inner.h // 2 - 2)
        cmds += [text(top, caption, font, ink, face, CENTER), text(bottom, sub, FONT_S, mix(ink, face, 0.35), face, CENTER)]
    else:
        cmds.append(text(inner, caption, font, ink, face, CENTER))
    c.op(key, cmds, [fill(r, bg)])
    if action is not None:
        c.hit(key, r, action)


def chip(c: Canvas, key: str, r: Rect, s: str, color: int, bg: int = Theme.SURFACE, ink: int = Theme.BG):
    c.op(key, rounded(r, color, r.h // 2) + [text(r.inset(r.h // 3, 0), s, FONT_S, ink, color, CENTER)], [fill(r, bg)])


def dot(c: Canvas, key: str, x: int, y: int, radius: int, color: int, bg: int):
    c.op(key, [disc(x, y, radius, color)], [disc(x, y, radius, bg)])


def bar(c: Canvas, key: str, r: Rect, frac: float, color: int = Theme.ACCENT, track: int = Theme.SURFACE2,
        bg: int = Theme.SURFACE):
    """Progress bar with rounded ends; only the cut point moves between frames."""
    frac = max(0.0, min(1.0, frac))
    filled = int(r.w * frac)
    radius = r.h // 2
    cmds = rounded(r, track, radius)
    if filled > 0:
        cmds += rounded(Rect(r.x, r.y, max(filled, 2 * radius), r.h), color, radius)
    c.op(key, cmds, [fill(r, bg)])


def toggle(c: Canvas, key: str, r: Rect, on: bool, action: Optional[Callable[[], None]], bg: int = Theme.SURFACE):
    """A switch: pill track with a knob."""
    track = Theme.ACCENT if on else Theme.RAISED
    if c.pressed == key:
        track = mix(track, Theme.TEXT, 0.2)
    radius = r.h // 2
    knob_x = r.x + r.w - radius if on else r.x + radius
    c.op(key, rounded(r, track, radius) + [disc(knob_x, r.y + radius, radius - 4, Theme.TEXT)], [fill(r, bg)])
    if action is not None:
        c.hit(key, r.inset(-8), action)


def big_text(c: Canvas, key: str, x: int, y: int, s: str, size: int, fg: int, bg: int, align: int = LEFT,
             width: int = 0, gap: int = 0):
    """Large seven-segment text; each character is its own part, so only changed digits redraw.

    With `width` the string is right- or centre-aligned in that width and the unused
    space is cleared.
    """
    gap = gap or max(3, size // 8)
    total = big_width(s, size, gap)
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
        c.op("%s/%d" % (key, i), big_char(x, y, size, ch, fg, bg), [fill(Rect(x, y, big_char_width(size, ch), size), bg)])
        x += big_char_width(size, ch) + gap


def segmented(c: Canvas, key: str, r: Rect, options: Sequence[str], selected: int,
              on_select: Callable[[int], None], bg: int = Theme.SURFACE):
    """A row of mutually exclusive choices (tabs, step sizes)."""
    c.op(key, rounded(r, Theme.BG if bg != Theme.BG else Theme.SURFACE, r.h // 2), [fill(r, bg)])
    for i, cell in enumerate(r.inset(3).split_h(len(options), 3)):
        button(c, "%s/%d" % (key, i), cell, options[i], (lambda i=i: on_select(i)),
               style=ACCENT if i == selected else GHOST, bg=Theme.BG, font=FONT_S if cell.w < 90 else FONT_M,
               radius=cell.h // 2)
