# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing on a TJC display through its serial commands, with retained-mode diffing.

Pages draw their whole frame every time; the Canvas sends only the parts whose
commands differ from what is already on the glass. Every part has a key. A part
whose key starts with "<parent>/" is redrawn whenever its parent is, so draw
parents (cards) before their children (text on the card).
"""

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .metrics import ADV_LIGHT, ADV_REGULAR, ADV_SEMIBOLD, UPM_LIGHT, UPM_REGULAR, UPM_SEMIBOLD

W, H = 800, 480

# Fonts and pictures of hmi/plus4-canvas/plus4-canvas.tft (ids as listed in hmi/plus4-canvas/README.md).
# Light text looks best on dark faces; SemiBold keeps dark ink readable on bright faces (text() swaps by itself).
# Text is big on purpose (5 inch screen): 24 px is the smallest body size, 32 px the normal one.
FONT_XS, FONT_S, FONT_M, FONT_L = 7, 8, 9, 9          # Inter Light 20 / 24 / 32 / 32 (L is an alias of M)
FONT_XSB, FONT_SB, FONT_MB = 11, 12, 13              # Inter SemiBold 20 / 24 / 32
FONT_D48, FONT_D96 = 4, 5                             # SemiBold digits 48/96
# ids 0-3 are Inter Regular 16/20/24/32, 6 and 10 Light/SemiBold 16 (unused)
FONT_PX = {0: 16, 1: 20, 2: 24, 3: 32, 6: 16, 7: 20, 8: 24, 9: 32, 10: 16, 11: 20, 12: 24, 13: 32,
           FONT_D48: 48, FONT_D96: 96}
LINE_H = {7: 26, 8: 30, 9: 40, 11: 26, 12: 30, 13: 40, FONT_D48: 58, FONT_D96: 116}
DIGITS = {FONT_D48, FONT_D96}  # only "0123456789.-:%C /+"
BOLD_OF = {7: 11, 8: 12, 9: 13}

_BOLD = {FONT_D48, FONT_D96, 10, 11, 12, 13}
_LIGHT = {6, 7, 8, 9}


def text_width(s: str, font: int) -> int:
    """Pixel width of `s` in a font (advance widths from the Inter files)."""
    if font in _BOLD:
        adv, upm = ADV_SEMIBOLD, UPM_SEMIBOLD
    elif font in _LIGHT:
        adv, upm = ADV_LIGHT, UPM_LIGHT
    else:
        adv, upm = ADV_REGULAR, UPM_REGULAR
    return int(sum(adv[ord(ch) - 32] for ch in s if 32 <= ord(ch) < 127) * FONT_PX[font] / upm + 0.99)


LEFT, CENTER, RIGHT = 0, 1, 2


def rgb(r: int, g: int, b: int) -> int:
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def unrgb(c: int) -> Tuple[int, int, int]:
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def mix(a: int, b: int, t: float) -> int:
    ra, ga, ba = unrgb(a)
    rb, gb, bb = unrgb(b)
    t = max(0.0, min(1.0, t))
    return rgb(int(ra + (rb - ra) * t), int(ga + (gb - ga) * t), int(ba + (bb - ba) * t))


class Theme:
    BG = rgb(14, 16, 20)
    SURFACE = rgb(30, 34, 41)
    SURFACE2 = rgb(44, 49, 58)
    RAISED = rgb(58, 64, 75)
    BORDER = RAISED  # outlines, empty-gate rings, chart grid
    TEXT = rgb(236, 239, 244)
    MUTED = rgb(140, 148, 160)
    FAINT = rgb(90, 97, 108)
    ACCENT = rgb(0, 180, 235)
    ACCENT_DIM = rgb(0, 92, 124)
    OK = rgb(64, 200, 120)
    WARN = rgb(255, 176, 32)
    ERR = rgb(240, 72, 72)
    ERR_DIM = rgb(110, 32, 36)
    ERR_INK = rgb(255, 154, 154)  # text and icons on ERR_DIM
    COLD = rgb(80, 150, 255)
    HOT = rgb(255, 110, 40)


def heat_color(temperature: float, hot_at: float = 200.0) -> int:
    """Blue when cold, amber when warm, orange when hot."""
    t = (temperature - 30.0) / max(1.0, hot_at - 30.0)
    return mix(Theme.COLD, Theme.WARN, t * 2) if t < 0.5 else mix(Theme.WARN, Theme.HOT, t * 2 - 1)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def inset(self, dx: int, dy: Optional[int] = None) -> "Rect":
        dy = dx if dy is None else dy
        return Rect(self.x + dx, self.y + dy, max(0, self.w - 2 * dx), max(0, self.h - 2 * dy))

    def row(self, y: int, h: int) -> "Rect":
        return Rect(self.x, self.y + y, self.w, h)

    def col(self, x: int, w: int) -> "Rect":
        return Rect(self.x + x, self.y, w, self.h)

    def split_h(self, n: int, gap: int = 0) -> List["Rect"]:
        w = (self.w - gap * (n - 1)) / n
        return [Rect(int(self.x + i * (w + gap)), self.y, int(w), self.h) for i in range(n)]

    def split_v(self, n: int, gap: int = 0) -> List["Rect"]:
        h = (self.h - gap * (n - 1)) / n
        return [Rect(self.x, int(self.y + i * (h + gap)), self.w, int(h)) for i in range(n)]


# --- Command builders (pure) ------------------------------------------------

def wrap_px(s: str, width: int, font: int, max_lines: int) -> List[str]:
    """Break text into lines no wider than `width` px (words stay whole; the last line gets .. when cut)."""
    lines: List[str] = []
    words: List[Tuple[str, bool]] = []  # (piece, glued to the previous piece)
    for word in clean(s).split():  # a word wider than the box (a file name) breaks after _ - . or anywhere
        glued = False
        while text_width(word, font) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], font) > width:
                cut -= 1
            soft = next((p for p in (word.rfind(ch, 0, cut) for ch in "_-.") if p > cut // 2), -1)
            cut = soft + 1 if soft > 0 else cut
            words.append((word[:cut], glued))
            word, glued = word[cut:], True
        words.append((word, glued))
    line = ""
    for word, glued in words:
        trial = line + word if glued else (line + " " + word).strip()
        if line and text_width(trial, font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + " ..", width, font)
    return lines


def clean(s: str) -> str:
    """Text the display can show: no quotes or control characters, ASCII only."""
    s = str(s).replace('"', "'").replace("\\", "/")
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in s)


def fit(s: str, width: int, font: int) -> str:
    """Shorten to the box width, with '..' when cut."""
    s = clean(s)
    if text_width(s, font) <= width:
        return s
    while s and text_width(s + "..", font) > width:
        s = s[:-1]
    return s + ".." if s else ""


def fill(r: Rect, color: int) -> str:
    return "fill %d,%d,%d,%d,%d" % (r.x, r.y, r.w, r.h, color)


def _luma(c: int) -> float:
    r, g, b = unrgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def text(r: Rect, s: str, font: int, fg: int, bg: int, align: int = CENTER, valign: int = CENTER) -> str:
    if font in BOLD_OF and _luma(fg) < _luma(bg):  # dark ink on a bright face: Light would wash out
        font = BOLD_OF[font]
    return 'xstr %d,%d,%d,%d,%d,%d,%d,%d,%d,1,"%s"' % (
        r.x, r.y, r.w, r.h, font, fg, bg, align, valign, fit(s, r.w, font))


def disc(x: int, y: int, radius: int, color: int) -> str:
    return "cirs %d,%d,%d,%d" % (x, y, radius, color)


def ring(x: int, y: int, radius: int, color: int) -> str:
    return "cir %d,%d,%d,%d" % (x, y, radius, color)


def soft_disc(x: int, y: int, radius: int, color: int, bg: int) -> List[str]:
    """A filled circle whose stair-stepped edge is softened by two outlines blended towards the backdrop."""
    return [disc(x, y, radius, color), ring(x, y, radius, mix(color, bg, 0.45)), ring(x, y, radius + 1, mix(color, bg, 0.8))]


def line(x1: int, y1: int, x2: int, y2: int, color: int) -> str:
    return "line %d,%d,%d,%d,%d" % (x1, y1, x2, y2, color)


# Picture ids (see hmi/plus4-canvas/README.md and assets/pics/pics.json, written by tools/hmi_assets.js).
# Pictures have no alpha: each icon strip is baked for one (ink, backdrop) pair and each corner sheet for one
# (fill, backdrop) pair; drawing falls back to the nearest strip, or to filled discs for corners.
ICON_NAMES = ["home", "move", "temp", "fan", "spool", "files", "target", "sys", "stop", "nozzle", "bed", "chamber",
              "drop", "light", "power", "wifi", "play", "pause", "x", "clock", "hour", "flag", "layers", "gauge", "flow",
              "z", "plus", "minus", "reset", "cube", "check", "del", "up", "down", "left", "right", "level", "extrude",
              "retract", "arrow", "snow", "part", "side", "exhaust", "eject", "refresh", "wrench", "bypass", "guard",
              "back", "sort", "folder", "trash", "weight", "cal", "wave", "pid", "screw", "bolt", "info", "moon", "sun",
              "sound", "reboot", "warn", "lock"]
ICONS_PER_ROW = 25
ICON_INKS = [  # (ink, backdrop) of each strip; ids 0-9 are 24 px, 10-19 the same pairs at 32 px
    (Theme.MUTED, Theme.BG), (Theme.TEXT, Theme.BG), (Theme.ACCENT, Theme.SURFACE), (Theme.MUTED, Theme.SURFACE),
    (Theme.TEXT, Theme.SURFACE), (Theme.OK, Theme.SURFACE), (Theme.MUTED, Theme.SURFACE2), (Theme.TEXT, Theme.SURFACE2),
    (Theme.BG, Theme.ACCENT), (Theme.ERR_INK, Theme.ERR_DIM),
]
ICON_PIC = {24: 0, 32: len(ICON_INKS)}
CORNER_PIC = 2 * len(ICON_INKS)  # one atlas of corner sheets
CORNER_RADII = [4, 6, 8, 10, 12, 16, 20, 24]
CORNER_Y = [0, 4, 10, 18, 28, 40, 56, 76]
SHEET_W, SHEET_H, SHEETS_PER_ROW = 96, 100, 8
T = Theme
CORNER_PAIRS = [  # (fill, backdrop), atlas order
    (T.SURFACE, T.BG), (T.SURFACE2, T.SURFACE), (T.SURFACE2, T.BG), (T.ACCENT, T.BG), (T.ACCENT, T.SURFACE),
    (T.ACCENT, T.SURFACE2), (T.ERR_DIM, T.BG), (T.ERR_DIM, T.SURFACE), (T.BORDER, T.SURFACE), (T.SURFACE, T.BORDER),
    (T.BORDER, T.BG), (T.BG, T.BORDER), (T.BG, T.SURFACE), (T.SURFACE2, T.ACCENT), (T.TEXT, T.BG), (T.TEXT, T.SURFACE),
    (T.SURFACE2, T.TEXT), (T.ACCENT, T.TEXT), (T.ERR_DIM, T.TEXT), (T.SURFACE, T.TEXT), (T.BG, T.TEXT),
    (T.TEXT, T.ACCENT), (T.MUTED, T.SURFACE2), (T.ACCENT, T.ERR_DIM),
]
CORNER_SHEET = {pair: i for i, pair in enumerate(CORNER_PAIRS)}


def xpic(x: int, y: int, w: int, h: int, sx: int, sy: int, pic: int) -> str:
    return "xpic %d,%d,%d,%d,%d,%d,%d" % (x, y, w, h, sx, sy, pic)


def icon(name: str, x: int, y: int, size: int, bg: int, ink: int = Theme.MUTED) -> str:
    """One icon (24 or 32 px) from the strip baked for (`ink`, `bg`), or the nearest one there is."""
    k = min(range(len(ICON_INKS)), key=lambda i: (4 * _distance(ICON_INKS[i][1], bg) + _distance(ICON_INKS[i][0], ink)))
    n = ICON_NAMES.index(name)
    return xpic(x, y, size, size, (n % ICONS_PER_ROW) * size, (n // ICONS_PER_ROW) * size, ICON_PIC[size] + k)


def _distance(a: int, b: int) -> int:
    return sum((p - q) ** 2 for p, q in zip(unrgb(a), unrgb(b)))


def rounded(r: Rect, color: int, radius: int = 10, bg: Optional[int] = None) -> List[str]:
    """A filled rounded rectangle: three fills and four corners (anti-aliased sprites when the
    fill/backdrop pair and radius have a sheet, else filled discs)."""
    radius = max(0, min(radius, (r.w - 1) // 2, (r.h - 1) // 2))
    if radius < 2:
        return [fill(r, color)]
    cmds = [  # three fills that do not overlap (the display pays per pixel)
        fill(Rect(r.x + radius, r.y, r.w - 2 * radius, r.h), color),
        fill(Rect(r.x, r.y + radius, radius, r.h - 2 * radius), color),
        fill(Rect(r.x + r.w - radius, r.y + radius, radius, r.h - 2 * radius), color),
    ]
    x2, y2 = r.x + r.w - radius, r.y + r.h - radius
    sheet = CORNER_SHEET.get((color, bg))
    if sheet is not None and radius in CORNER_RADII:
        sx = (sheet % SHEETS_PER_ROW) * SHEET_W
        sy = (sheet // SHEETS_PER_ROW) * SHEET_H + CORNER_Y[CORNER_RADII.index(radius)]
        pic = CORNER_PIC
        return cmds + [xpic(r.x, r.y, radius, radius, sx, sy, pic), xpic(x2, r.y, radius, radius, sx + radius, sy, pic),
                       xpic(r.x, y2, radius, radius, sx + 2 * radius, sy, pic),
                       xpic(x2, y2, radius, radius, sx + 3 * radius, sy, pic)]
    x2, y2 = x2 - 1, y2 - 1
    return cmds + [disc(r.x + radius, r.y + radius, radius, color), disc(x2, r.y + radius, radius, color),
                   disc(r.x + radius, y2, radius, color), disc(x2, y2, radius, color)]


def big_font(size: int) -> int:
    """Digit font for a requested glyph height (the 48 px font draws ~35 px digits, the 96 px one ~70)."""
    return FONT_D48 if size <= 52 else FONT_D96


def big_width(s: str, size: int, gap: int = 0) -> int:
    return text_width(clean(s), big_font(size))


# --- Retained canvas -------------------------------------------------------

_NUMS = re.compile(r"-?\d+")


def bbox(cmds: Sequence[str]) -> Optional[Rect]:
    """Area a list of drawing commands touches."""
    x1 = y1 = 10 ** 6
    x2 = y2 = -1
    for cmd in cmds:
        verb = cmd.split(" ", 1)[0]
        n = [int(v) for v in _NUMS.findall(cmd.split('"', 1)[0][len(verb):])]
        if verb in ("fill", "xstr", "xpic") and len(n) >= 4:
            box = (n[0], n[1], n[0] + n[2], n[1] + n[3])
        elif verb in ("cirs", "cir") and len(n) >= 3:
            box = (n[0] - n[2], n[1] - n[2], n[0] + n[2] + 1, n[1] + n[2] + 1)
        elif verb == "line" and len(n) >= 4:
            box = (min(n[0], n[2]), min(n[1], n[3]), max(n[0], n[2]) + 1, max(n[1], n[3]) + 1)
        else:
            continue
        x1, y1, x2, y2 = min(x1, box[0]), min(y1, box[1]), max(x2, box[2]), max(y2, box[3])
    return Rect(x1, y1, x2 - x1, y2 - y1) if x2 >= 0 else None


def overlaps(a: Rect, b: Rect) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


@dataclass
class Hit:
    key: str
    rect: Rect
    action: Callable[..., None]
    wants_xy: bool = False  # the action takes the release point (sliders)


class Canvas:
    def __init__(self, sink: Callable[[str], None]):
        self.sink = sink
        self.shown: Dict[str, Tuple[str, ...]] = {}
        self.erase: Dict[str, Tuple[str, ...]] = {}
        self.boxes: Dict[str, Optional[Rect]] = {}
        self.seen: set = set()
        self.hits: List[Hit] = []
        self.pressed: Optional[str] = None
        self.queue: List[str] = []
        self.sent = 0  # commands sent, for tests and stats

    def send(self, cmd: str):
        self.sent += 1
        self.sink(cmd)

    def reset(self, color: int = Theme.BG):
        """Forget the glass and paint it one colour: the next frame redraws everything."""
        self.shown.clear()
        self.erase.clear()
        self.boxes.clear()
        self.send(fill(Rect(0, 0, W, H), color))

    def begin(self):
        self.seen = set()
        self.hits = []
        self.queue: List[str] = []

    def op(self, key: str, cmds: Sequence[str], erase: Sequence[str] = ()):
        """Draw `cmds` under `key` unless the glass already shows exactly that."""
        self.seen.add(key)
        cmds = tuple(cmds)
        if erase:
            self.erase[key] = tuple(erase)
        if self.shown.get(key) == cmds:
            return
        self.queue.extend(cmds)  # sent in end(), after erasing what disappeared
        self.shown[key] = cmds
        self.boxes[key] = bbox(cmds)
        prefix = key + "/"
        for child in [k for k in self.shown if k.startswith(prefix)]:
            del self.shown[child]

    def end(self):
        """Erase parts that were drawn last frame but not this one, then draw what changed."""
        for key in [k for k in self.shown if k not in self.seen]:
            for cmd in self.erase.pop(key, ()):
                self.send(cmd)
            self.forget(key)
        for cmd in self.queue:
            self.send(cmd)
        self.queue = []

    def forget(self, key: str):
        self.shown.pop(key, None)
        self.erase.pop(key, None)
        self.boxes.pop(key, None)

    def clear_region(self, r: Rect, color: int = Theme.BG, drop: Callable[[str], bool] = lambda k: False):
        """Paint `r` and forget every part drawn there (and parts `drop` names), so they draw again."""
        self.send(fill(r, color))
        for key in list(self.shown):
            box = self.boxes.get(key)
            if drop(key) or box is None or overlaps(box, r):
                self.forget(key)

    def region_of(self, prefix: str) -> Optional[Rect]:
        boxes = [b for k, b in self.boxes.items() if k.startswith(prefix) and b is not None]
        if not boxes:
            return None
        x1, y1 = min(b.x for b in boxes), min(b.y for b in boxes)
        x2, y2 = max(b.x + b.w for b in boxes), max(b.y + b.h for b in boxes)
        return Rect(x1, y1, x2 - x1, y2 - y1)

    def hit(self, key: str, rect: Rect, action: Callable[..., None], wants_xy: bool = False):
        self.hits.append(Hit(key, rect, action, wants_xy))

    def find(self, x: int, y: int) -> Optional[Hit]:
        for h in reversed(self.hits):  # last drawn is on top
            if h.rect.contains(x, y):
                return h
        return None
