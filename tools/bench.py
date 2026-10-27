#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure how fast the display executes drawing commands (needs the serial port to itself).

    bench.py [--legacy] [--baud N]

Default runs the plus4-canvas.tft asset tests (fonts 0-3 Inter 16/20/24/32, 4-5 digits 48/96,
pictures 0-5 icons24, 6-11 icons32, 12-21 corner sheets); --legacy runs the QIDI-HMI shape tests.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from klipmi.canvas.link import END, SerialLink  # noqa: E402


def run(link, name, cmds, window):
    link.port.reset_input_buffer()
    start = time.time()
    in_flight = 0
    for cmd in cmds:
        data = cmd.encode() + END
        if in_flight + len(data) > window:
            sync(link)
            in_flight = 0
        link.port.write(data)
        in_flight += len(data)
    sync(link)
    ms = (time.time() - start) * 1000
    print("%-34s window %4d: %7.1f ms total, %6.2f ms/cmd" % (name, window, ms, ms / len(cmds)), flush=True)


def sync(link):
    link.port.write(b"sendme" + END)
    end = time.time() + 2
    buf = b""
    while time.time() < end:
        buf += link.port.read(64)
        if b"\x66" in buf and END in buf:
            junk = buf.replace(b"\x66", b"").replace(END, b"")
            if junk.strip(b"\x00"):
                print("  display replies: %r" % junk, flush=True)
            return
    print("  sync timeout")


N = 60
LEGACY = [
    ("fill 10x10", ["fill %d,10,10,10,%d" % (10 + i, i * 100) for i in range(N)]),
    ("fill 200x100", ["fill 100,100,200,100,%d" % (i * 300) for i in range(N)]),
    ("fill 800x480 (full)", ["fill 0,0,800,480,%d" % (i * 500) for i in range(12)]),
    ("cirs r10", ["cirs 300,300,10,%d" % (i * 300) for i in range(N)]),
    ("cirs r30", ["cirs 300,300,30,%d" % (i * 300) for i in range(N)]),
    ("line 200", ["line 10,200,210,%d,65535" % (200 + i) for i in range(N)]),
]


def xs(font, h, text, w=400):
    return ['xstr 10,300,%d,%d,%d,65535,%d,0,1,1,"%s"' % (w, h, font, i * 300, text) for i in range(N)]


ASSETS = [
    ("xstr Inter16 400x30", xs(0, 30, "Temperature 215.4 C")),
    ("xstr Inter20 400x30", xs(1, 30, "Temperature 215.4 C")),
    ("xstr Inter24 400x34", xs(2, 34, "Temperature 215.4 C")),
    ("xstr Inter32 400x44", xs(3, 44, "Temperature 215.4 C")),
    ("xstr Digit48 300x60", xs(4, 60, "215.4", 300)),
    ("xstr Digit96 400x110", xs(5, 110, "215.4")),
    ("xstr Inter16 80x24", xs(0, 24, "215 C", 80)),
    ("pic icons24 480x24", ["pic 100,100,%d" % (i % 6) for i in range(N)]),
    ("pic icons32 640x32", ["pic 100,100,%d" % (6 + i % 6) for i in range(N)]),
    ("pic corner sheet 96x100", ["pic 100,100,%d" % (12 + i % 10) for i in range(N)]),
    ("xpic icon 24x24", ["xpic 100,100,24,24,%d,0,%d" % (24 * (i % 20), i % 6) for i in range(N)]),
    ("xpic icon 32x32", ["xpic 100,100,32,32,%d,0,%d" % (32 * (i % 20), 6 + i % 6) for i in range(N)]),
    ("xpic corner 12x12", ["xpic 100,100,12,12,%d,28,%d" % (12 * (i % 4), 12 + i % 10) for i in range(N)]),
    ("xpic corner 24x24", ["xpic 100,100,24,24,%d,76,%d" % (24 * (i % 4), 12 + i % 10) for i in range(N)]),
    ("picq 24x24 (strip crop)", ["picq 100,100,24,24,%d" % (i % 6) for i in range(N)]),
]


def main():
    baud = int(sys.argv[sys.argv.index("--baud") + 1]) if "--baud" in sys.argv else 921600
    link = SerialLink("/dev/ttyS1", fast=baud, page="logo" if "--legacy" in sys.argv else "canvas")
    link.open()
    tests = LEGACY if "--legacy" in sys.argv else ASSETS
    for window in (256, 900):
        for name, cmds in tests:
            run(link, name, cmds, window)
    link.port.write(b"fill 0,0,800,480,0" + END)


if __name__ == "__main__":
    main()
