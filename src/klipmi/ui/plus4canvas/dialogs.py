# SPDX-License-Identifier: GPL-3.0-or-later
"""Modals: confirm and choice dialogs, the numeric keypad and text keyboard sheets, manual Z probing."""

from typing import Callable, Optional, Sequence, Tuple

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal
from klipmi.canvas.gfx import (CENTER, FONT_D48, FONT_D96, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, Rect,
                               Theme, clean, fill, icon, rounded, text, text_width, wrap_px)


def wrapped(c, key: str, r: Rect, s: str, font: int = FONT_XS, fg: int = Theme.MUTED, bg: int = Theme.SURFACE,
            lines: int = 3, line_h: int = 28):
    rows = wrap_px(s, r.w, font, lines)
    for i in range(lines):
        box = Rect(r.x, r.y + i * line_h, r.w, line_h)
        c.op("%s/%d" % (key, i), [text(box, rows[i] if i < len(rows) else "", font, fg, bg, LEFT)], [fill(box, bg)])


class Confirm(Modal):
    width = 560

    def __init__(self, app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
        super().__init__(app)
        self.title_text, self.body, self.ok, self.on_ok, self.danger = title, body, ok, on_ok, danger
        self.lines = min(4, len(wrap_px(body, self.width - 48, FONT_XS, 4)))
        self.height = 62 + 28 * self.lines + 104

    def draw(self, c):
        p = self.panel
        c.op("modal/title", [text(Rect(p.x + 24, p.y + 16, p.w - 48, 40), self.title_text, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT)])
        wrapped(c, "modal/body", Rect(p.x + 24, p.y + 62, p.w - 48, 28 * self.lines), self.body, FONT_XS, Theme.MUTED,
                Theme.SURFACE, self.lines, 28)
        cancel, ok = Rect(p.x + 20, p.y + p.h - 80, p.w - 40, 60).split_h(2, 12)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close)
        ui.button(c, "modal/ok", ok, self.ok, self._ok, style=ui.DANGER if self.danger else ui.ACCENT)

    def _ok(self):
        self.close()
        self.on_ok()


def confirm(app: App, title: str, body: str, ok: str, on_ok: Callable[[], None], danger: bool = True):
    app.open_modal(Confirm(app, title, body, ok, on_ok, danger))


