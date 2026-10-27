# SPDX-License-Identifier: GPL-3.0-or-later
"""Draw a small picture on the display as a mosaic of filled rectangles.

The screen can only show pictures stored in its firmware, so a G-code thumbnail is quantised to a few
colours and drawn as horizontal runs of `fill` commands (a 48x48 mosaic is a few hundred commands).
Needs Pillow; without it `mosaic` returns nothing.
"""

import io
from typing import List

from .gfx import Rect, fill, rgb


def mosaic(png: bytes, x: int, y: int, cells: int, cell: int, bg: int, colors: int = 56) -> List[str]:
    """`cells` x `cells` blocks of `cell` px; equal neighbours are merged into rectangles."""
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
    except Exception:
        return []
    r = (bg >> 11 & 31) << 3
    g = (bg >> 5 & 63) << 2
    b = (bg & 31) << 3
    base = Image.new("RGBA", im.size, (r, g, b, 255))
    base.alpha_composite(im)
    small = base.convert("RGB").resize((cells, cells), Image.LANCZOS)
    q = small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = q.getpalette()
    px = q.load()
    # horizontal runs, then stack identical runs of consecutive rows into one rectangle
    open_runs = {}
    cmds: List[str] = []

    def flush(key, row_end):
        col, end, idx, row0 = key[0], key[1], key[2], open_runs.pop(key)
        color = rgb(palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2])
        cmds.append(fill(Rect(x + col * cell, y + row0 * cell, (end - col) * cell, (row_end - row0) * cell), color))

    for row in range(cells + 1):
        runs = set()
        if row < cells:
            col = 0
            while col < cells:
                idx = px[col, row]
                end = col + 1
                while end < cells and px[end, row] == idx:
                    end += 1
                runs.add((col, end, idx))
                col = end
        for key in list(open_runs):
            if key not in runs:
                flush(key, row)
        for key in runs:
            open_runs.setdefault(key, row)
    return cmds
