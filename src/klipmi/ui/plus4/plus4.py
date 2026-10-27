# SPDX-License-Identifier: GPL-3.0-or-later
from typing import Dict, List

from klipmi.features import mmu
from klipmi.model.ui import BaseUi
from klipmi.utils import classproperty

from .pages import BootPage, MainPage


class Plus4UI(BaseUi):
    @classproperty
    def printerObjects(cls) -> Dict[str, List[str]]:
        return {
            "extruder": ["target", "temperature"],
            "heater_bed": ["target", "temperature"],
            "heater_generic chamber": ["target", "temperature"],
            "display_status": ["progress"],
            "print_stats": ["state", "print_duration", "filename", "total_duration", "info"],
        }

    async def resolveObjects(self, available, query):
        objects = await super().resolveObjects(available, query)
        if self.state.options.klipmi.mmu != "off":
            objects.update(await mmu.resolveObjects(available, query))
        return objects

    def onNotReady(self):
        self.changePage(BootPage)

    def onReady(self):
        self.changePage(MainPage)

    def onStopped(self):
        pass

    def onMoonrakerError(self):
        pass

    def onKlipperError(self):
        pass
