# SPDX-License-Identifier: GPL-3.0-or-later
"""Display commands for the stock `one_box_page` (QIDI Plus 4 HMI), as plain strings. No display dependency, so it is unit-testable."""

from typing import List

from klipmi.features import mmu

# Per column: external holder first, then the box slots 1A..4A
# Per column: external holder first, then the box slots 1A..4A.
# The HMI draws each filament as a solid-colour text block over the spool icon: it is
# hidden at page load, `bco` is the filament colour and the text "?" means unknown.
LABELS = ["t1", "t5", "t6", "t13", "t14"]
FRAMES = ["p5", "p6", "p7", "p8", "p9"]  # selection frame pictures
GATES = [mmu.BYPASS, 0, 1, 2, 3]

UNKNOWN_COLOR = 16904  # the HMI's own grey for a spool without a known colour
HEAT_ICON = {False: 366, True: 367}  # t16.pic, from the HMI's own comment


def slotCommands(label: str, slot: mmu.Slot) -> List[str]:
    if slot.status == mmu.GATE_EMPTY:
        return ["vis %s,0" % label]
    if slot.status == mmu.GATE_UNKNOWN:
        return ["vis %s,1" % label, "%s.bco=%d" % (label, UNKNOWN_COLOR), '%s.txt="?"' % label]
    color = mmu.rgb565(slot.color) if slot.color else UNKNOWN_COLOR
    return ["vis %s,1" % label, "%s.bco=%d" % (label, color), '%s.txt=""' % label]


def render(box: mmu.Box, selected: int) -> List[str]:
    cmds: List[str] = []
    slots = {s.index: s for s in box.slots}

    for label, frame, gate in zip(LABELS, FRAMES, GATES):
        cmds.append("vis %s,%d" % (frame, 1 if gate == selected else 0))
        if gate == mmu.BYPASS:
            continue  # Happy Hare reports no state for an external spool here
        slot = slots.get(gate)
        cmds.extend(slotCommands(label, slot) if slot else ["vis %s,0" % label])

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
