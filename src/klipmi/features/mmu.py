# SPDX-License-Identifier: GPL-3.0-or-later
"""
Happy Hare / Bunny-Box support, kept free of display and Moonraker code so it
can be tested on its own. Field meanings follow Happy Hare 3.42 (the Bunny-Box
fork); newer versions only add fields, so everything is read with defaults.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

GATE_UNKNOWN = -1
GATE_EMPTY = 0
GATE_AVAILABLE = 1
GATE_BUFFER = 2  # available from buffer

BYPASS = -2
UNKNOWN = -1

DEFAULT_COLOR = 65535  # RGB565 white, the HMI's default text colour


def detect(available: Iterable[str]) -> bool:
    """Happy Hare is configured if Klipper has an `mmu` or `mmu_machine` object."""
    names = set(available)
    return "mmu" in names or "mmu_machine" in names


async def resolveObjects(available: List[str], query) -> Dict[str, Optional[List[str]]]:
    """The MMU objects to subscribe to, including the box heater and sensor that
    `mmu_machine` names (empty when Happy Hare is not configured)."""
    if not detect(available):
        return {}

    objects: Dict[str, Optional[List[str]]] = {"mmu": None, "mmu_machine": None}
    try:
        machine = (await query({"mmu_machine": None})).get("mmu_machine", {})
    except Exception:
        machine = {}

    for unit in _units(machine):
        for key in ("environment_sensor", "filament_heater"):
            name = unit.get(key)
            if name and name in available:
                objects[name] = None
    return objects


def _units(machine: dict) -> List[dict]:
    return [v for k, v in sorted(machine.items()) if k.startswith("unit_") and isinstance(v, dict)]


def rgb565(color: str) -> int:
    """Happy Hare colours are `RRGGBB` or `RRGGBBAA` hex (no `#`) or a colour name."""
    color = (color or "").lstrip("#")
    if len(color) in (6, 8):
        try:
            r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return DEFAULT_COLOR
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    return DEFAULT_COLOR


@dataclass
class Slot:
    index: int
    status: int = GATE_UNKNOWN
    color: str = ""
    material: str = ""
    name: str = ""

    @property
    def available(self) -> bool:
        return self.status in (GATE_AVAILABLE, GATE_BUFFER)


@dataclass
class Box:
    """State of the MMU as the screen shows it."""

    enabled: bool = False
    gate: int = UNKNOWN
    tool: int = UNKNOWN
    filament: str = "Unknown"
    filamentPos: int = UNKNOWN
    action: str = "Idle"
    printState: str = ""
    reason: str = ""
    slots: List[Slot] = field(default_factory=list)
    temperature: Optional[float] = None
    target: Optional[float] = None
    humidity: Optional[float] = None
    drying: bool = False

    @property
    def busy(self) -> bool:
        return self.action not in ("Idle", "Unknown", "")

    @property
    def errored(self) -> bool:
        return self.printState == "pause_locked"

    @property
    def heating(self) -> bool:
        return self.target is not None and self.temperature is not None and self.target > self.temperature


def parse(status: dict) -> Optional[Box]:
    """Build a Box from the subscribed status, or None when Happy Hare is absent."""
    mmu = status.get("mmu")
    if not isinstance(mmu, dict):
        return None

    count = int(mmu.get("num_gates", 0) or 0)

    def per_gate(key: str, i: int, default):
        values = mmu.get(key) or []
        return values[i] if i < len(values) else default

    box = Box(
        enabled=bool(mmu.get("enabled", False)),
        gate=int(mmu.get("gate", UNKNOWN)),
        tool=int(mmu.get("tool", UNKNOWN)),
        filament=str(mmu.get("filament", "Unknown")),
        filamentPos=int(mmu.get("filament_pos", UNKNOWN)),
        action=str(mmu.get("action", "Idle")),
        printState=str(mmu.get("print_state", "")),
        reason=str(mmu.get("reason_for_pause", "")),
        drying=any(s == "active" for s in (mmu.get("drying_state") or [])),
        slots=[
            Slot(
                index=i,
                status=int(per_gate("gate_status", i, GATE_UNKNOWN)),
                color=str(per_gate("gate_color", i, "")),
                material=str(per_gate("gate_material", i, "")),
                name=str(per_gate("gate_filament_name", i, "")),
            )
            for i in range(count)
        ],
    )

    for unit in _units(status.get("mmu_machine", {})):
        sensor = status.get(unit.get("environment_sensor") or "", {})
        heater = status.get(unit.get("filament_heater") or "", {})
        box.temperature = sensor.get("temperature", heater.get("temperature"))  # air, not the heater plate
        box.target = heater.get("target")
        box.humidity = sensor.get("humidity")
        break  # the stock pages show one box
    return box


# --- Touch ids sent by the stock one_box_page (0x65 <page> <id>) -------------
EXIT = 1
EJECT = 2  # stock "uninstall"
LOAD = 3
UNLOAD = 4  # stock "retract"
COLUMNS = {10: BYPASS, 11: 0, 12: 1, 13: 2, 14: 3}  # column touch areas -> gate


def gcode(touch: int, selected: int, box: Box) -> Optional[str]:
    """G-code for a button on the box page; None if it needs no command.

    `selected` is the column the user last touched (a gate index, or BYPASS).
    Load/unload/eject need a gate; the bypass column only supports unload.
    """
    if touch == LOAD and selected >= 0:
        return "MMU_CHANGE_TOOL GATE=%d STANDALONE=1" % selected
    if touch == UNLOAD:
        if selected >= 0 and selected != box.gate:
            return "MMU_SELECT GATE=%d\nMMU_UNLOAD" % selected
        return "MMU_UNLOAD"
    if touch == EJECT and selected >= 0:
        return "MMU_EJECT GATE=%d" % selected
    return None
