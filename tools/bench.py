#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure how fast the display executes drawing commands (needs the serial port to itself)."""

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
            return
    print("  sync timeout")


def main():
    link = SerialLink("/dev/ttyS1")
    link.open()
    n = 60
    tests = [
        ("fill 10x10", ["fill %d,10,10,10,%d" % (10 + i, i * 100) for i in range(n)]),
        ("fill 200x100", ["fill 100,100,200,100,%d" % (i * 300) for i in range(n)]),
        ("fill 800x480 (full)", ["fill 0,0,800,480,%d" % (i * 500) for i in range(12)]),
        ("cirs r10", ["cirs 300,300,10,%d" % (i * 300) for i in range(n)]),
        ("cirs r30", ["cirs 300,300,30,%d" % (i * 300) for i in range(n)]),
        ("xstr font1 200x30", ['xstr 10,400,200,30,1,65535,%d,0,1,1,"Hello world"' % (i * 300) for i in range(n)]),
        ("xstr font0 300x40", ['xstr 10,400,300,40,0,65535,%d,0,1,1,"Temperature 215 C"' % (i * 300) for i in range(n)]),
        ("line 200", ["line 10,200,210,%d,65535" % (200 + i) for i in range(n)]),
    ]
    for window in (256, 900):
        for name, cmds in tests:
            run(link, name, cmds, window)
    link.port.write(b"fill 0,0,800,480,0" + END)


if __name__ == "__main__":
    main()
