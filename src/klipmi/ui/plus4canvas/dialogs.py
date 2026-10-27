# SPDX-License-Identifier: GPL-3.0-or-later
"""Modal dialogs: confirm, numeric keypad, text keyboard, list of choices."""

from typing import Callable, List, Optional, Sequence, Tuple

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import App, Modal
from klipmi.canvas.gfx import (CENTER, FONT_L, FONT_M, FONT_S, LEFT, RIGHT, Rect, Theme, clean, fill, ring, text,
                               text_width)


class Confirm(Modal):
    width, height = 600, 320

    def __init__(self, app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
        super().__init__(app)
        self.title_text, self.body, self.ok, self.on_ok, self.danger = title, body, ok, on_ok, danger

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 16, p.w - 48, 44), self.title_text, FONT_M, Theme.TEXT)
        ui.wrapped(c, "modal/body", Rect(p.x + 24, p.y + 72, p.w - 48, 120), self.body, FONT_S, Theme.MUTED, Theme.SURFACE, 4, 30)
        cancel, ok = Rect(p.x + 24, p.y + p.h - 92, p.w - 48, 68).split_h(2, 16)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close)
        ui.button(c, "modal/ok", ok, self.ok, self._ok, style=ui.DANGER if self.danger else ui.ACCENT)

    def _ok(self):
        self.close()
        self.on_ok()


def confirm(app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
    app.open_modal(Confirm(app, title, body, ok, on_ok, danger))


class Keypad(Modal):
    """Numeric entry, e.g. a target temperature. Presets sit in a column on the left of the same panel."""

    width, height = 400, 440

    def __init__(self, app: App, title: str, value: float, lo: float, hi: float, on_ok: Callable[[float], None],
                 unit: str = "", decimals: int = 0, presets: Sequence[Tuple[str, float]] = ()):
        super().__init__(app)
        self.title_text, self.lo, self.hi, self.on_ok, self.unit, self.decimals = title, lo, hi, on_ok, unit, decimals
        self.entry = ""
        self.initial = value
        self.presets = list(presets)[:5]
        self.error = ""
        if self.presets:
            self.width = 620

    @property
    def panel(self) -> Rect:
        return Rect((800 - self.width) // 2, 20, self.width, self.height)

    def _value(self) -> Optional[float]:
        if not self.entry:
            return self.initial
        try:
            return float(self.entry)
        except ValueError:
            return None

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 20, p.y + 8, p.w - 40, 36), self.title_text, FONT_S, Theme.MUTED)
        left = 214 if self.presets else 0
        body = Rect(p.x + 20 + left, p.y + 46, p.w - 40 - left, p.h - 46)
        shown = self.entry or (("%%.%df" % self.decimals) % self.initial)
        ui.card(c, "modal/display", Rect(body.x, body.y, body.w, 70), Theme.BG, Theme.SURFACE, 12)
        unit_w = 56 if self.unit else 0
        ui.big_text(c, "modal/display/v", body.x + 12, body.y + 8, shown, 52,
                    Theme.ERR if self.error else (Theme.TEXT if self.entry else Theme.MUTED), Theme.BG,
                    align=RIGHT, width=body.w - 24 - unit_w)
        if self.unit == "C":
            ux = body.x + body.w - 50
            c.op("modal/display/u", [ring(ux + 4, body.y + 24, 4, Theme.MUTED), ring(ux + 4, body.y + 24, 3, Theme.MUTED),
                                     text(Rect(ux + 12, body.y + 14, 30, 44), "C", FONT_M, Theme.MUTED, Theme.BG, LEFT)])
        else:
            c.op("modal/display/u", [text(Rect(body.x + body.w - 58, body.y + 14, 50, 44), self.unit, FONT_S, Theme.MUTED,
                                          Theme.BG, LEFT)])
        rows = Rect(body.x, body.y + 78, body.w, 252).split_v(4, 8)
        keys = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["." if self.decimals else "", "0", "<"]]
        for r, row in enumerate(keys):
            for k, cell in zip(row, rows[r].split_h(3, 8)):
                if k:
                    ui.button(c, "modal/k%d%s" % (r, k), cell, "Del" if k == "<" else k, (lambda k=k: self._key(k)),
                              font=FONT_S if k == "<" else FONT_M)
        cancel, ok = Rect(body.x, p.y + p.h - 68, body.w, 56).split_h(2, 12)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close)
        ui.button(c, "modal/ok", ok, "Set", self._ok, style=ui.ACCENT)
        if self.presets:
            side = Rect(p.x + 20, p.y + 46, 198, p.h - 46 - 12)
            unit = "" if self.unit == "C" else self.unit
            for i, ((name, value), cell) in enumerate(zip(self.presets, side.split_v(len(self.presets), 8))):
                ui.button(c, "modal/p%d" % i, cell, name, (lambda v=value: self._preset(v)), font=FONT_S,
                          sub=(("%%.%df %%s" % self.decimals) % (value, unit)).strip() if value else "")

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


