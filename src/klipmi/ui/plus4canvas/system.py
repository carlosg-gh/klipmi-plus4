# SPDX-License-Identifier: GPL-3.0-or-later
"""System: Wi-Fi, screen brightness and sleep, restarts and power; the Wi-Fi sheet, About, the offline screen."""

import logging
import socket
import time
from typing import List, Optional

from klipmi.canvas import widgets as ui
from klipmi.canvas.app import CONTENT, App, Modal, Page
from klipmi.canvas.gfx import (CENTER, FONT_MB, FONT_S, FONT_SB, FONT_XS, FONT_XSB, LEFT, RIGHT, Rect, Theme, fill, icon,
                               rounded, soft_disc, text)

from . import wifi
from .dialogs import choose, confirm, text_entry, wrapped


def signal_cmds(x: int, y: int, percent: int, color: int, bg: int, off: int = Theme.BORDER, scale: int = 1) -> List[str]:
    """Four rising bars (rounded), lit by signal strength. 40 x 30 px at scale 1."""
    lit = 0 if percent <= 0 else min(4, 1 + percent // 26)
    cmds = [fill(Rect(x, y, 40, 30), bg)]
    for i in range(4):
        h = 9 + i * 7
        cmds.append(fill(Rect(x + i * 10, y + 30 - h, 7, h), color if i < lit else off))
    return cmds


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


class SystemPage(Page):
    nav = "system"
    allow_offline = True
    SLEEP = [0, 5, 15, 30]

    def __init__(self, app):
        super().__init__(app)
        self.ssid, self.signal, self.ip = "", 0, ""
        self.loaded = False

    def enter(self):
        self.app.spawn(self._load())

    async def _load(self):
        try:
            self.ssid, self.signal, self.ip = await wifi.status()
        except Exception as e:
            logging.info("wifi status: %s", e)
        self.ip = self.ip or local_ip()
        self.loaded = True
        self.app.invalidate()

    def draw(self, c):
        app = self.app
        left = Rect(CONTENT.x, CONTENT.y, 420, CONTENT.h)
        net = Rect(left.x, left.y, left.w, 104)
        ui.button(c, "sy/net", net, "", lambda: app.open_modal(WifiSheet(app, self)), face=Theme.SURFACE, bg=Theme.BG, radius=12)
        c.op("sy/net/c", signal_cmds(net.x + 20, net.y + 37, self.signal, Theme.ACCENT, Theme.SURFACE) + [
            text(Rect(net.x + 80, net.y + 18, net.w - 130, 34), self.ssid or ("Not connected" if self.loaded else "..."),
                 FONT_SB, Theme.TEXT if self.ssid else Theme.MUTED, Theme.SURFACE, LEFT),
            text(Rect(net.x + 80, net.y + 54, net.w - 130, 30), self.ip or "no address", FONT_XS, Theme.MUTED, Theme.SURFACE, LEFT),
            icon("right", net.x + net.w - 40, net.y + 40, 24, Theme.SURFACE, Theme.MUTED)])
        bright = Rect(left.x, left.y + 112, left.w, 76)
        ui.card(c, "sy/b", bright)
        b = app.settings["brightness"]
        c.op("sy/b/i", [icon("sun", bright.x + 16, bright.y + 26, 24, Theme.SURFACE, Theme.MUTED),
                        icon("sun", bright.x + bright.w - 48, bright.y + 22, 32, Theme.SURFACE, Theme.TEXT)])
        ui.slider(c, "sy/b/s", Rect(bright.x + 56, bright.y + 14, bright.w - 120, 48), (b - 10) / 90.0, self._brightness)
        sleep = Rect(left.x, left.y + 196, left.w, 76)
        ui.card(c, "sy/s", sleep)
        c.op("sy/s/i", [icon("moon", sleep.x + 16, sleep.y + 22, 32, Theme.SURFACE, Theme.MUTED)])
        current = app.settings["sleep_minutes"]
        for i, (m, cell) in enumerate(zip(self.SLEEP, Rect(sleep.x + 60, sleep.y + 12, sleep.w - 72, 52).split_h(4, 6))):
            ui.button(c, "sy/s/%d" % i, cell, "Never" if m == 0 else "%dm" % m, (lambda m=m: self._sleep(m)), style=ui.OUTLINE,
                      font=FONT_XSB, selected=m == current)
        low = Rect(left.x, left.y + 280, left.w, left.h - 280).split_h(2, 8)
        ui.button(c, "sy/off", low[0], "Screen off", self._screen_off, bg=Theme.BG, icon_name="moon", vertical=True,
                  icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "sy/about", low[1], "About", lambda: app.open_modal(About(app)), bg=Theme.BG, icon_name="info",
                  vertical=True, icon_ink=Theme.MUTED, font=FONT_XSB)
        right = Rect(CONTENT.x + 428, CONTENT.y, CONTENT.w - 428, CONTENT.h)
        cells = [cell for row in right.split_v(2, 8) for cell in row.split_h(2, 8)]
        ui.button(c, "sy/restart", cells[0], "Klipper", lambda: confirm(
            app, "Restart Klipper", "Reloads the configuration. A running print stops.", "Restart",
            lambda: app.gcode("RESTART"), danger=app.printing), bg=Theme.BG, icon_name="refresh", vertical=True,
            icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "sy/fw", cells[1], "Firmware", lambda: confirm(
            app, "Firmware restart", "Restarts Klipper and every controller board. A running print stops.", "Restart",
            lambda: app.spawn(app.call("printer.firmware_restart")), danger=app.printing), bg=Theme.BG, icon_name="bolt",
            vertical=True, icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "sy/reboot", cells[2], "Reboot", lambda: confirm(
            app, "Reboot printer", "Restarts the printer's computer. It takes about a minute to come back.", "Reboot",
            lambda: app.spawn(app.call("machine.reboot"))), bg=Theme.BG, icon_name="reboot", vertical=True,
            icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "sy/shutdown", cells[3], "Shut down", lambda: confirm(
            app, "Shut down", "Powers off the printer's computer. Switch the printer off and on to start it again.",
            "Shut down", lambda: app.spawn(app.call("machine.shutdown"))), style=ui.DANGER, bg=Theme.BG, icon_name="power",
            vertical=True, font=FONT_XSB)

    def _brightness(self, f: float):
        v = int(round((10 + 90 * f) / 5.0) * 5)
        self.app.settings["brightness"] = v
        self.app.sink("dim=%d" % v)
        self.app.invalidate()

    def _sleep(self, m: int):
        self.app.settings["sleep_minutes"] = m
        self.app.invalidate()

    def _screen_off(self):
        self.app.sleeping = True
        self.app.sink("dim=3")


class About(Modal):
    width, height = 560, 300

    def __init__(self, app):
        super().__init__(app)
        self.rows = [("Klipper", "..."), ("Moonraker", "..."), ("Host", "..."), ("Address", "...")]
        app.spawn(self._load())

    async def _load(self):
        app = self.app
        klipper = moon = host = ""
        try:
            info = await app.call("printer.info")
            klipper = (info.get("software_version") or "").split("-")[0]
            host = info.get("hostname", "")
        except Exception:
            pass
        try:
            moon = ((await app.call("server.info")).get("moonraker_version") or "").split("-")[0]
        except Exception:
            pass
        self.rows = [("Klipper", klipper or "--"), ("Moonraker", moon or "--"), ("Host", host or socket.gethostname()),
                     ("Address", local_ip() or "--")]
        app.invalidate()

    def draw(self, c):
        p = self.panel
        for i, (k, v) in enumerate(self.rows):
            cell = Rect(p.x + 24 + (i % 2) * 264, p.y + 20 + (i // 2) * 84, 252, 76)
            c.op("modal/k%d" % i, [fill(cell, Theme.SURFACE), text(cell.row(0, 28), k, FONT_XS, Theme.MUTED, Theme.SURFACE, LEFT),
                                   text(cell.row(30, 40), v, FONT_SB, Theme.TEXT, Theme.SURFACE, LEFT)])
        ui.button(c, "modal/close", Rect(p.x + 20, p.y + p.h - 76, p.w - 40, 56), "Close", self.close, style=ui.OUTLINE)


class WifiSheet(Modal):
    """Scan, join, leave and forget Wi-Fi networks."""

    sheet = True
    nav = "system"
    rows = 5

    def __init__(self, app, system: Optional[SystemPage] = None):
        super().__init__(app)
        self.system = system
        self.nets: List[wifi.Network] = []
        self.offset = 0
        self.busy = "Scanning..."
        app.spawn(self._scan(True))

    async def _scan(self, rescan: bool):
        self.busy = "Scanning..."
        self.app.invalidate()
        try:
            self.nets = await wifi.scan(rescan)
            self.busy = "" if self.nets else "No networks found"
        except Exception as e:
            logging.warning("wifi scan failed: %s", e)
            self.busy = "Scan failed"
        self.offset = 0
        self.app.invalidate()

    def draw(self, c):
        p = CONTENT
        active = next((n for n in self.nets if n.active), None)
        area = Rect(p.x, p.y, p.w - 72, p.h - 72)
        for i, r in enumerate(area.split_v(self.rows, 6)):
            index = self.offset + i
            key = "modal/n%d" % i
            if index >= len(self.nets):
                if i == 0 and self.busy:
                    c.op(key, [fill(r, Theme.BG), text(r, self.busy, FONT_S, Theme.MUTED, Theme.BG, CENTER)])
                else:
                    c.op(key, [fill(r, Theme.BG)])
                continue
            n = self.nets[index]
            ui.button(c, key, r, "", (lambda n=n: self._pick(n)), face=Theme.SURFACE, bg=Theme.BG, radius=12)
            tag = "Connected" if n.active else ("Saved" if n.saved else "")
            cmds = signal_cmds(r.x + 18, r.y + (r.h - 30) // 2, n.signal, Theme.ACCENT if n.active else Theme.TEXT, Theme.SURFACE)
            cmds.append(text(Rect(r.x + 76, r.y, r.w - 300, r.h), n.ssid, FONT_S, Theme.ACCENT if n.active else Theme.TEXT,
                             Theme.SURFACE, LEFT))
            cmds.append(text(Rect(r.x + r.w - 220, r.y, 160, r.h), tag, FONT_XS, Theme.OK if n.active else Theme.MUTED,
                             Theme.SURFACE, RIGHT))
            if n.secured:
                cmds.append(icon("lock", r.x + r.w - 46, r.y + (r.h - 24) // 2, 24, Theme.SURFACE, Theme.MUTED))
            c.op(key + "/c", cmds)
        side = Rect(p.x + p.w - 64, p.y, 64, p.h - 72)
        ui.button(c, "modal/up", Rect(side.x, side.y, side.w, side.h // 2 - 4), "", self._up if self.offset else None, bg=Theme.BG,
                  icon_name="up", icon_size=32)
        ui.button(c, "modal/down", Rect(side.x, side.y + side.h // 2 + 4, side.w, side.h // 2 - 4), "",
                  self._down if self.offset + self.rows < len(self.nets) else None, bg=Theme.BG, icon_name="down", icon_size=32)
        foot = Rect(p.x, p.y + p.h - 64, p.w, 64)
        ui.button(c, "modal/rescan", Rect(foot.x, foot.y, 200, foot.h), "Rescan", lambda: self.app.spawn(self._scan(True)),
                  bg=Theme.BG, icon_name="refresh", icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "modal/disc", Rect(foot.x + 208, foot.y, 240, foot.h), "Disconnect", self._disconnect if active else None,
                  bg=Theme.BG, icon_name="x", icon_ink=Theme.MUTED, font=FONT_XSB)
        ui.button(c, "modal/close", Rect(foot.x + foot.w - 200, foot.y, 200, foot.h), "Done", self._close, style=ui.ACCENT,
                  bg=Theme.BG, icon_name="check", font=FONT_XSB)

    def _close(self):
        self.close()
        if self.system is not None:
            self.app.spawn(self.system._load())

    def _up(self):
        self.offset = max(0, self.offset - self.rows)
        self.app.invalidate()

    def _down(self):
        self.offset += self.rows
        self.app.invalidate()

    def _reopen(self):
        self.app.open_modal(self)
        self.app.spawn(self._scan(False))

    def _pick(self, n: "wifi.Network"):
        app = self.app
        if n.active:
            choose(app, n.ssid, [
                ("Disconnect", "leave the network", self._disconnect),
                ("Forget", "remove saved password", lambda: self._run(wifi.forget(n.ssid), "Forgot " + n.ssid)),
            ])
        elif n.saved or not n.secured:
            self._join(n, "")
        else:
            text_entry(app, "Password for " + n.ssid, lambda pw: self._join(n, pw), secret=True, ok="Connect", min_len=8,
                       on_cancel=self._reopen)

    def _join(self, n: "wifi.Network", password: str):
        self.app.open_modal(self)
        self.busy = "Connecting to " + n.ssid + "..."
        self.app.spawn(self._connect(n, password))

    async def _connect(self, n: "wifi.Network", password: str):
        ok, message = await wifi.connect(n.ssid, password)
        self.app.toast(("Connected to " + n.ssid) if ok else ("Could not connect: " + message), Theme.OK if ok else Theme.ERR, 8)
        await self._scan(False)

    def _disconnect(self):
        confirm(self.app, "Disconnect Wi-Fi", "The printer leaves the network: Mainsail and remote access stop until you "
                "connect again from this screen.", "Disconnect", lambda: self._run(wifi.disconnect(), "Disconnected"))

    def _run(self, coro, done: str):
        async def go():
            ok, message = await coro
            self.app.toast(done if ok else message or "Failed", Theme.OK if ok else Theme.ERR)
        self.app.spawn(go())


class OfflinePage(Page):
    bar_temps = False

    def draw_splash(self, c):
        app = self.app
        waiting = {"disconnected": "Waiting for Moonraker", "connecting": "Connecting to Moonraker"}.get(
            app.klippy, "Waiting for Klipper")
        lit = int(time.time()) % 3  # three dots, one lit, so the screen is seen to be alive
        dots = []
        for i in range(3):
            dots += soft_disc(372 + i * 28, 316, 6, Theme.ACCENT if i == lit else Theme.BORDER, Theme.BG)
        c.op("splash/title", [text(Rect(150, 170, 500, 50), "QIDI Plus 4", FONT_MB, Theme.TEXT, Theme.BG, CENTER)])
        c.op("splash/state", [text(Rect(150, 232, 500, 34), waiting, FONT_S, Theme.MUTED, Theme.BG, CENTER)])
        c.op("splash/dots", dots)
        note = (app.klippy_message or "").strip().splitlines()
        c.op("splash/note", [text(Rect(100, 350, 600, 28), note[0][:70] if note else "", FONT_XS, Theme.MUTED, Theme.BG,
                                  CENTER)])

    def draw(self, c):
        app = self.app
        if app.splashing():
            return self.draw_splash(c)
        r = CONTENT
        ui.card(c, "off/card", r)
        starting = app.klippy in ("startup", "connecting")
        headline = "Starting up..." if starting else ("Klipper is not ready" if app.klippy != "disconnected" else
                                                     "Moonraker is not reachable")
        c.op("off/card/h", [icon("warn", r.x + 24, r.y + 26, 32, Theme.SURFACE, Theme.MUTED),
                            text(Rect(r.x + 70, r.y + 20, r.w - 100, 44), headline, FONT_MB, Theme.TEXT, Theme.SURFACE, LEFT)])
        wrapped(c, "off/card/m", Rect(r.x + 24, r.y + 80, r.w - 48, 200), app.klippy_message or "", FONT_XS, Theme.MUTED,
                Theme.SURFACE, 7, 28)
        row = Rect(r.x + 16, r.y + r.h - 80, r.w - 32, 64).split_h(3, 8)
        ui.button(c, "off/restart", row[0], "Restart", lambda: app.spawn(app.call("printer.restart")), icon_name="refresh",
                  icon_ink=Theme.MUTED)
        ui.button(c, "off/fw", row[1], "Firmware", lambda: app.spawn(app.call("printer.firmware_restart")), style=ui.ACCENT,
                  icon_name="bolt")
        ui.button(c, "off/sys", row[2], "System", lambda: app.go_nav("system"), icon_name="sys", icon_ink=Theme.MUTED)
