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
        from klipmi.canvas.app import App
        from klipmi.ui.plus4canvas import box, pages

        self.preview, self.pages, self.box = preview, pages, box
        self.out = []
        self.printer = preview.FakePrinter()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.app = App(self.out.append, self.printer, settings_path=os.devnull, nav=[
            ("home", "Home", lambda a: True), ("box", "Box", lambda a: a.has("mmu"))])
        fixture = os.path.join(HERE, "fixtures", "mmu-idle-bunnybox.json")
        self.app.status = preview.base_status(fixture)
        self.app.available = list(self.app.status)
        self.app.klippy = "ready"
        self.app.register("home", pages.HomePage)
        self.app.register("box", box.BoxPage)
        self.app.register("files", pages.FilesPage)

    def tearDown(self):
        self.loop.close()

    def tap(self, key):
        self.app.render()
        hit = next(h for h in self.app.canvas.hits if h.key == key)
        x, y = hit.rect.x + 2, hit.rect.y + 2
        self.app.touch(x, y, True)
        self.app.touch(x, y, False)
        self.loop.run_until_complete(asyncio.sleep(0))
        self.app.render()

    def test_box_load_selected_gate(self):
        self.app.go(self.box.BoxPage)
        self.app.status["mmu"]["filament"] = "Unloaded"
        self.tap("box/s1")
        self.tap("box/act/load")
        self.assertEqual(self.printer.sent[-1], "MMU_CHANGE_TOOL GATE=1 STANDALONE=1")

    def test_second_tap_opens_slot_editor_and_saves(self):
        self.app.go(self.box.BoxPage)
        self.tap("box/s1")
        self.tap("box/s1")
        self.assertIsInstance(self.app.modal, self.box.SlotEditor)
        self.tap("modal/c3")  # red
        self.tap("modal/save")
        self.assertEqual(self.printer.sent[-1], "MMU_GATE_MAP GATE=1 MATERIAL=PETG COLOR=e53935 QUIET=1")
        self.assertIsNone(self.app.modal)

    def test_keypad_sets_nozzle_target(self):
        self.app.go(self.pages.HomePage)
        self.tap("home/h/extruder")
        for key in ("modal/k21", "modal/k08", "modal/k30"):  # 1, 8, 0
            self.tap(key)
        self.tap("modal/ok")
        self.assertEqual(self.printer.sent[-1], "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=180")

    def test_keypad_rejects_out_of_range(self):
        self.app.go(self.pages.HomePage)
        self.tap("home/h/extruder")
        for key in ("modal/k09", "modal/k09", "modal/k09"):
            self.tap(key)
        self.tap("modal/ok")
        self.assertIsNotNone(self.app.modal)
        self.assertEqual(self.printer.sent, [])

    def test_wake_touch_is_swallowed(self):
        self.app.go(self.pages.HomePage)
        self.app.sleeping = True
        self.app.touch(700, 340, True)  # over STOP
        self.app.touch(700, 340, False)
        self.app.render()
        self.assertIsNone(self.app.modal)
        self.assertIn("dim=100", self.out)

    def test_box_hidden_without_mmu(self):
        del self.app.status["mmu"]
        self.app.available = [k for k in self.app.available if k != "mmu"]
        self.app.go(self.pages.HomePage)
        self.app.render()
        keys = [h.key for h in self.app.canvas.hits]
        self.assertNotIn("nav/box", keys)
        self.assertNotIn("home/q/box", [k for k in keys if self.app.has("mmu")])


if __name__ == "__main__":
    unittest.main()