class Choice(Modal):
    """Pick one of a few options (up to eight), two per row."""

    width = 600

    def __init__(self, app: App, title: str, options: Sequence[Tuple[str, str, Callable[[], None]]], body: str = ""):
        super().__init__(app)
        self.title_text, self.options, self.body = title, list(options)[:8], body
        rows = (len(self.options) + 1) // 2
        self.height = min(CONTENT.h - 24, 68 + (60 if body else 0) + 80 * rows + 76)

    def draw(self, c):
        p = self.panel
        c.op("modal/title", [text(Rect(p.x + 24, p.y + 14, p.w - 48, 40), self.title_text, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT)])
        y = p.y + 62
        if self.body:
            wrapped(c, "modal/body", Rect(p.x + 24, y, p.w - 48, 56), self.body, FONT_XS, Theme.MUTED, Theme.SURFACE, 2, 28)
            y += 60
        col_w = (p.w - 40 - 8) // 2
        for i, (caption, sub, action) in enumerate(self.options):
            cell = Rect(p.x + 20 + (i % 2) * (col_w + 8), y + (i // 2) * 80, col_w, 72)
            ui.button(c, "modal/o%d" % i, cell, caption, (lambda a=action: self._pick(a)), sub=sub)
        ui.button(c, "modal/cancel", Rect(p.x + 20, p.y + p.h - 72, p.w - 40, 56), "Cancel", self.close, style=ui.OUTLINE)

    def _pick(self, action):
        self.close()
        action()


def choose(app: App, title: str, options, body: str = ""):
    app.open_modal(Choice(app, title, options, body))


class Keypad(Modal):
    """Numeric entry sheet: name and the value being typed on the left with presets, keys on the right."""

    sheet = True

    def __init__(self, app: App, title: str, value: float, lo: float, hi: float, on_ok: Callable[[float], None],
                 unit: str = "", icon_name: str = "", current: Optional[float] = None,
                 presets: Sequence[Tuple[str, float]] = (), allow_off: bool = True, nav: Optional[str] = None,
                 decimals: int = 0):
        super().__init__(app)
        self.title_text, self.lo, self.hi, self.on_ok, self.unit = title, lo, hi, on_ok, unit
        self.icon_name, self.current, self.allow_off, self.decimals = icon_name, current, allow_off, decimals
        self.presets = list(presets)[:4]
        self.initial = value
        self.entry = ""
        self.error = False
        self.nav = nav

    def _value(self) -> Optional[float]:
        if not self.entry:
            return self.initial
        try:
            return float(self.entry)
        except ValueError:
            return None

    def draw(self, c):
        left = Rect(CONTENT.x, CONTENT.y, 308, CONTENT.h)
        ui.card(c, "modal/l", left)
        head = Rect(left.x + 16, left.y + 12, left.w - 32, 32)
        cmds = [fill(head, Theme.SURFACE)]
        x = head.x
        if self.icon_name:
            cmds.append(icon(self.icon_name, x, head.y + 4, 24, Theme.SURFACE, Theme.MUTED))
            x += 34
        cmds.append(text(Rect(x, head.y, head.w - 110, head.h), self.title_text, FONT_S, Theme.TEXT, Theme.SURFACE, LEFT))
        if self.current is not None:
            cmds += ui.value_cmds(Rect(head.x + head.w - 100, head.y, 100, head.h), "%d" % round(self.current), FONT_S,
                                  Theme.MUTED, Theme.SURFACE, 2, self.unit == "C")[1:]
        c.op("modal/l/head", cmds)
        shown = self.entry or (("%%.%df" % self.decimals) % self.initial)
        disp = Rect(left.x + 16, left.y + 54, left.w - 32, 124)
        color = Theme.ERR if self.error else (Theme.TEXT if self.entry else Theme.MUTED)
        font = FONT_D96 if text_width(shown + self.unit, FONT_D96) < disp.w - 30 else FONT_D48
        c.op("modal/l/disp", rounded(disp, Theme.BG, 10, Theme.SURFACE) +
             [fill(Rect(disp.x + 10, disp.y + disp.h - 3, disp.w - 20, 3), Theme.ACCENT)] +
             ui.value_cmds(Rect(disp.x + 10, disp.y + 8, disp.w - 20, disp.h - 16), shown, font, color, Theme.BG, CENTER,
                           self.unit == "C", self.unit if self.unit not in ("", "C") else "", FONT_D48 if font == FONT_D96 else FONT_SB)[1:])
        if self.presets:
            cells = [r for row in Rect(left.x + 16, left.y + 190, left.w - 32, 136).split_v(2, 8) for r in row.split_h(2, 8)]
            for i, ((name, v), cell) in enumerate(zip(self.presets, cells)):
                key = "modal/p%d" % i
                ui.button(c, key, cell, "", (lambda v=v: self._done(v)), style=ui.OUTLINE)
                c.op(key + "/v", ui.value_cmds(Rect(cell.x + 6, cell.y + 6, cell.w - 12, 30), "%d" % v, FONT_SB, Theme.TEXT,
                                               Theme.SURFACE, CENTER, self.unit == "C",
                                               "%" if self.unit == "%" else "", FONT_SB)[1:] +
                     [text(Rect(cell.x + 6, cell.y + 34, cell.w - 12, 24), name, FONT_XS, Theme.MUTED, Theme.SURFACE, CENTER)])
        row = Rect(left.x + 16, left.y + left.h - 72, left.w - 32, 56)
        cancel, off = row.split_h(2, 8) if self.allow_off else (row, None)
        ui.button(c, "modal/cancel", cancel, "Cancel", self.close, icon_name="x")
        if off is not None:
            ui.button(c, "modal/off", off, "Off", lambda: self._done(0))
        keys = Rect(CONTENT.x + 316, CONTENT.y, CONTENT.w - 316, CONTENT.h)
        ui.card(c, "modal/r", keys)
        grid = keys.inset(10)
        rows = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["<", "0", "ok"]]
        if self.decimals:
            rows[3][0] = "."
        for r, (labels, line) in enumerate(zip(rows, grid.split_v(4, 8))):
            for k, cell in zip(labels, line.split_h(3, 8)):
                if k == "ok":
                    ui.button(c, "modal/ok", cell, "", self._ok, style=ui.ACCENT, icon_name="check", icon_size=32)
                elif k == "<":
                    ui.button(c, "modal/del", cell, "", self._del, icon_name="del", icon_size=32)
                else:
                    ui.button(c, "modal/k%s" % k, cell, k, (lambda k=k: self._key(k)), font=FONT_MB)

    def _key(self, k: str):
        self.error = False
        if len(self.entry) < 5 and not (k == "." and "." in self.entry):
            self.entry += k
        self.app.invalidate()

    def _del(self):
        self.error = False
        self.entry = self.entry[:-1]
        self.app.invalidate()

    def _done(self, v: float):
        self.close()
        self.on_ok(v)

    def _ok(self):
        v = self._value()
        if v is None or v < self.lo or v > self.hi:
            self.error = True
            self.app.toast("Enter a value from %g to %g" % (self.lo, self.hi), Theme.WARN)
            self.app.invalidate()
            return
        self._done(v)


def keypad(app: App, title: str, value: float, lo: float, hi: float, on_ok: Callable[[float], None], **kw):
    app.open_modal(Keypad(app, title, value, lo, hi, on_ok, **kw))


class TextEntry(Modal):
    """On-screen keyboard sheet for a line of text (a Wi-Fi password). `secret` hides it until Show is on."""

    sheet = True
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

    def draw(self, c):
        p = CONTENT
        c.op("modal/title", [text(Rect(p.x + 4, p.y, p.w - 8, 30), self.title_text, FONT_XS, Theme.MUTED, Theme.BG, LEFT)])
        field = Rect(p.x, p.y + 32, p.w - (136 if self.secret else 0), 56)
        ui.card(c, "modal/field", field, Theme.SURFACE, Theme.BG, 10)
        shown = ("*" * len(self.entry)) if self.secret and not self.reveal else clean(self.entry)
        while shown and text_width(shown, FONT_SB) > field.w - 50:
            shown = shown[1:]
        c.op("modal/field/t", [text(Rect(field.x + 16, field.y, field.w - 32, field.h), shown + "|", FONT_SB, Theme.TEXT,
                                    Theme.SURFACE, LEFT)])
        if self.secret:
            ui.button(c, "modal/show", Rect(p.x + p.w - 128, p.y + 32, 128, 56), "Hide" if self.reveal else "Show",
                      self._toggle_reveal, bg=Theme.BG, font=FONT_XSB)
        rows = self.LAYERS[1 if self.symbols else 0]
        kw = (p.w - 9 * 6) // 10
        lines = Rect(p.x, p.y + 98, p.w, 5 * 58 + 4 * 6).split_v(5, 6)
        for r, chars in enumerate(rows):
            wide = kw + kw // 2 if r == 3 else 0
            total = len(chars) * kw + (len(chars) - 1) * 6 + (2 * (wide + 6) if r == 3 else 0)
            x = lines[r].x + (lines[r].w - total) // 2
            if r == 3:
                if self.symbols:
                    c.op("modal/shift", [fill(Rect(x, lines[r].y, wide, 58), Theme.BG)])
                else:
                    ui.button(c, "modal/shift", Rect(x, lines[r].y, wide, 58), "", self._toggle_shift, bg=Theme.BG,
                              icon_name="up", selected=self.shift)
                x += wide + 6
            for i, ch in enumerate(chars):
                out = ch.upper() if (self.shift and ch.isalpha()) else ch
                ui.button(c, "modal/k%d%d" % (r, i), Rect(x, lines[r].y, kw, 58), out, (lambda o=out: self._type(o)), bg=Theme.BG)
                x += kw + 6
            if r == 3:
                ui.button(c, "modal/bs", Rect(x, lines[r].y, wide, 58), "", self._backspace, bg=Theme.BG, icon_name="del")
        bottom = lines[4]
        ui.button(c, "modal/sym", Rect(bottom.x, bottom.y, 112, 58), "abc" if self.symbols else "123",
                  self._toggle_symbols, bg=Theme.BG, font=FONT_XSB)
        ui.button(c, "modal/space", Rect(bottom.x + 118, bottom.y, 290, 58), "", lambda: self._type(" "), bg=Theme.BG)
        ui.button(c, "modal/cancel", Rect(bottom.x + 414, bottom.y, 140, 58), "Cancel", self._cancel, bg=Theme.BG,
                  style=ui.OUTLINE, font=FONT_XSB)
        ui.button(c, "modal/ok", Rect(bottom.x + 560, bottom.y, bottom.w - 560, 58), self.ok_text,
                  self._ok if len(self.entry) >= self.min_len else None, style=ui.ACCENT, bg=Theme.BG, font=FONT_XSB)

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


class ManualProbe(Modal):
    """Klipper's manual Z probe (PROBE_CALIBRATE, Z_ENDSTOP_CALIBRATE): nudge the nozzle until paper drags, accept."""

    width, height = 600, 330
    STEPS = [0.01, 0.05, 0.1, 1.0]

    def __init__(self, app: App):
        super().__init__(app)
        self.step = 1

    def draw(self, c):
        app, p = self.app, self.panel
        z = app.get("manual_probe", "z_position", None)
        c.op("modal/title", [text(Rect(p.x + 24, p.y + 14, p.w - 48, 40), "Z offset: paper test", FONT_SB, Theme.TEXT,
                                  Theme.SURFACE, LEFT)])
        ui.value(c, "modal/z", Rect(p.x + 24, p.y + 60, 260, 70), "--" if z is None else "%.3f" % z, FONT_D48)
        steps = Rect(p.x + 300, p.y + 68, p.w - 324, 52)
        for i, (s, cell) in enumerate(zip(self.STEPS, steps.split_h(len(self.STEPS), 6))):
            ui.button(c, "modal/s%d" % i, cell, "%g" % s, (lambda i=i: self._set_step(i)), style=ui.OUTLINE,
                      selected=i == self.step, font=FONT_XSB)
        move = Rect(p.x + 20, p.y + 144, p.w - 40, 72).split_h(2, 12)
        ui.button(c, "modal/down", move[0], "Lower", lambda: app.gcode("TESTZ Z=-%g" % self.STEPS[self.step]), icon_name="down")
        ui.button(c, "modal/up", move[1], "Raise", lambda: app.gcode("TESTZ Z=+%g" % self.STEPS[self.step]), icon_name="up")
        row = Rect(p.x + 20, p.y + p.h - 80, p.w - 40, 60).split_h(2, 12)
        ui.button(c, "modal/abort", row[0], "Abort", lambda: self._end("ABORT"), style=ui.OUTLINE)
        ui.button(c, "modal/accept", row[1], "Accept", lambda: self._end("ACCEPT"), style=ui.ACCENT, icon_name="check")

    def _set_step(self, i):
        self.step = i
        self.app.invalidate()

    def _end(self, verb: str):
        self.close()
        self.app.gcode(verb)
        if verb == "ACCEPT":
            self.app.toast("Offset accepted. Save config to keep it.", Theme.OK, 8)
