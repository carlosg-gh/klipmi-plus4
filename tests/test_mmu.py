# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from klipmi.features import mmu, mmu_plus4  # noqa: E402

HERE = os.path.dirname(__file__)


def fixture(name="mmu-idle-bunnybox.json") -> dict:
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)["result"]["status"]


class DetectTest(unittest.TestCase):
    def test_detect(self):
        self.assertTrue(mmu.detect(["extruder", "mmu", "mmu_machine"]))
        self.assertTrue(mmu.detect(["mmu_machine"]))
        self.assertFalse(mmu.detect(["extruder", "heater_bed"]))

    def test_resolve_without_mmu_subscribes_nothing(self):
        async def query(_):
            raise AssertionError("must not query")

        self.assertEqual(asyncio.run(mmu.resolveObjects(["extruder"], query)), {})

    def test_resolve_adds_box_climate_objects(self):
        status = fixture()

        async def query(objects):
            return {"mmu_machine": status["mmu_machine"]}

        available = ["mmu", "mmu_machine", "heater_generic box1_heater", "temperature_sensor box1_env"]
        got = asyncio.run(mmu.resolveObjects(available, query))
        self.assertEqual(
            set(got), {"mmu", "mmu_machine", "heater_generic box1_heater", "temperature_sensor box1_env"}
        )

    def test_resolve_skips_objects_klipper_lacks(self):
        status = fixture()

        async def query(objects):
            return {"mmu_machine": status["mmu_machine"]}

        got = asyncio.run(mmu.resolveObjects(["mmu", "mmu_machine"], query))
        self.assertEqual(set(got), {"mmu", "mmu_machine"})


class ParseTest(unittest.TestCase):
    def test_no_mmu(self):
        self.assertIsNone(mmu.parse({"extruder": {}}))

    def test_bunnybox_idle(self):
        box = mmu.parse(fixture())
        self.assertTrue(box.enabled)
        self.assertEqual([s.status for s in box.slots], [2, 1, 1, 1])
        self.assertTrue(all(s.available for s in box.slots))
        self.assertEqual((box.gate, box.tool), (0, 0))
        self.assertEqual(box.filament, "Unloaded")
        self.assertFalse(box.busy)
        self.assertFalse(box.errored)
        self.assertEqual(box.target, 50.0)
        status = fixture()
        self.assertEqual(box.temperature, status["temperature_sensor box1_env"]["temperature"])  # air, not heater plate
        self.assertIsNone(box.humidity)  # the sensor in this sample reports none
        self.assertTrue(box.heating)
        self.assertTrue(box.drying)

    def test_temperature_is_box_air_not_heater_plate(self):
        status = {
            "mmu": {"num_gates": 4},
            "mmu_machine": {"unit_0": {"environment_sensor": "s", "filament_heater": "h"}},
            "s": {"temperature": 31.0, "humidity": 12.4},
            "h": {"temperature": 80.0, "target": 45.0},
        }
        box = mmu.parse(status)
        self.assertEqual((box.temperature, box.target, box.humidity), (31.0, 45.0, 12.4))

    def test_short_arrays_do_not_crash(self):
        box = mmu.parse({"mmu": {"num_gates": 4, "gate_status": [1]}})
        self.assertEqual([s.status for s in box.slots], [1, -1, -1, -1])

    def test_pause_locked_is_an_error(self):
        box = mmu.parse({"mmu": {"num_gates": 4, "print_state": "pause_locked", "reason_for_pause": "x"}})
        self.assertTrue(box.errored)


class ColorTest(unittest.TestCase):
    def test_rgb565(self):
        self.assertEqual(mmu.rgb565("ff0000"), 0xF800)
        self.assertEqual(mmu.rgb565("#00ff00"), 0x07E0)
        self.assertEqual(mmu.rgb565("0000ffff"), 0x001F)

    def test_bad_values_fall_back_to_white(self):
        for bad in ("", "red", "zzzzzz", None):
            self.assertEqual(mmu.rgb565(bad), mmu.DEFAULT_COLOR)


class GcodeTest(unittest.TestCase):
    def setUp(self):
        self.box = mmu.parse(fixture())

    def test_load_needs_a_selected_gate(self):
        self.assertIsNone(mmu.gcode(mmu.LOAD, mmu.UNKNOWN, self.box))
        self.assertEqual(mmu.gcode(mmu.LOAD, 2, self.box), "MMU_CHANGE_TOOL GATE=2 STANDALONE=1")

    def test_unload_selects_a_different_gate_first(self):
        self.assertEqual(mmu.gcode(mmu.UNLOAD, 0, self.box), "MMU_UNLOAD")  # gate 0 is current
        self.assertEqual(mmu.gcode(mmu.UNLOAD, 3, self.box), "MMU_SELECT GATE=3\nMMU_UNLOAD")
        self.assertEqual(mmu.gcode(mmu.UNLOAD, mmu.BYPASS, self.box), "MMU_UNLOAD")

    def test_eject(self):
        self.assertEqual(mmu.gcode(mmu.EJECT, 1, self.box), "MMU_EJECT GATE=1")
        self.assertIsNone(mmu.gcode(mmu.EJECT, mmu.BYPASS, self.box))

    def test_unknown_touch(self):
        self.assertIsNone(mmu.gcode(99, 0, self.box))


class RenderTest(unittest.TestCase):
    def test_idle_box(self):
        box = mmu.parse(fixture())
        box.slots[1].color = "ff0000"
        cmds = mmu_plus4.render(box, selected=1)
        self.assertIn("vis p6,0", cmds)
        self.assertIn("vis p7,1", cmds)  # gate 1 -> second slot
        self.assertIn("vis t6,1", cmds)
        self.assertIn("t6.bco=%d" % 0xF800, cmds)
        self.assertIn("t5.bco=%d" % mmu_plus4.UNKNOWN_COLOR, cmds)  # no colour known: grey
        self.assertIn('t5.txt=""', cmds)
        self.assertIn('t17.txt="%d"' % round(box.temperature), cmds)
        self.assertIn('t18.txt="50"', cmds)
        self.assertIn('t26.txt="--"', cmds)
        self.assertIn("t16.pic=367", cmds)
        self.assertFalse([c for c in cmds if c.startswith("t3.txt")])

    def test_external_holder_is_left_alone(self):
        cmds = mmu_plus4.render(mmu.parse(fixture()), selected=mmu.BYPASS)
        self.assertIn("vis p5,1", cmds)
        self.assertFalse([c for c in cmds if c.startswith(("t1.", "vis t1,"))])

    def test_empty_and_unknown_gates(self):
        box = mmu.parse({"mmu": {"num_gates": 4, "gate_status": [0, -1, 1, 1]}})
        cmds = mmu_plus4.render(box, selected=mmu.UNKNOWN)
        self.assertIn("vis t5,0", cmds)  # empty gate: no spool drawn
        self.assertIn("vis t6,1", cmds)
        self.assertIn('t6.txt="?"', cmds)

    def test_busy_and_error_text(self):
        busy = mmu.parse({"mmu": {"num_gates": 4, "action": "Loading"}})
        self.assertIn('t3.txt="Loading"', mmu_plus4.render(busy, mmu.UNKNOWN))
        err = mmu.parse({"mmu": {"num_gates": 4, "print_state": "pause_locked", "reason_for_pause": 'a "b"'}})
        self.assertIn("t3.txt=\"a 'b'\"", mmu_plus4.render(err, mmu.UNKNOWN))


if __name__ == "__main__":
    unittest.main()
