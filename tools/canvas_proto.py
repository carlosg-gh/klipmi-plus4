#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prototype: draw a UI from the host onto the stock `logo` page of QIDI's Plus 4 HMI.

    canvas_proto.py fonts            font sampler
    canvas_proto.py home [seconds]   home screen with live temperatures, touch via coordinates

Needs the serial port to itself (stop klipmi/FreeDi). Logs every display reply and touch.
"""

import json
import struct
import sys
import time
import urllib.request

import serial

END = b"\xff\xff\xff"
PORT, BAUDS = "/dev/ttyS1", (921600, 115200)  # the stock HMI boots at 115200; `baud=` raises it until power-off
FAST = 921600
CODES = {0x00: "invalid", 0x01: "ok", 0x02: "bad component", 0x03: "bad page", 0x04: "bad picture",
         0x05: "bad font", 0x1A: "bad variable", 0x1B: "bad operation", 0x1C: "assignment failed",
         0x1E: "bad parameter count", 0x1F: "io failed", 0x20: "escape char error", 0x23: "name too long"}

RGB = lambda r, g, b: ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
BG, CARD, HI, TXT, DIM, RED = RGB(24, 26, 30), RGB(52, 56, 62), RGB(0, 170, 220), 65535, RGB(160, 165, 170), RGB(230, 70, 70)


class Display:
    def __init__(self, debug: bool = False):
        self.port = serial.Serial(PORT, BAUDS[-1], timeout=0.01)
        self.buf = b""
        self.touches = []
        self.debug = debug
        self.shown = {}  # what each text slot currently shows

    def frames(self, wait: float):
        end = time.time() + wait
        out = []
        while True:
            self.buf += self.port.read(256)
            while END in self.buf:
                frame, self.buf = self.buf.split(END, 1)
                if not frame:
                    continue
                if frame[0] == 0x67 and len(frame) == 6:
                    x, y, ev = struct.unpack(">HHB", frame[1:])
                    self.touches.append((x, y, ev))
                    if self.debug:
                        print("touch x=%d y=%d event=%d" % (x, y, ev), flush=True)
                else:
                    out.append(frame)
            if time.time() >= end:
                return out

    def write(self, cmd: str):
        self.port.write(cmd.encode("utf-8") + END)

    def send(self, cmd: str, wait: float = 0.0):
        """Fire and forget unless `wait`: with bkcmd=2 the display only answers failures."""
        self.write(cmd)
        for frame in self.frames(wait):
            if frame[:1] != b"":
                print("  %-60s -> %s" % (cmd[:60], CODES.get(frame[0], frame.hex())), flush=True)

    def text(self, x, y, w, h, font, color, back, s, xc=1, yc=1, sta=1):
        """Draws only if this slot shows something else; the solid background replaces the old text."""
        key = (x, y, w, h)
        value = (font, color, back, s)
        if self.shown.get(key) == value:
            return
        self.shown[key] = value
        self.write('xstr %d,%d,%d,%d,%d,%d,%d,%d,%d,%d,"%s"' % (x, y, w, h, font, color, back, xc, yc, sta, s.replace('"', "'")))

    def box(self, x, y, w, h, color):
        self.write("fill %d,%d,%d,%d,%d" % (x, y, w, h, color))
        for key in [k for k in self.shown if x <= k[0] < x + w and y <= k[1] < y + h]:
            del self.shown[key]


def alive(d: Display) -> bool:
    d.port.reset_input_buffer()
    d.buf = b""
    d.write("")
    d.frames(0.1)
    d.write("connect")
    return any(f.startswith(b"comok") for f in d.frames(0.4))


def open_canvas() -> Display:
    d = Display()
    for baud in BAUDS:  # a previous run may have left the display fast
        d.port.baudrate = baud
        if alive(d):
            break
    else:
        raise SystemExit("display does not answer")
    print("display at %d baud" % d.port.baudrate, flush=True)
    if d.port.baudrate != FAST:
        d.write("baud=%d" % FAST)  # temporary; `bauds=` would be saved
        d.port.flush()
        time.sleep(0.1)
        d.port.baudrate = FAST
        if not alive(d):
            d.port.baudrate = BAUDS[-1]
            raise SystemExit("display lost at %d baud; power-cycle the printer or rerun" % FAST)
        print("raised to %d baud" % FAST, flush=True)
    d.send("bkcmd=2")  # failures only
    d.send("page logo", 0.5)
    d.send("tm0.en=0", 0.1)  # the logo page restarts the UI after 100 s
    d.send("sendxy=1")
    d.send("dim=100", 0.1)
    d.box(0, 0, 800, 480, BG)
    return d


def fonts():
    d = open_canvas()
    for f in range(0, 12):
        d.text(16, 12 + f * 38, 770, 34, f, TXT, CARD, "font %d: Nozzle 41C  Bed 26C  Home Control Files 0123456789" % f, 0, 1)
    d.frames(12)


def moonraker():
    u = "http://127.0.0.1:7125/printer/objects/query?extruder&heater_bed&heater_generic%20chamber&print_stats"
    return json.load(urllib.request.urlopen(u, timeout=3))["result"]["status"]


NAV = ["Home", "Control", "Files", "Tools", "Settings"]


def home(seconds: float, small=1, big=0):
    import threading

    d = open_canvas()
    state = {"status": {}, "active": 0, "pressed": None, "touch": "touch: none", "stop": False}

    def poll():
        while not state["stop"]:
            try:
                state["status"] = moonraker()
            except Exception:
                pass
            time.sleep(1)

    threading.Thread(target=poll, daemon=True).start()

    # Static layout, drawn once
    rows = [("Nozzle", "extruder"), ("Bed", "heater_bed"), ("Chamber", "heater_generic chamber")]
    for i, (label, _) in enumerate(rows):
        y = 16 + i * 130
        d.box(16, y, 250, 120, CARD)
        d.text(16, y + 8, 250, 30, small, DIM, CARD, label)
    d.box(282, 16, 502, 380, CARD)
    d.text(282, 24, 502, 40, small, DIM, CARD, "Print status")

    def draw_nav():
        for i, name in enumerate(NAV):
            x = 16 + i * 154
            color = RGB(120, 200, 235) if i == state["pressed"] else (HI if i == state["active"] else CARD)
            d.text(x, 408, 146, 64, small, TXT, color, name)  # the text box is the button face

    def draw_values():
        status = state["status"]
        for i, (_, key) in enumerate(rows):
            t = status.get(key, {})
            shown = "%d / %d C" % (round(t.get("temperature", 0)), round(t.get("target", 0))) if t else "n/a"
            d.text(16, 16 + i * 130 + 44, 250, 64, big, TXT, CARD, shown)
        ps = status.get("print_stats", {})
        d.text(282, 90, 502, 60, big, TXT, CARD, (ps.get("state") or "?").capitalize())
        d.text(282, 170, 502, 40, small, TXT, CARD, ps.get("filename") or "No file loaded")
        d.text(282, 340, 502, 40, small, DIM, CARD, state["touch"])

    draw_nav()
    deadline = time.time() + seconds
    while time.time() < deadline:
        draw_values()
        for x, y, ev in d.touches[:]:
            d.touches.remove((x, y, ev))
            state["touch"] = "touch: x=%d y=%d %s" % (x, y, "press" if ev else "release")
            if 408 <= y <= 472:
                i = (x - 16) // 154
                if 0 <= i < 5 and x - 16 - i * 154 < 146:
                    if ev:
                        state["pressed"] = i
                    else:
                        state["active"], state["pressed"] = i, None
                    draw_nav()
                    continue
            state["pressed"] = None
            draw_nav()
        d.frames(0.02)
    state["stop"] = True


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "home"
    if mode == "fonts":
        fonts()
    else:
        args = sys.argv[2:]
        home(float(args[0]) if args else 120, *(int(a) for a in args[1:3]))
