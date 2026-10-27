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
         4: ("SemiBold", 48), 5: ("SemiBold", 96),
         6: ("Light", 16), 7: ("Light", 20), 8: ("Light", 24), 9: ("Light", 32),
         10: ("SemiBold", 16), 11: ("SemiBold", 20), 12: ("SemiBold", 24), 13: ("SemiBold", 32)}
PIC_DIRS = (os.path.join(HMI, "assets", "pics"), os.path.expanduser("~/klipmi/hmi/assets"))
def _manifest():
    for d in PIC_DIRS:
        if os.path.exists(os.path.join(d, "pics.json")):
            with open(os.path.join(d, "pics.json"), encoding="utf-8") as f:
                return json.load(f)["order"]
    return []


PIC_FILES = _manifest()
TO565 = [(v >> 3) * 255 // 31 for v in range(256)] + [(v >> 2) * 255 // 63 for v in range(256)] + \
        [(v >> 3) * 255 // 31 for v in range(256)]  # the editor stores pictures as RGB565, like every colour


def load_font(style, px):
    for path in (os.path.join(HMI, "assets", "inter", "extras", "ttf", "Inter-%s.ttf" % style),
                 os.path.expanduser("~/klipmi/hmi/assets/Inter-%s.ttf" % style),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def load_pic(pid):
    for base in PIC_DIRS:
        path = os.path.join(base, PIC_FILES[pid] + ".png")
        if os.path.exists(path):
            return Image.open(path).convert("RGB").point(TO565)
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
        elif cmd.startswith("cir "):
            x, y, r, c = map(int, cmd[4:].split(","))
            self.d.ellipse([x - r, y - r, x + r, y + r], outline=unrgb(c))
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




FILES = [
    {"filename": "benchy_PETG_0.2mm.gcode", "modified": 1793100000, "size": 4200000,
     "estimated_time": 6120, "filament_weight_total": 9.4, "thumbnails": [{"width": 96, "relative_path": ".thumbs/a.png"}]},
    {"filename": "calibration_cube_20mm_PLA_0.2mm.gcode", "modified": 1793000000, "size": 1800000,
     "estimated_time": 1320, "filament_weight_total": 6.1, "thumbnails": [{"width": 96, "relative_path": ".thumbs/b.png"}]},
    {"filename": "spiral_vase_PLA_0.28mm.gcode", "modified": 1792900000, "size": 9100000,
     "estimated_time": 11100, "filament_weight_total": 41, "thumbnails": [{"width": 96, "relative_path": ".thumbs/c.png"}]},
    {"filename": "phone_stand_long_name_that_does_not_fit_on_one_line_at_all.gcode", "modified": 1792700000,
     "size": 6600000, "estimated_time": 15480, "filament_weight_total": 58},
    {"filename": "spool_holder.gcode", "modified": 1792600000, "size": 3300000},
]


def fake_history(target, start, ramp_at):
    out = []
    for i in range(1200):
        t = i - (1200 - 600)
        v = start if t < ramp_at else min(target, start + (target - start) * (1 - 0.985 ** (t - ramp_at)) * 1.05)
        out.append(round(v, 1))
    return out


class FakeClient:
    def __init__(self):
        self.files = FILES

    async def call_method(self, method, **params):
        if method == "server.files.get_directory":
            if params.get("path", "gcodes") == "gcodes":
                return {"dirs": [{"dirname": "calibration", "modified": 1793050000, "size": 0}], "files": self.files}
            return {"dirs": [], "files": self.files[1:2]}
        if method == "server.files.metadata":
            return {"estimated_time": 6120, "filament_total": 3100, "layer_height": 0.2, "layer_count": 240,
                    "filament_type": "[\"PETG\"]", "slicer": "OrcaSlicer", "filament_weight_total": 9.4,
                    "modified": 1793100000, "thumbnails": [{"width": 96, "height": 96, "relative_path": ".thumbs/x-96x96.png"}]}
        if method == "printer.info":
            return {"state": "ready", "software_version": "v0.13.0-656-g4cc47cf5-dirty", "state_message": "Printer is ready",
                    "hostname": "mkspi"}
        if method == "server.info":
            return {"moonraker_version": "v0.9.3-41-gabc"}
        if method == "server.temperature_store":
            return {"extruder": {"temperatures": fake_history(214.6, 28, 120)},
                    "heater_bed": {"temperatures": fake_history(59.8, 24, 40)},
                    "heater_generic chamber": {"temperatures": fake_history(31.2, 25, 60)}}
        if method == "printer.objects.query":
            return {"status": {"configfile": {"settings": {
                "input_shaper": {"shaper_type_x": "mzv", "shaper_freq_x": 52.4, "shaper_freq_y": 48.1},
                "cartographer": {"z_offset": -0.025}}}}}
        return {}


class FakePrinter:
    def __init__(self):
        self.client = FakeClient()
        self.sent = []

    def runGcode(self, g):
        self.sent.append(g)

    def startPrint(self, f):
        self.sent.append("PRINT " + f)


def fake_mesh(n=20):
    import math
    return [[round(-0.08 + 0.19 * (0.55 * x / (n - 1) + 0.45 * y / (n - 1)) + 0.012 * math.sin(x * 0.9) * math.cos(y * 0.7), 4)
             for x in range(n)] for y in range(n)]


def base_status(path):
    status = {}
    if path:
        with open(path, encoding="utf-8") as f:
            status = json.load(f)["result"]["status"]
    status.update({
        "webhooks": {"state": "ready"},
        "extruder": {"temperature": 182.4, "target": 215.0},
        "heater_bed": {"temperature": 59.8, "target": 60.0},
        "heater_generic chamber": {"temperature": 31.2, "target": 0.0},
        "print_stats": {"state": "standby", "filename": "", "print_duration": 0, "info": {}},
        "display_status": {"progress": 0.0, "message": ""},
        "gcode_move": {"speed_factor": 1.0, "extrude_factor": 0.98, "homing_origin": [0, 0, 0.02, 0]},
        "toolhead": {"homed_axes": "xy", "position": [125.0, 110.0, 12.4, 0]},
        "fan": {"speed": 0.4},
        "fan_generic sidefan": {"speed": 0.0},
        "fan_generic filterfan": {"speed": 1.0},
        "heater_fan hotend_fan": {"speed": 1.0},
        "heater_fan chamber_heater_fan": {"speed": 0.0},
        "temperature_fan Mainboard_fan": {"speed": 0.32},
        "output_pin caselight": {"value": 1.0},
        "exclude_object": {"objects": [{"name": "benchy_1"}, {"name": "benchy_2"}], "excluded_objects": []},
        "manual_probe": {"is_active": False, "z_position": None},
        "bed_mesh": {"profile_name": "", "probed_matrix": [[]], "profiles": {"default": {"points": fake_mesh()}}},
    })
    if "mmu" in status:
        mm = status["mmu"]
        mm["num_gates"] = 4
        mm["gate_status"] = [1, 1, 1, 0]
        mm["gate_color"] = ["ffffff", "e53935", "1a1a1a", ""]
        mm["gate_material"] = ["PLA", "PETG", "PLA", ""]
        mm["filament"] = "Loaded"
        mm["gate"] = 1
        mm["filament_pos"] = 10
        mm["tool"] = 1
        mm["action"] = "Idle"
        mm["enabled"] = True
        mm["sensors"] = {"mmu_pre_gate_0": True, "mmu_pre_gate_1": True, "mmu_pre_gate_2": True, "mmu_pre_gate_3": False,
                         "mmu_gate": True, "extruder": True}
        mm["ttg_map"] = [0, 1, 2, 3]
        mm["flowguard"] = {"trigger": "", "level": 0.12, "enabled": True}
        mm["endless_spool_enabled"] = 1
        mm["num_toolchanges"] = 12
        status.setdefault("aht10 box1_env", {"humidity": 38})
    return status


def make_app(sink, status_path):
    from klipmi.canvas.app import App
    from klipmi.ui.plus4canvas import NAV, PAGES, home, system

    printer = FakePrinter()
    app = App(sink, printer, settings_path=os.devnull, nav=NAV)
    status = base_status(status_path)
    app.available = list(status)
    app.status = status
    app.klippy = "ready"
    for nav_id, page in PAGES.items():
        app.register(nav_id, page)
    app.printing_page = home.PrintingPage
    app.offline_page = system.OfflinePage(app)
    app.on_estop = lambda: None
    return app, printer, status


async def device_demo(status_path):
    """Draw the pages on the real display and time how long each takes to appear."""
    import time

    from klipmi.canvas.link import SerialLink
    from klipmi.ui.plus4canvas import PAGES, home

    link = SerialLink("/dev/ttyS1", page="canvas")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, link.open)
    link.start(loop)
    app, printer, status = make_app(link.write, status_path)

    async def show(name, pause=5):
        await asyncio.sleep(0.3)
        start = time.time()
        app.render()
        while not link.outbox.empty():
            await asyncio.sleep(0.005)
        await loop.run_in_executor(None, link._sync)
        print("%-16s on the glass after %5.0f ms" % (name, (time.time() - start) * 1000), flush=True)
        await asyncio.sleep(pause)

    for nav_id in PAGES:
        app.go_nav(nav_id)
        await show(nav_id)
    status["print_stats"] = {"state": "printing", "filename": "benchy_PETG_0.2mm.gcode", "print_duration": 4320,
                             "info": {"current_layer": 87, "total_layer": 210}}
    status["display_status"] = {"progress": 0.42, "message": ""}
    app.go(home.PrintingPage)
    await show("printing", 8)
    link.running = False


async def main(out, status_path):
    import io
    import urllib.request

    from klipmi.ui.plus4canvas import NAV, PAGES, box, dialogs, files, home, system, wifi

    os.makedirs(out, exist_ok=True)
    glass = Glass()
    app, printer, status = make_app(glass, status_path)

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    art = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(art)
    d.polygon([(30, 190), (270, 190), (237, 250), (66, 250)], fill=(200, 52, 46))
    d.rectangle([93, 120, 192, 190], fill=(232, 64, 58))
    d.rectangle([108, 135, 135, 160], fill=(60, 30, 30))
    d.rectangle([150, 135, 177, 160], fill=(60, 30, 30))
    d.rectangle([84, 105, 201, 120], fill=(200, 52, 46))
    d.rectangle([180, 45, 204, 108], fill=(200, 52, 46))
    buf = io.BytesIO()
    art.save(buf, "PNG")
    urllib.request.urlopen = lambda url, timeout=0: FakeResp(buf.getvalue())

    async def fake_scan(rescan=True):
        return [wifi.Network("HomeNet", 100, True, True, True), wifi.Network("HomeNet_2GHz", 92, True, False, True),
                wifi.Network("Neighbour-5G", 61, True), wifi.Network("Guest open", 44, False),
                wifi.Network("Cafe WiFi", 31, True), wifi.Network("Office_2G", 18, True)]

    async def fake_status():
        return "HomeNet", 100, "192.168.1.50"

    wifi.scan, wifi.status = fake_scan, fake_status
    system.local_ip = lambda: "192.168.1.50"

    async def shot(name, settle=0.2):
        for _ in range(3):  # spawned loads finish, then the frame that shows them
            await asyncio.sleep(settle)
            app.render()
        before = glass.count
        app.canvas.shown.clear()
        app.repaint = True
        app.render()
        glass.img.save(os.path.join(out, name + ".png"))
        print("%-22s %4d commands (full frame)" % (name, glass.count - before))

    for i, nav_id in enumerate(PAGES):
        app.go_nav(nav_id)
        await shot("%02d-%s" % (i + 1, nav_id))
    app.open_modal(dialogs.Keypad(app, "Nozzle", 215, 0, 300, lambda v: None, unit="C", icon_name="nozzle", current=182.4,
                                  presets=[("PLA", 210), ("PETG", 240), ("ABS", 250), ("TPU", 250)], nav="temp"))
    await shot("10-keypad")
    app.close_modal()
    app.go_nav("filament")
    app.open_modal(box.GateSheet(app, 1))
    status.setdefault("mmu_machine", {})
    await shot("11-gate")
    app.close_modal()
    app.go(files.FilePage(app, "benchy_PETG_0.2mm.gcode"))
    await shot("12-file", 0.4)
    app.go_nav("system")
    app.open_modal(system.WifiSheet(app))
    await shot("13-wifi")
    app.close_modal()
    app.open_modal(dialogs.TextEntry(app, "Password for Neighbour-5G", lambda s: None, secret=True, ok="Connect", initial="hunter22"))
    await shot("14-keyboard")
    app.close_modal()
    app.open_modal(system.About(app))
    await shot("15-about")
    app.close_modal()
    app.open_modal(dialogs.Confirm(app, "Cancel print", "Stop this print? It cannot be resumed.", "Cancel print", lambda: None))
    await shot("16-confirm")
    app.close_modal()
    status["print_stats"] = {"state": "printing", "filename": "benchy_PETG_0.2mm.gcode", "print_duration": 4320,
                             "info": {"current_layer": 87, "total_layer": 210}}
    status["display_status"] = {"progress": 0.42, "message": ""}
    app.go_nav("home")
    await shot("17-printing", 0.4)
    app.open_modal(home.Tune(app))
    await shot("18-tune")
    app.close_modal()
    status["manual_probe"] = {"is_active": True, "z_position": 0.142}
    app.open_modal(dialogs.ManualProbe(app))
    await shot("19-probe")
    app.close_modal()
    status["manual_probe"] = {"is_active": False}
    if "mmu" in status:
        status["mmu"]["print_state"] = "pause_locked"
        status["mmu"]["reason_for_pause"] = "Failed to load gate 2: no filament detected at the extruder"
        app.go_nav("filament")
        await shot("20-filament-error")
        status["mmu"]["print_state"] = "initialized"
    status["print_stats"] = {"state": "standby"}
    app.klippy = "error"
    app.klippy_message = "MCU 'mmu' shutdown: Timer too close. Once the underlying issue is corrected, use the FIRMWARE_RESTART command."
    app.go_nav("home")
    await shot("21-offline")
    print("gcode sent:", printer.sent)


if __name__ == "__main__":
    if sys.argv[1] == "--device":
        asyncio.run(device_demo(sys.argv[2] if len(sys.argv) > 2 else ""))
    else:
        asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
