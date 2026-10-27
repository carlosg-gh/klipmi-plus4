# SPDX-License-Identifier: GPL-3.0-or-later
"""Serial link to a TJC display used as a canvas.

Commands are written without waiting for an answer (`bkcmd=2`: the display only
reports failures). A reader thread turns touch frames into callbacks on the
asyncio loop and notices when the display restarts (it then boots at 115200 and
shows its own page again, so the canvas must be set up anew).
"""

import asyncio
import logging
import queue
import struct
import threading
import time
from typing import Callable, List, Optional

import serial

END = b"\xff\xff\xff"
TOUCH_XY = 0x67
STARTUP = 0x88  # sent by the stock HMI's Program.s at power-up
SENDME = 0x66  # answer to `sendme` (current page), used as a flow-control marker
WINDOW = 900  # bytes in flight before waiting for the display to catch up

FAILURES = {
    0x00: "invalid instruction", 0x02: "invalid component", 0x03: "invalid page", 0x04: "invalid picture",
    0x05: "invalid font", 0x1A: "invalid variable", 0x1B: "invalid operation", 0x1C: "assignment failed",
    0x1E: "invalid parameter count", 0x1F: "io failed", 0x20: "escape character", 0x23: "name too long",
    0x24: "serial buffer overflow",
}


class SerialLink:
    def __init__(self, device: str, fast: int = 921600, slow: int = 115200, page: str = "logo"):
        self.device = device
        self.fast = fast
        self.slow = slow
        self.page = page
        self.port: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self.buf = b""
        self.on_touch: Callable[[int, int, bool], None] = lambda x, y, pressed: None
        self.on_restart: Callable[[], None] = lambda: None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.model = ""
        self.running = False
        self.errors = 0
        self.outbox: "queue.Queue[bytes]" = queue.Queue()
        self.synced = threading.Event()

    # --- setup (blocking; run in an executor) ---------------------------------

    def _frames(self, wait: float) -> List[bytes]:
        end = time.time() + wait
        out = []
        while True:
            self.buf += self.port.read(256)
            while END in self.buf:
                frame, self.buf = self.buf.split(END, 1)
                if frame:
                    out.append(frame)
            if time.time() >= end:
                return out

    def _write(self, cmd: str):
        self.port.write(cmd.encode("ascii", "replace") + END)

    def _alive(self) -> bool:
        self.port.reset_input_buffer()
        self.buf = b""
        self._write("")
        self._frames(0.08)
        self._write("connect")
        for frame in self._frames(0.4):
            if frame.startswith(b"comok"):
                self.model = frame.decode("latin-1")
                return True
        return False

    def open(self):
        """Find the display, raise the baud rate (temporarily) and turn `page` into a canvas."""
        with self.lock:
            if self.port is None:
                self.port = serial.Serial(self.device, self.slow, timeout=0.02)
            for baud in (self.fast, self.slow):
                self.port.baudrate = baud
                if self._alive():
                    break
            else:
                raise IOError("display on %s does not answer" % self.device)
            if self.port.baudrate != self.fast:
                self._write("baud=%d" % self.fast)  # `bauds=` would be saved in the display
                self.port.flush()
                time.sleep(0.1)
                self.port.baudrate = self.fast
                if not self._alive():
                    self.port.baudrate = self.slow
                    raise IOError("display lost after switching to %d baud" % self.fast)
            for cmd in ("bkcmd=2", "page %s" % self.page, "tm0.en=0", "sendxy=1", "thsp=0", "thup=1"):
                self._write(cmd)
                time.sleep(0.03)
            self._frames(0.2)  # the logo page prints 0x91 on load
            logging.info("canvas display ready: %s at %d baud", self.model, self.port.baudrate)

    # --- runtime ---------------------------------------------------------------

    def write(self, cmd: str):
        """Queue a command; the writer thread paces them so the display's buffer never overflows."""
        self.outbox.put(cmd.encode("ascii", "replace") + END)

    def start(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.running = True
        threading.Thread(target=self._reader, name="canvas-reader", daemon=True).start()
        threading.Thread(target=self._writer, name="canvas-writer", daemon=True).start()

    def _writer(self):
        in_flight = 0
        while self.running:
            data = self.outbox.get()
            batch = [data]
            while len(batch) < 64:  # coalesce what is already queued into one write
                try:
                    batch.append(self.outbox.get_nowait())
                except queue.Empty:
                    break
            for item in batch:
                if in_flight + len(item) > WINDOW:
                    self._sync()
                    in_flight = 0
                try:
                    self.port.write(item)
                except serial.SerialException as e:
                    logging.error("display write failed: %s", e)
                in_flight += len(item)
            if self.outbox.empty() and in_flight:
                self._sync()
                in_flight = 0

    def _sync(self):
        """Wait until the display has executed everything sent so far."""
        self.synced.clear()
        try:
            self.port.write(b"sendme" + END)
        except serial.SerialException:
            return
        if not self.synced.wait(0.5):
            logging.debug("display sync timed out")

    def _reader(self):
        while self.running:
            with self.lock:
                try:
                    frames = self._frames(0.0)
                except serial.SerialException as e:
                    logging.error("display read failed: %s", e)
                    frames = []
            for frame in frames:
                self._dispatch(frame)
            time.sleep(0.005)

    def _dispatch(self, frame: bytes):
        kind = frame[0]
        if kind == SENDME:
            self.synced.set()
        elif kind == TOUCH_XY and len(frame) == 6:
            x, y, ev = struct.unpack(">HHB", frame[1:])
            self.loop.call_soon_threadsafe(self.on_touch, x, y, bool(ev))
        elif kind == STARTUP or frame.endswith(b"\x88") or frame.startswith(b"\x00\x00\x00"):
            logging.warning("display restarted, setting the canvas up again")
            self.loop.call_soon_threadsafe(self.on_restart)
        elif kind in FAILURES:
            self.errors += 1
            logging.warning("display: %s", FAILURES[kind])
        elif kind != 0x91:
            logging.debug("display sent %s", frame.hex())
