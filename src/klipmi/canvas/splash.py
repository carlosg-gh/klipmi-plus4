# SPDX-License-Identifier: GPL-3.0-or-later
"""The start-up splash. Its fixed part (logo, name, status line, dots) is drawn both by klipmi and, as the same
commands, by the screen firmware itself at power-on (`tools/splash_program.py` prints them for the HMI editor),
so the hand-over from firmware to klipmi does not change a pixel."""

from typing import List

from .gfx import CENTER, FONT_MB, FONT_S, Rect, Theme, icon, rounded, soft_disc, text

LOGO = Rect(368, 60, 64, 64)
TITLE = Rect(150, 136, 500, 44)
STATUS = Rect(150, 182, 500, 30)
DOTS_Y = 236
DOT_X = (372, 400, 428)
TITLE_TEXT = "klipmi-plus4"


def logo_cmds() -> List[str]:
    return rounded(LOGO, Theme.ACCENT, 16, Theme.BG) + [icon("nozzle", LOGO.x + 16, LOGO.y + 16, 32, Theme.ACCENT, Theme.BG)]


def title_cmds() -> List[str]:
    return [text(TITLE, TITLE_TEXT, FONT_MB, Theme.TEXT, Theme.BG, CENTER)]


def status_cmds(s: str) -> List[str]:
    return [text(STATUS, s, FONT_S, Theme.MUTED, Theme.BG, CENTER)]


def dots_cmds(lit: int) -> List[str]:
    out: List[str] = []
    for i, x in enumerate(DOT_X):
        out += soft_disc(x, DOTS_Y, 6, Theme.ACCENT if i == lit else Theme.BORDER, Theme.BG)
    return out


def firmware_program(status: str = "Starting up") -> List[str]:
    """The lines for the canvas page's post-initialize event in the HMI project."""
    return logo_cmds() + title_cmds() + status_cmds(status) + dots_cmds(0)