class TextEntry(Modal):
    """On-screen keyboard for a line of text (a Wi-Fi password). `secret` hides the characters until Show is on."""

    width, height = 780, 460
    LAYERS = [
        ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"],
        ["1234567890", "!@#$%^&*()", "-_=+[]{};:", "'./,?<>\\|"],
    ]

    def __init__(self, app: App, title: str, on_ok: Callable[[str], None], secret: bool = False, ok: str = "OK",
                 initial: str = "", min_len: int = 0, on_cancel: Optional[Callable[[], None]] = None):
        super().__init__(app)
        self.on_cancel = on_cancel
        self.title_text, self.on_ok, self.secret, self.ok_text, self.min_len = title, on_ok, secret, ok, min_len
        self.entry = initial
        self.reveal = False
        self.shift = False
        self.symbols = False

    @property
    def panel(self) -> Rect:
        return Rect(10, 10, self.width, self.height)

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 20, p.y + 6, p.w - 40, 36), self.title_text, FONT_S, Theme.MUTED)
        field = Rect(p.x + 20, p.y + 44, p.w - 40 - 136 * (1 if self.secret else 0), 56)
        ui.card(c, "modal/field", field, Theme.BG, Theme.SURFACE, 10)
        shown = ("*" * len(self.entry)) if self.secret and not self.reveal else clean(self.entry)
        while shown and text_width(shown, FONT_M) > field.w - 50:
            shown = shown[1:]
        c.op("modal/field/t", [text(Rect(field.x + 16, field.y, field.w - 32, field.h), shown + "|", FONT_M, Theme.TEXT,
                                    Theme.BG, LEFT)])
        if self.secret:
            ui.button(c, "modal/show", Rect(p.x + p.w - 20 - 128, p.y + 44, 128, 56), "Hide" if self.reveal else "Show",
                      self._toggle_reveal, font=FONT_S)
        rows = self.LAYERS[1 if self.symbols else 0]
        kw = (p.w - 40 - 9 * 6) // 10
        lines = Rect(p.x + 20, p.y + 112, p.w - 40, 5 * 58 + 4 * 6).split_v(5, 6)
        for r, chars in enumerate(rows):
            wide = kw + kw // 2 if r == 3 else 0
            total = len(chars) * kw + (len(chars) - 1) * 6 + (2 * (wide + 6) if r == 3 else 0)
            x = lines[r].x + (lines[r].w - total) // 2
            if r == 3:
                if self.symbols:
                    c.op("modal/shift", [fill(Rect(x, lines[r].y, wide, 58), Theme.SURFACE)])
                else:
                    ui.button(c, "modal/shift", Rect(x, lines[r].y, wide, 58), "Aa", self._toggle_shift,
                              style=ui.ACCENT if self.shift else ui.NORMAL, font=FONT_S)
                x += wide + 6
            for i, ch in enumerate(chars):
                out = ch.upper() if (self.shift and ch.isalpha()) else ch
                ui.button(c, "modal/k%d%d" % (r, i), Rect(x, lines[r].y, kw, 58), out, (lambda o=out: self._type(o)))
                x += kw + 6
            if r == 3:
                ui.button(c, "modal/bs", Rect(x, lines[r].y, wide, 58), "Del", self._backspace, font=FONT_S)
        bottom = lines[4]
        ui.button(c, "modal/sym", Rect(bottom.x, bottom.y, 120, 58), "abc" if self.symbols else "123",
                  self._toggle_symbols, font=FONT_S)
        ui.button(c, "modal/space", Rect(bottom.x + 126, bottom.y, 300, 58), "space", lambda: self._type(" "), font=FONT_S)
        ui.button(c, "modal/cancel", Rect(bottom.x + 432, bottom.y, 150, 58), "Cancel", self._cancel, font=FONT_S)
        ui.button(c, "modal/ok", Rect(bottom.x + 588, bottom.y, bottom.w - 588, 58), self.ok_text,
                  self._ok if len(self.entry) >= self.min_len else None, style=ui.ACCENT, font=FONT_S)

    def _type(self, ch: str):
        if len(self.entry) < 64:
            self.entry += ch
        self.shift = False
        self.app.invalidate()

    def _backspace(self):
        self.entry = self.entry[:-1]
        self.app.invalidate()

    def _toggle_shift(self):
        self.shift = not self.shift
        self.app.invalidate()

    def _toggle_symbols(self):
        self.symbols = not self.symbols
        self.app.invalidate()

    def _toggle_reveal(self):
        self.reveal = not self.reveal
        self.app.invalidate()

    def _cancel(self):
        self.close()
        if self.on_cancel is not None:
            self.on_cancel()

    def _ok(self):
        self.close()
        self.on_ok(self.entry)


def text_entry(app: App, title: str, on_ok: Callable[[str], None], **kw):
    app.open_modal(TextEntry(app, title, on_ok, **kw))


class Choice(Modal):
    """Pick one of a few options (up to six)."""

    width = 620

    def __init__(self, app: App, title: str, options: Sequence[Tuple[str, str, Callable[[], None]]], body: str = ""):
        super().__init__(app)
        self.title_text, self.options, self.body = title, list(options)[:6], body
        self.height = 76 + (64 if body else 0) + 92 * ((len(self.options) + 1) // 2) + 84

    def draw(self, c):
        p = self.panel
        ui.label(c, "modal/title", Rect(p.x + 24, p.y + 14, p.w - 48, 44), self.title_text, FONT_M, Theme.TEXT)
        y = p.y + 66
        if self.body:
            ui.wrapped(c, "modal/body", Rect(p.x + 24, y, p.w - 48, 60), self.body, FONT_S, Theme.MUTED, Theme.SURFACE, 2, 30)
            y += 64
        for i, (caption, sub, action) in enumerate(self.options):
            col, row = i % 2, i // 2
            cell = Rect(p.x + 24 + col * ((p.w - 48) // 2 + 4), y + row * 92, (p.w - 48) // 2 - 4, 84)
            ui.button(c, "modal/o%d" % i, cell, caption, (lambda a=action: self._pick(a)), sub=sub)
        ui.button(c, "modal/cancel", Rect(p.x + 24, p.y + p.h - 76, p.w - 48, 60), "Cancel", self.close, style=ui.GHOST)

    def _pick(self, action):
        self.close()
        action()


def choose(app: App, title: str, options, body: str = ""):
    app.open_modal(Choice(app, title, options, body))
