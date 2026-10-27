#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Flash a .tft to a TJC display over serial (`whmi-wri`). Stop any service using the port first.

    flash_tft.py --port /dev/ttyS1 --baud 921600 file.tft [--dry-run]

Protocol: `connect` must answer `comok ...`; `whmi-wri <size>,<baud>,0` is answered with 0x05
at the upload baud; the file then goes out in 4096-byte chunks, each acknowledged with 0x05
(0x08 + a 4-byte offset asks to resume from that offset).
"""

import argparse
import struct
import sys
import time

import serial

END = b"\xff\xff\xff"
CHUNK = 4096


def read_reply(port: serial.Serial, timeout: float) -> bytes:
    port.timeout = timeout
    return port.read(1)


def connect(port: serial.Serial) -> str:
    port.reset_input_buffer()
    port.write(END)
    time.sleep(0.1)
    port.write(b"connect" + END)
    time.sleep(0.5)
    reply = port.read(300)
    if b"comok" not in reply:
        raise SystemExit("no comok reply: %r" % reply)
    return reply.decode("latin-1").strip("\xff")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tft")
    ap.add_argument("--port", default="/dev/ttyS1")
    ap.add_argument("--baud", type=int, default=921600, help="current display baud")
    ap.add_argument("--upload-baud", type=int, default=None, help="default: same as --baud")
    ap.add_argument("--dry-run", action="store_true", help="connect and report, do not flash")
    args = ap.parse_args()
    upload_baud = args.upload_baud or args.baud

    with open(args.tft, "rb") as f:
        data = f.read()
    print("file: %s, %d bytes" % (args.tft, len(data)))

    port = serial.Serial(args.port, args.baud, timeout=0.6)
    print("display:", connect(port))
    if args.dry_run:
        print("dry run, nothing flashed")
        return 0

    port.write(b"whmi-wri %d,%d,0" % (len(data), upload_baud) + END)
    port.flush()
    port.baudrate = upload_baud
    if read_reply(port, 2.0) != b"\x05":
        raise SystemExit("display did not accept the upload command")
    print("display ready, uploading at %d baud" % upload_baud)

    pos, started, last = 0, time.time(), 0
    while pos < len(data):
        chunk = data[pos : pos + CHUNK]
        port.write(chunk)
        reply = read_reply(port, len(chunk) * 10 / upload_baud + 3.0)
        if reply == b"\x08":
            port.timeout = 1.0
            raw = port.read(4)
            if len(raw) != 4:
                raise SystemExit("incomplete resume offset")
            pos = struct.unpack("<I", raw)[0]
            continue
        if reply != b"\x05":
            raise SystemExit("bad reply %r at offset %d" % (reply, pos))
        pos += len(chunk)
        if pos - last >= 1 << 20 or pos == len(data):
            last = pos
            print("%5.1f%%  %d/%d bytes, %ds" % (100 * pos / len(data), pos, len(data), time.time() - started), flush=True)

    print("upload complete; the display restarts by itself")
    return 0


if __name__ == "__main__":
    sys.exit(main())
