# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal dialogs: confirm, numeric keypad, list of choices."""

from typing import Callable, List, Optional, Sequence, Tuple

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import App, Modal
from klipmi.canvas.gfx import CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Rect, Theme, text


class Confirm(Modal):
    width, height = 520, 240

    def __init__(self, app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
        super().__init__(app)
        self.title_text, self.body, self.ok, self.on_ok, self.danger = title, body, ok, on_ok, danger

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 20, p.w - 48, 34), self.title_text, FONT_L, Theme.TEXT)
        ui.label(c, "modal/body", Rect(p.x + 24, p.y + 70, p.w - 48, 60), self.body, FONT_M, Theme.MUTED)
        cancel, ok = Rect(p.x + 24, p.y + p.h - 84, p.w - 48, 60).split_h(2, 16)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close)
        ui.button(c, "modal/ok", ok, self.ok, self._ok, style=ui.DANGER if self.danger else ui.ACCENT)

    def _ok(self):
        self.close()
        self.on_ok()


def confirm(app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
    app.open_modal(Confirm(app, title, body, ok, on_ok, danger))


class Keypad(Modal):
    """Numeric entry, e.g. a target temperature."""

    width, height = 420, 440

    def __init__(self, app: App, title: str, value: float, lo: float, hi: float, on_ok: Callable[[float], None],
                 unit: str = "", decimals: int = 0, presets: Sequence[Tuple[str, float]] = ()):
        super().__init__(app)
        self.title_text, self.lo, self.hi, self.on_ok, self.unit, self.decimals = title, lo, hi, on_ok, unit, decimals
        self.entry = ""
        self.initial = value
        self.presets = list(presets)[:4]
        self.error = ""

    @property
    def panel(self) -> Rect:
        return Rect(400 - self.width // 2 + (90 if self.presets else 0), 20, self.width, self.height)

    def _value(self) -> Optional[float]:
        if not self.entry:
            return self.initial
        try:
            return float(self.entry)
        except ValueError:
            return None

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 20, p.y + 14, p.w - 40, 30), self.title_text, FONT_M, Theme.MUTED)
        shown = self.entry or (("%%.%df" % self.decimals) % self.initial)
        ui.card(c, "modal/display", Rect(p.x + 20, p.y + 48, p.w - 40, 64), Theme.BG, Theme.SURFACE, 12)
        ui.big_text(c, "modal/display/v", p.x + 36, p.y + 58, shown, 44,
                    Theme.ERR if self.error else (Theme.TEXT if self.entry else Theme.MUTED), Theme.BG,
                    align=RIGHT, width=p.w - 110)
        c.op("modal/display/u", [text(Rect(p.x + p.w - 70, p.y + 70, 44, 30), self.unit, FONT_M, Theme.MUTED, Theme.BG, LEFT)])
        grid = Rect(p.x + 20, p.y + 124, p.w - 40, 236)
        rows = grid.split_v(4, 8)
        keys = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["." if self.decimals else "", "0", "<"]]
        for r, row in enumerate(keys):
            for k, cell in zip(row, rows[r].split_h(3, 8)):
                if k:
                    ui.button(c, "modal/k%d%s" % (r, k), cell, "Del" if k == "<" else k, (lambda k=k: self._key(k)),
                              font=FONT_L)
        cancel, ok = Rect(p.x + 20, p.y + p.h - 70, p.w - 40, 56).split_h(2, 12)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close)
        ui.button(c, "modal/ok", ok, "Set", self._ok, style=ui.ACCENT)
        if self.presets:
            side = Rect(p.x - 190, p.y + 48, 170, 64 * len(self.presets))
            c.op("modal/presets", [])
            for i, ((name, value), cell) in enumerate(zip(self.presets, side.split_v(len(self.presets), 10))):
                ui.button(c, "modal/p%d" % i, cell, name, (lambda v=value: self._preset(v)), bg=Theme.BG,
                          sub=("%%.%df %%s" % self.decimals) % (value, self.unit))

    def _key(self, k: str):
        self.error = ""
        if k == "<":
            self.entry = self.entry[:-1]
        elif len(self.entry) < 6 and not (k == "." and "." in self.entry):
            self.entry += k
        self.app.invalidate()

    def _preset(self, value: float):
        self.close()
        self.on_ok(value)

    def _ok(self):
        v = self._value()
        if v is None or v < self.lo or v > self.hi:
            self.error = "range"
            self.app.toast("Enter a value between %g and %g %s" % (self.lo, self.hi, self.unit), Theme.WARN)
            self.app.invalidate()
            return
        self.close()
        self.on_ok(v)


def keypad(app: App, title: str, value: float, lo: float, hi: float, on_ok: Callable[[float], None], **kw):
    app.open_modal(Keypad(app, title, value, lo, hi, on_ok, **kw))


class Choice(Modal):
    """Pick one of a few options (up to six)."""

    width = 520

    def __init__(self, app: App, title: str, options: Sequence[Tuple[str, str, Callable[[], None]]], body: str = ""):
        super().__init__(app)
        self.title_text, self.options, self.body = title, list(options)[:6], body
        self.height = 110 + (40 if body else 0) + 68 * ((len(self.options) + 1) // 2) + 70

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 18, p.w - 48, 34), self.title_text, FONT_L, Theme.TEXT)
        y = p.y + 64
        if self.body:
            ui.label(c, "modal/body", Rect(p.x + 24, y, p.w - 48, 32), self.body, FONT_S, Theme.MUTED)
            y += 40
        for i, (caption, sub, action) in enumerate(self.options):
            col, row = i % 2, i // 2
            cell = Rect(p.x + 24 + col * ((p.w - 48) // 2 + 8), y + row * 68, (p.w - 48) // 2 - 8, 58)
            ui.button(c, "modal/o%d" % i, cell, caption, (lambda a=action: self._pick(a)), sub=sub)
        ui.button(c, "modal/cancel", Rect(p.x + 24, p.y + p.h - 70, p.w - 48, 52), "Cancel", self.close, style=ui.GHOST)

    def _pick(self, action):
        self.close()
        action()


def choose(app: App, title: str, options, body: str = ""):
    app.open_modal(Choice(app, title, options, body))
