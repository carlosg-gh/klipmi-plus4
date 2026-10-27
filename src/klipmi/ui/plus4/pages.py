# SPDX-License-Identifier: GPL-3.0-or-later
"""Pages of the QIDI Plus 4 stock HMI (`hmi/plus4`). Pages are addressed by name."""

import logging

from nextion import EventType

from klipmi.features import mmu
from klipmi.model.ui import BasePage
from klipmi.features import mmu_plus4
from klipmi.utils import classproperty

# Touch ids sent by the nav bar present on most stock pages
NAV_HOME, NAV_CONTROL, NAV_FILES, NAV_TOOLS, NAV_SETTINGS = 33, 34, 35, 36, 37


class Plus4Page(BasePage):
    @classproperty
    def pageRef(cls) -> str:
        return cls.name

    @classproperty
    def id(cls) -> int:
        # Page indices in the .HMI are not stable across editor saves; the name is used instead
        return -1


class BootPage(Plus4Page):
    @classproperty
    def name(cls) -> str:
        return "logo"


class MainPage(Plus4Page):
    """Home. Temperatures only for now; navigation to the other stock pages is not wired up yet."""

    @classproperty
    def name(cls) -> str:
        return "main"

    async def onDisplayEvent(self, type: EventType, data):
        if type == EventType.TOUCH:
            logging.info("main: touch id %d (unhandled)" % data.component_id)


class BoxPage(Plus4Page):
    """`one_box_page`: the four Happy Hare gates, box climate and load/unload buttons."""

    @classproperty
    def name(cls) -> str:
        return "one_box_page"

    selected: int = mmu.UNKNOWN
    box: mmu.Box | None = None

    async def init(self):
        status = self.state.printer.status
        await self.onPrinterStatusUpdate(status)

    async def render(self):
        if self.box is None:
            return
        for cmd in mmu_plus4.render(self.box, self.selected):
            await self.state.display.command(cmd, self.state.options.timeout)

    async def onPrinterStatusUpdate(self, data: dict):
        self.box = mmu.parse(data) or self.box
        await self.render()

    async def onDisplayEvent(self, type: EventType, data):
        if type != EventType.TOUCH or self.box is None:
            return
        touch = data.component_id
        if touch in mmu.COLUMNS:
            self.selected = mmu.COLUMNS[touch]
            await self.render()
        elif touch == mmu.EXIT:
            self.changePage(MainPage)
        else:
            script = mmu.gcode(touch, self.selected, self.box)
            if script is None:
                logging.info("box: touch id %d ignored (selected %d)" % (touch, self.selected))
                return
            for line in script.split("\n"):
                self.state.printer.runGcode(line)


class ZeroBoxPage(Plus4Page):
    """`zero_box_page`: stock "BOX not connected" page, used when Happy Hare is configured but disabled."""

    @classproperty
    def name(cls) -> str:
        return "zero_box_page"

    async def onDisplayEvent(self, type: EventType, data):
        if type == EventType.TOUCH and data.component_id == mmu.EXIT:
            self.changePage(MainPage)
