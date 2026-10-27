# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw a small picture on the display as a mosaic of filled rectangles.

The screen can only show pictures stored in its firmware, so a G-code thumbnail is quantised to a few
colours and drawn as horizontal runs of `fill` commands (a 48x48 mosaic is a few hundred commands).
Needs Pillow; without it `mosaic` returns nothing.
"""

import io
from typing import List

from .gfx import Rect, fill, rgb


def mosaic(png: bytes, x: int, y: int, cells: int, cell: int, bg: int, colors: int = 28) -> List[str]:
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    except Exception:
        return []
    # flatten onto the background the picture sits on
    r = (bg >> 11 & 31) << 3
    g = (bg >> 5 & 63) << 2
    b = (bg & 31) << 3
    base = Image.new("RGBA", im.size, (r, g, b, 255))
    base.alpha_composite(im)
    small = base.convert("RGB").resize((cells, cells), Image.BOX)
    q = small.quantize(colors=colors, dither=Image.Dither.NONE)
    palette = q.getpalette()
    px = q.load()
    cmds: List[str] = []
    for row in range(cells):
        col = 0
        while col < cells:
            idx = px[col, row]
            end = col + 1
            while end < cells and px[end, row] == idx:
                end += 1
            color = rgb(palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2])
            cmds.append(fill(Rect(x + col * cell, y + row * cell, (end - col) * cell, cell), color))
            col = end
    return cmds
