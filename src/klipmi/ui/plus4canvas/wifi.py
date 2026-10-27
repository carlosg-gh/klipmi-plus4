# SPDX-License-Identifier: GPL-3.0-or-later
"""Wi-Fi control through NetworkManager's `nmcli` (the printer's computer runs NetworkManager).

Passwords are only ever passed to nmcli on its command line and are never logged.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Network:
    ssid: str
    signal: int = 0
    secured: bool = False
    active: bool = False
    saved: bool = False


def split_terse(line: str) -> List[str]:
    """Split one `nmcli -t` line on unescaped colons."""
    out, cur, i = [], "", 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


async def _run(*args: str, timeout: float = 30.0) -> Tuple[int, str]:
    proc = await asyncio.create_subprocess_exec("nmcli", *args, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "timed out"
    return proc.returncode or 0, out.decode("utf-8", "replace").strip()


async def device() -> Optional[str]:
    code, out = await _run("-t", "-f", "DEVICE,TYPE", "dev")
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) >= 2 and parts[1] == "wifi":
            return parts[0]
    return None


async def saved_profiles() -> List[str]:
    code, out = await _run("-t", "-f", "NAME,TYPE", "con", "show")
    return [p[0] for p in map(split_terse, out.splitlines()) if len(p) >= 2 and p[1] == "802-11-wireless"]


async def scan(rescan: bool = True) -> List[Network]:
    """Visible networks, strongest first, one entry per SSID (the connected one wins)."""
    saved = set(await saved_profiles())
    code, out = await _run("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan",
                           "yes" if rescan else "no")
    best = {}
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or not parts[1]:
            continue
        net = Network(ssid=parts[1], signal=int(parts[2] or 0), secured=parts[3] not in ("", "--"),
                      active=parts[0] == "*", saved=parts[1] in saved)
        old = best.get(net.ssid)
        if old is None or net.active or (not old.active and net.signal > old.signal):
            best[net.ssid] = net
    return sorted(best.values(), key=lambda n: (not n.active, -n.signal))


async def status() -> Tuple[str, int, str]:
    """(ssid, signal %, ip) of the current connection; empty ssid when not connected."""
    dev = await device()
    if dev is None:
        return "", 0, ""
    code, out = await _run("-t", "-f", "GENERAL.CONNECTION,IP4.ADDRESS", "dev", "show", dev)
    ssid, ip = "", ""
    for line in out.splitlines():
        key, _, value = line.partition(":")
        if key == "GENERAL.CONNECTION" and value != "--":
            ssid = value
        elif key.startswith("IP4.ADDRESS") and not ip:
            ip = value.split("/")[0]
    signal = 0
    if ssid:
        for net in await scan(rescan=False):
            if net.active:
                signal = net.signal
                ssid = net.ssid
    return ssid, signal, ip


async def connect(ssid: str, password: str = "") -> Tuple[bool, str]:
    logging.info("wifi: connecting to %s", ssid)
    if ssid in await saved_profiles() and not password:
        code, out = await _run("con", "up", "id", ssid, timeout=45)
    else:
        args = ["dev", "wifi", "connect", ssid]
        if password:
            args += ["password", password]
        code, out = await _run(*args, timeout=45)
    logging.info("wifi: connect %s exit %d", ssid, code)
    return code == 0, _short(out)


async def disconnect() -> Tuple[bool, str]:
    dev = await device()
    if dev is None:
        return False, "No Wi-Fi adapter"
    code, out = await _run("dev", "disconnect", dev)
    return code == 0, _short(out)


async def forget(ssid: str) -> Tuple[bool, str]:
    code, out = await _run("con", "delete", "id", ssid)
    return code == 0, _short(out)


def _short(out: str) -> str:
    line = out.strip().splitlines()[-1] if out.strip() else ""
    for noise in ("Error: ", "Connection activation failed: "):
        line = line.replace(noise, "")
    return line[:80]
