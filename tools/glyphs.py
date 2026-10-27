#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Show which symbols the HMI's fonts contain (the stock UI ships CJK, Cyrillic, Arabic and Hebrew text,
so its fonts cover far more than ASCII). Needs the serial port to itself."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from klipmi.canvas.link import END, SerialLink  # noqa: E402

ROWS = [
    "A: ℃ ° ± × ÷ µ ‰ № ← → ↑ ↓ ↔ ⇒",
    "B: ■ □ ▪ ▫ ● ○ ◎ ◆ ◇ ▲ △ ▼ ▽ ◀ ▶",
    "C: ★ ☆ ♪ ✓ ✔ ✗ ✘ ⚠ ⚙ ☀ ☁ ⏻ ⏸ ⏵ ⏹",
    "D: █ ▓ ▒ ░ ▀ ▄ ▌ ▐ ─ │ ┌ ┐ └ ┘ ═ ║",
    "E: ① ② ③ ④ Ⅰ Ⅱ Ⅲ ㎜ ㎝ ㎏ ・ … 〇 「」",
    "F: 温度 喷头 热床 料架 ÄÖÜ ñ é Ж Ω π",
]


def main():
    link = SerialLink("/dev/ttyS1")
    link.open()
    w = lambda cmd: (link.port.write(cmd.encode("utf-8") + END), link._frames(0.08))
    w("fill 0,0,800,480,0")
    y = 4
    for font in (0, 1, 2):
        for row in ROWS[:4] if font else ROWS:
            h = {0: 30, 1: 24, 2: 20}[font]
            w('xstr 8,%d,784,%d,%d,65535,0,0,1,1,"%s"' % (y, h, font, ("%d" % font) + row[1:]))
            y += h + 2
        y += 4
    print("errors seen:", [f.hex() for f in link._frames(0.3)])


if __name__ == "__main__":
    main()
