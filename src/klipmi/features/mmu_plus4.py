# SPDX-License-Identifier: GPL-3.0-or-later
"""Display commands for the stock `one_box_page` (QIDI Plus 4 HMI), as plain strings. No display dependency, so it is unit-testable."""

from typing import List

from klipmi.features import mmu

# Per column: external holder first, then the box slots 1A..4A
LABELS = ["t1", "t5", "t6", "t13", "t14"]  # state text, "?" by default
FRAMES = ["p5", "p6", "p7", "p8", "p9"]  # selection frame pictures
GATES = [mmu.BYPASS, 0, 1, 2, 3]

HEAT_ICON = {False: 366, True: 367}  # t16.pic, from the HMI's own comment
TEXT_MAX = 3  # the state labels are 57 px wide


def slotText(slot: mmu.Slot) -> str:
    if slot.status == mmu.GATE_UNKNOWN:
        return "?"
    if slot.status == mmu.GATE_EMPTY:
        return "-"
    return (slot.material or "OK")[:TEXT_MAX]


def render(box: mmu.Box, selected: int) -> List[str]:
    cmds: List[str] = []
    slots = {s.index: s for s in box.slots}

    for label, frame, gate in zip(LABELS, FRAMES, GATES):
        cmds.append("vis %s,%d" % (frame, 1 if gate == selected else 0))
        if gate == mmu.BYPASS:
            continue  # Happy Hare reports no state for an external spool here
        slot = slots.get(gate)
        if slot is None:
            cmds.append('%s.txt=""' % label)
            continue
        cmds.append('%s.txt="%s"' % (label, slotText(slot)))
        cmds.append("%s.pco=%d" % (label, mmu.rgb565(slot.color) if slot.available else mmu.DEFAULT_COLOR))

    if box.temperature is not None:
        cmds.append('t17.txt="%d"' % round(box.temperature))
    if box.target is not None:
        cmds.append('t18.txt="%d"' % round(box.target))
    cmds.append('t26.txt="%s"' % ("%d" % round(box.humidity) if box.humidity is not None else "--"))
    cmds.append("t16.pic=%d" % HEAT_ICON[box.heating])

    if box.errored and box.reason:
        cmds.append('t3.txt="%s"' % box.reason.replace('"', "'")[:60])
    elif box.busy:
        cmds.append('t3.txt="%s"' % box.action)
    return cmds
