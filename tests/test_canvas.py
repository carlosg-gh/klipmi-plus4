# SPDX-License-Identifier: GPL-3.0-or-later
"""Canvas diffing and page interactions, rendered against a fake display and printer.

Needs the runtime dependencies (nextion, pyserial); run it where klipmi runs.
"""

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

from klipmi.canvas.gfx import Canvas, Rect, fill, rounded  # noqa: E402
from klipmi.canvas import widgets as ui  # noqa: E402


class CanvasTest(unittest.TestCase):
    def test_unchanged_frame_sends_nothing(self):
        out = []
        c = Canvas(out.append)
        for _ in range(2):
            c.begin()
            ui.card(c, "a", Rect(0, 0, 100, 50))
            ui.label(c, "a/t", Rect(10, 10, 80, 20), "hello")
            c.end()
        self.assertEqual(len(out), len(rounded(Rect(0, 0, 100, 50), 0, 14)) + 1)

    def test_parent_redraw_redraws_children(self):
        out = []
        c = Canvas(out.append)
        for color in (1, 2):
            c.begin()
            c.op("p", [fill(Rect(0, 0, 10, 10), color)])
            c.op("p/child", ["child"])
            c.end()
        self.assertEqual(out.count("child"), 2)

    def test_vanished_part_is_erased_before_new_draws(self):
        out = []
        c = Canvas(out.append)
        c.begin()
        c.op("x", ["draw x"], ["erase x"])
        c.end()
        c.begin()
        c.op("y", ["draw y"])
        c.end()
        self.assertEqual(out[-2:], ["erase x", "draw y"])

    def test_pressed_button_hit(self):
        c = Canvas(lambda cmd: None)
        hits = []
        c.begin()
        ui.button(c, "b", Rect(10, 10, 100, 40), "Go", lambda: hits.append(1))
        c.end()
        self.assertEqual(c.find(20, 20).key, "b")
        self.assertIsNone(c.find(200, 200))




class AppTest(unittest.TestCase):
    def setUp(self):
        import preview
        from klipmi.ui.plus4canvas import box, home, motion

        self.box, self.home, self.motion = box, home, motion
        self.out = []
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        fixture = os.path.join(HERE, "fixtures", "mmu-idle-bunnybox.json")
        self.app, self.printer, self.status = preview.make_app(self.out.append, fixture)

    def tearDown(self):
        self.loop.close()

    def press(self, x, y):
        self.app.touch(x, y, True)
        self.app.touch(x, y, False)
        self.loop.run_until_complete(asyncio.sleep(0))
        self.app.render()

    def tap(self, key):
        self.app.render()
        hit = next(h for h in self.app.canvas.hits if h.key == key)
        self.press(hit.rect.x + hit.rect.w // 2, hit.rect.y + hit.rect.h // 2)

    def test_gate_sheet_loads_gate(self):
        self.app.go_nav("filament")
        self.tap("fl/d/g1")
        self.assertIsInstance(self.app.modal, self.box.GateSheet)
        self.tap("modal/load")
        self.assertEqual(self.printer.sent[-1], "MMU_CHANGE_TOOL GATE=1 STANDALONE=1")

    def test_gate_sheet_saves_colour(self):
        self.app.open_modal(self.box.GateSheet(self.app, 1))
        self.tap("modal/c3")  # red
        self.tap("modal/save")
        self.assertEqual(self.printer.sent[-1], "MMU_GATE_MAP GATE=1 MATERIAL=PETG COLOR=e53935 QUIET=1")

    def test_keypad_sets_nozzle_target(self):
        self.app.go_nav("home")
        self.tap("home/h/extruder")
        for key in ("modal/k1", "modal/k8", "modal/k0", "modal/ok"):
            self.tap(key)
        self.assertEqual(self.printer.sent[-1], "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=180")
        self.assertIsNone(self.app.modal)

    def test_keypad_rejects_out_of_range(self):
        self.app.go_nav("home")
        self.tap("home/h/extruder")
        for key in ("modal/k9", "modal/k9", "modal/k9", "modal/ok"):
            self.tap(key)
        self.assertIsNotNone(self.app.modal)
        self.assertEqual(self.printer.sent, [])

    def test_rail_closes_sheet_and_navigates(self):
        self.app.go_nav("home")
        self.tap("home/h/extruder")
        self.tap("nav/move")
        self.assertIsNone(self.app.modal)
        self.assertIsInstance(self.app.page, self.motion.MovePage)

    def test_slider_sets_fan_where_touched(self):
        self.app.go_nav("fans")
        self.app.render()
        hit = next(h for h in self.app.canvas.hits if h.key == "fn/0/s")
        self.press(hit.rect.x + hit.rect.w // 2, hit.rect.y + 10)
        self.assertEqual(self.printer.sent[-1], "M106 S128")

    def test_home_shows_printing_page_while_printing(self):
        self.status["print_stats"] = {"state": "printing", "filename": "x.gcode", "print_duration": 10, "info": {}}
        self.app.go_nav("home")
        self.assertIsInstance(self.app.page, self.home.PrintingPage)

    def test_wake_touch_is_swallowed(self):
        self.app.go_nav("home")
        self.app.sleeping = True
        self.press(36, 450)  # over the stop button
        self.assertIsNone(self.app.modal)

    def test_filament_hidden_without_mmu(self):
        del self.app.status["mmu"]
        self.app.available = [k for k in self.app.available if k != "mmu"]
        self.app.go_nav("home")
        self.app.render()
        self.assertNotIn("nav/filament", [h.key for h in self.app.canvas.hits])


if __name__ == "__main__":
    unittest.main()
