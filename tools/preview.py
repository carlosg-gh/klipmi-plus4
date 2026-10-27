#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the canvas UI to PNG files without a display, from a recorded printer status.

    preview.py OUTDIR [status.json]
    preview.py --device [status.json]     draw pages on the real display (needs the serial port to itself)

Interprets the TJC drawing commands (fill, xstr, xpic, cirs, line) with Pillow, using the
plus4-canvas.tft assets (Inter fonts, the PNGs the pictures were built from), so the
pictures show what the display would draw (the font rasteriser differs slightly).
"""

import asyncio
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from klipmi.canvas.app import App  # noqa: E402
from klipmi.canvas.gfx import unrgb  # noqa: E402

HMI = os.path.join(os.path.dirname(__file__), "..", "hmi", "plus4-canvas")
FONTS = {0: ("Regular", 16), 1: ("Regular", 20), 2: ("Regular", 24), 3: ("Regular", 32),
         4: ("SemiBold", 48), 5: ("SemiBold", 96)}
PIC_FILES = ([f"ic{n}_{bg}" for n in (24, 32) for bg in ("bg", "surface", "surface2", "raised", "accent", "accent_dim")]
             + ["cr_surface_bg", "cr_surface2_surface", "cr_raised_surface", "cr_surface2_bg", "cr_raised_bg",
                "cr_accent_bg", "cr_accent_surface", "cr_accent_dim_surface", "cr_err_dim_surface", "cr_bg_surface"])


def load_font(style, px):
    for path in (os.path.join(HMI, "assets", "inter", "extras", "ttf", "Inter-%s.ttf" % style),
                 os.path.expanduser("~/klipmi/hmi/assets/Inter-%s.ttf" % style),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def load_pic(pid):
    for base in (os.path.join(HMI, "assets", "pics"), os.path.expanduser("~/klipmi/hmi/assets")):
        path = os.path.join(base, PIC_FILES[pid] + ".png")
        if os.path.exists(path):
            return Image.open(path).convert("RGB")
    raise FileNotFoundError(PIC_FILES[pid])


class Glass:
    def __init__(self):
        self.img = Image.new("RGB", (800, 480), (0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.fonts = {k: load_font(*v) for k, v in FONTS.items()}
        self.pics = {}
        self.count = 0

    def __call__(self, cmd: str):
        self.count += 1
        if cmd.startswith("fill "):
            x, y, w, h, c = map(int, cmd[5:].split(","))
            if w > 0 and h > 0:
                self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=unrgb(c))
        elif cmd.startswith("cirs "):
            x, y, r, c = map(int, cmd[5:].split(","))
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=unrgb(c))
        elif cmd.startswith("line "):
            x1, y1, x2, y2, c = map(int, cmd[5:].split(","))
            self.d.line([x1, y1, x2, y2], fill=unrgb(c))
        elif cmd.startswith("xstr "):
            m = re.match(r'xstr (\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),"(.*)"$', cmd)
            x, y, w, h, font, fg, bg, xc, yc, sta = map(int, m.groups()[:10])
            s = m.group(11)
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=unrgb(bg))
            f = self.fonts[font]
            tw = int(f.getlength(s))
            ascent, descent = f.getmetrics()
            tx = x if xc == 0 else (x + (w - tw) // 2 if xc == 1 else x + w - tw)
            ty = y + (h - (ascent + descent)) // 2 if yc == 1 else y
            clip = Image.new("RGB", (w, h), unrgb(bg))
            ImageDraw.Draw(clip).text((tx - x, ty - y), s, font=f, fill=unrgb(fg))
            self.img.paste(clip, (x, y))
        elif cmd.startswith("xpic "):
            x, y, w, h, sx, sy, pid = map(int, cmd[5:].split(","))
            if pid not in self.pics:
                self.pics[pid] = load_pic(pid)
            self.img.paste(self.pics[pid].crop((sx, sy, sx + w, sy + h)), (x, y))


class FakeClient:
    def __init__(self, files):
        self.files = files

    async def call_method(self, method, **params):
        if method == "server.files.list":
            return self.files
        if method == "server.files.metadata":
            return {"estimated_time": 9120, "filament_total": 12500, "layer_height": 0.2, "object_height": 42.4,
                    "filament_type": "PLA", "slicer": "OrcaSlicer"}
        if method == "printer.info":
            return {"state": "ready", "software_version": "v0.13.0-656-g4cc47cf5-dirty", "state_message": "Printer is ready"}
        return {}


class FakePrinter:
    def __init__(self):
        self.client = FakeClient([
            {"path": "benchy_PLA_0.2mm.gcode", "modified": 1793100000, "size": 4200000},
            {"path": "calibration/temp_tower_PETG.gcode", "modified": 1793000000, "size": 1800000},
            {"path": "gridfinity_bin_2x3.gcode", "modified": 1792900000, "size": 9100000},
            {"path": "voron_cube.gcode", "modified": 1792800000, "size": 2300000},
            {"path": "phone_stand_long_name_that_does_not_fit_on_one_line_at_all.gcode", "modified": 1792700000, "size": 6600000},
            {"path": "spool_holder.gcode", "modified": 1792600000, "size": 3300000},
        ])
        self.sent = []

    def runGcode(self, g):
        self.sent.append(g)

    def startPrint(self, f):
        self.sent.append("PRINT " + f)


def base_status(path):
    status = {}
    if path:
        with open(path, encoding="utf-8") as f:
            status = json.load(f)["result"]["status"]
    status.update({
        "webhooks": {"state": "ready"},
        "extruder": {"temperature": 214.6, "target": 215.0},
        "heater_bed": {"temperature": 59.8, "target": 60.0},
        "heater_generic chamber": {"temperature": 31.2, "target": 0.0},
        "print_stats": {"state": "standby", "filename": "", "print_duration": 0, "info": {}},
        "display_status": {"progress": 0.0, "message": ""},
        "gcode_move": {"speed_factor": 1.0, "extrude_factor": 1.0, "homing_origin": [0, 0, -0.02, 0]},
        "toolhead": {"homed_axes": "xyz", "position": [152.0, 148.5, 12.4, 0]},
        "fan": {"speed": 0.6},
        "fan_generic sidefan": {"speed": 0.0},
        "fan_generic filterfan": {"speed": 0.3},
        "output_pin caselight": {"value": 1.0},
    })
    if "mmu" in status:
        status["mmu"]["gate_status"] = [2, 1, 0, -1]
        status["mmu"]["gate_color"] = ["e53935", "1e88e5", "", ""]
        status["mmu"]["gate_material"] = ["PLA", "PETG", "", ""]
        status["mmu"]["filament"] = "Loaded"
        status["mmu"]["gate"] = 0
        status["mmu"]["filament_pos"] = 10
        status.setdefault("aht10 box1_env", {"humidity": 28})
    return status


async def device_demo(status_path):
    """Draw a few pages on the real display and time how long each takes to appear."""
    import time

    from klipmi.canvas.link import SerialLink
    from klipmi.ui.plus4canvas import box, pages

    link = SerialLink("/dev/ttyS1", page="canvas")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, link.open)
    link.start(loop)
    printer = FakePrinter()
    app = App(link.write, printer, settings_path=os.devnull, nav=[
        ("home", "Home", lambda a: True), ("control", "Control", lambda a: True), ("files", "Files", lambda a: True),
        ("box", "Box", lambda a: a.has("mmu")), ("system", "System", lambda a: True)])
    status = base_status(status_path)
    app.available = list(status)
    app.status = status
    app.klippy = "ready"
    for nav_id, page in (("home", pages.HomePage), ("control", pages.ControlPage), ("files", pages.FilesPage),
                         ("box", box.BoxPage), ("system", pages.SystemPage)):
        app.register(nav_id, page)

    async def show(name, pause=5):
        await asyncio.sleep(0.05)
        start = time.time()
        app.render()
        while not link.outbox.empty():
            await asyncio.sleep(0.005)
        await loop.run_in_executor(None, link._sync)
        print("%-16s on the glass after %5.0f ms" % (name, (time.time() - start) * 1000), flush=True)
        await asyncio.sleep(pause)

    app.go(pages.HomePage)
    await show("home")
    for nav_id in ("control", "files", "box", "system"):
        app.go_nav(nav_id)
        await show(nav_id)
    status["print_stats"] = {"state": "printing", "filename": "benchy_PLA_0.2mm.gcode", "print_duration": 2410,
                             "info": {"current_layer": 57, "total_layer": 240}}
    status["display_status"] = {"progress": 0.37, "message": ""}
    app.go(pages.PrintingPage)
    await show("printing", 8)
    link.running = False


async def main(out, status_path):
    from klipmi.ui.plus4canvas import box, dialogs, pages

    os.makedirs(out, exist_ok=True)
    glass = Glass()
    printer = FakePrinter()
    app = App(glass, printer, settings_path=os.path.join(out, "settings.json"), nav=[
        ("home", "Home", lambda a: True), ("control", "Control", lambda a: True), ("files", "Files", lambda a: True),
        ("box", "Box", lambda a: a.has("mmu")), ("system", "System", lambda a: True)])
    status = base_status(status_path)
    app.available = list(status)
    app.status = status
    app.klippy = "ready"
    app.offline_page = pages.OfflinePage(app)
    for nav_id, page in (("home", pages.HomePage), ("control", pages.ControlPage), ("files", pages.FilesPage),
                         ("box", box.BoxPage), ("system", pages.SystemPage)):
        app.register(nav_id, page)

    async def shot(name):
        await asyncio.sleep(0.01)  # let spawned loads finish
        before = glass.count
        app.render()
        glass.img.save(os.path.join(out, name + ".png"))
        print("%-22s %4d commands" % (name, glass.count - before))

    app.go(pages.HomePage)
    await shot("01-home")
    before = glass.count
    app.render()
    print("%-22s %4d commands (unchanged frame)" % ("01-home again", glass.count - before))
    for i, nav_id in enumerate(["control", "files", "box", "system"]):
        app.go_nav(nav_id)
        await shot("%02d-%s" % (i + 2, nav_id))
    app.go(pages.ControlPage(app, 1))
    await shot("06-control-temp")
    app.go(pages.ControlPage(app, 2))
    await shot("07-control-fans")
    status["print_stats"] = {"state": "printing", "filename": "benchy_PLA_0.2mm.gcode", "print_duration": 2410,
                             "info": {"current_layer": 57, "total_layer": 240}}
    status["display_status"] = {"progress": 0.37, "message": ""}
    app.go(pages.HomePage)
    await shot("08-home-printing")
    app.go(pages.PrintingPage)
    await shot("09-printing")
    app.open_modal(pages.Tune(app))
    await shot("10-tune")
    app.close_modal()
    app.open_modal(dialogs.Keypad(app, "Nozzle target", 215, 0, 300, lambda v: None, unit="C",
                                  presets=[("PLA", 210), ("PETG", 240), ("ABS", 255), ("Off", 0)]))
    await shot("11-keypad")
    app.close_modal()
    if "mmu" in status:
        app.go_nav("box")
        app.open_modal(box.SlotEditor(app, 1))
        await shot("12-slot-editor")
        app.close_modal()
        status["mmu"]["print_state"] = "pause_locked"
        status["mmu"]["reason_for_pause"] = "Failed to load gate 2: no filament detected at the extruder"
        await shot("13-box-error")
    app.klippy = "error"
    app.klippy_message = "MCU 'mmu' shutdown: Timer too close\nOnce the underlying issue is corrected, use the FIRMWARE_RESTART command."
    app.go(pages.HomePage)
    await shot("14-offline")
    print("gcode sent:", printer.sent)


if __name__ == "__main__":
    if sys.argv[1] == "--device":
        asyncio.run(device_demo(sys.argv[2] if len(sys.argv) > 2 else ""))
    else:
        asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
