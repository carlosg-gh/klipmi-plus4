# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing on a TJC display through its serial commands, with retained-mode diffing.

Pages draw their whole frame every time; the Canvas sends only the parts whose
commands differ from what is already on the glass. Every part has a key. A part
whose key starts with "<parent>/" is redrawn whenever its parent is, so draw
parents (cards) before their children (text on the card).
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

W, H = 800, 480

# Fonts compiled into QIDI's Plus 4 HMI. Approximate advance width per character.
FONT_L, FONT_M, FONT_S = 0, 1, 2
CHAR_W = {FONT_L: 12.5, FONT_M: 10.2, FONT_S: 8.0}
LINE_H = {FONT_L: 30, FONT_M: 24, FONT_S: 20}

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
    TEXT = rgb(236, 239, 244)
    MUTED = rgb(140, 148, 160)
    FAINT = rgb(90, 97, 108)
    ACCENT = rgb(0, 180, 235)
    ACCENT_DIM = rgb(0, 92, 124)
    OK = rgb(64, 200, 120)
    WARN = rgb(255, 176, 32)
    ERR = rgb(240, 72, 72)
    ERR_DIM = rgb(110, 32, 36)
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

def clean(s: str) -> str:
    """Text the display can show: no quotes or control characters, ASCII only."""
    s = str(s).replace('"', "'").replace("\\", "/")
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in s)


def fit(s: str, width: int, font: int) -> str:
    """Shorten to the box width, with '..' when cut."""
    s = clean(s)
    n = int(width / CHAR_W[font])
    return s if len(s) <= n else s[: max(0, n - 2)] + ".."


def fill(r: Rect, color: int) -> str:
    return "fill %d,%d,%d,%d,%d" % (r.x, r.y, r.w, r.h, color)


def text(r: Rect, s: str, font: int, fg: int, bg: int, align: int = CENTER, valign: int = CENTER) -> str:
    return 'xstr %d,%d,%d,%d,%d,%d,%d,%d,%d,1,"%s"' % (
        r.x, r.y, r.w, r.h, font, fg, bg, align, valign, fit(s, r.w, font))


def disc(x: int, y: int, radius: int, color: int) -> str:
    return "cirs %d,%d,%d,%d" % (x, y, radius, color)


def line(x1: int, y1: int, x2: int, y2: int, color: int) -> str:
    return "line %d,%d,%d,%d,%d" % (x1, y1, x2, y2, color)


def rounded(r: Rect, color: int, radius: int = 10) -> List[str]:
    """A filled rounded rectangle: two fills and four corner discs."""
    radius = max(0, min(radius, (r.w - 1) // 2, (r.h - 1) // 2))
    if radius < 2:
        return [fill(r, color)]
    x2, y2 = r.x + r.w - radius - 1, r.y + r.h - radius - 1
    return [
        fill(Rect(r.x + radius, r.y, r.w - 2 * radius, r.h), color),
        fill(Rect(r.x, r.y + radius, r.w, r.h - 2 * radius), color),
        disc(r.x + radius, r.y + radius, radius, color),
        disc(x2, r.y + radius, radius, color),
        disc(r.x + radius, y2, radius, color),
        disc(x2, y2, radius, color),
    ]


# Seven-segment characters drawn with rectangles: the HMI's fonts top out at ~24 px.
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg",
    "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
}


def big_char_width(size: int, ch: str) -> int:
    if ch in ".:":
        return max(4, size // 6)
    if ch == "%":
        return int(size * 0.6)
    return int(size * 0.55)


def big_char(x: int, y: int, size: int, ch: str, fg: int, bg: int) -> List[str]:
    """One character of the large display font, `size` px high, background included."""
    w = big_char_width(size, ch)
    t = max(3, size // 9)  # stroke
    cmds = [fill(Rect(x, y, w, size), bg)]
    if ch == ".":
        cmds.append(fill(Rect(x, y + size - t, t, t), fg))
        return cmds
    if ch == ":":
        cmds += [fill(Rect(x, y + size // 3 - t // 2, t, t), fg), fill(Rect(x, y + 2 * size // 3, t, t), fg)]
        return cmds
    if ch == "%":
        rr = max(2, t)
        cmds += [disc(x + rr, y + rr + 1, rr, fg), disc(x + w - rr - 1, y + size - rr - 2, rr, fg)]
        for k in range(t):
            cmds.append(line(x + w - 2 - k, y + 1, x + 1 - k + t, y + size - 2, fg))
        return cmds
    half = size // 2
    seg = {
        "a": Rect(x + t, y, w - 2 * t, t),
        "b": Rect(x + w - t, y + t, t, half - t),
        "c": Rect(x + w - t, y + half, t, half - t),
        "d": Rect(x + t, y + size - t, w - 2 * t, t),
        "e": Rect(x, y + half, t, half - t),
        "f": Rect(x, y + t, t, half - t),
        "g": Rect(x + t, y + half - t // 2, w - 2 * t, t),
    }
    for s in SEGMENTS.get(ch, ""):
        cmds.append(fill(seg[s], fg))
    return cmds


def big_width(s: str, size: int, gap: int) -> int:
    return sum(big_char_width(size, ch) + gap for ch in s) - gap if s else 0


# --- Retained canvas -------------------------------------------------------

@dataclass
class Hit:
    key: str
    rect: Rect
    action: Callable[[], None]


class Canvas:
    def __init__(self, sink: Callable[[str], None]):
        self.sink = sink
        self.shown: Dict[str, Tuple[str, ...]] = {}
        self.erase: Dict[str, Tuple[str, ...]] = {}
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
        prefix = key + "/"
        for child in [k for k in self.shown if k.startswith(prefix)]:
            del self.shown[child]

    def end(self):
        """Erase parts that were drawn last frame but not this one, then draw what changed."""
        for key in [k for k in self.shown if k not in self.seen]:
            for cmd in self.erase.pop(key, ()):
                self.send(cmd)
            del self.shown[key]
        for cmd in self.queue:
            self.send(cmd)
        self.queue = []

    def hit(self, key: str, rect: Rect, action: Callable[[], None]):
        self.hits.append(Hit(key, rect, action))

    def find(self, x: int, y: int) -> Optional[Hit]:
        for h in reversed(self.hits):  # last drawn is on top
            if h.rect.contains(x, y):
                return h
        return None
