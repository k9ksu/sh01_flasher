"""
Pure-Python client for the HDSC HC32L110 / HC32F005 UART ISP bootloader,
ported from github.com/jeffreyabecker/hc32.tool (C#).

Wiring (per github.com/rcambrj/sovol-dryer-firmware):
    adapter VCC (3.3V) -> board 3V3
    adapter GND        -> board GND
    adapter TX         -> board SWDIO
    adapter RX         -> board SWDCK
    adapter RTS        -> board NRST

The board must NOT be connected to mains power while this runs.
"""
from __future__ import annotations
import struct
import time
from typing import Callable, Optional

import serial

RAM_SHIM_BASE = 0x20000000
DEFAULT_WRITE_PAGE = 64
DEFAULT_BLANKCHECK_PAGE = 512
DEFAULT_BLANKCHECK_PAGES = 64  # 64 * 512 = 32KB, full flash


class IspError(RuntimeError):
    pass


def checksum8(data: bytes) -> int:
    return sum(data) & 0xFF


def with_checksum(data: bytes) -> bytes:
    return data + bytes([checksum8(data)])


class HC32Programmer:
    def __init__(self, port: str, baud: int = 9600, log: Callable[[str], None] = print):
        self.log = log
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.timeout = 0.05

    def open(self):
        if self.ser.is_open:
            self.ser.close()
        self.ser.open()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def _flush(self):
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def _write(self, data: bytes):
        self._flush()
        self.ser.write(data)

    def _read(self, n: int, timeout: float = 5.0) -> bytes:
        start = time.monotonic()
        buf = bytearray()
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf += chunk
            if time.monotonic() - start > timeout:
                raise IspError(f"expected {n} bytes, got {len(buf)}: {bytes(buf).hex()}")
        return bytes(buf)

    def reset_mcu(self):
        if not self.ser.is_open:
            self.open()
        self.log("Resetting MCU...")
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.010)
        self.ser.rts = False
        self.ser.dtr = False
        time.sleep(0.100)

    def handshake(self):
        self.log("Handshaking with bootloader...")
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.010)
        self._flush()
        self.ser.write(bytes([0x18, 0xFF]) * 10)
        self.ser.rts = False
        self.ser.dtr = False
        time.sleep(0.100)
        resp = self._read(1, timeout=5.0)
        if resp[0] != 0x11:
            raise IspError(f"handshake failed, got {resp.hex()}")
        self._flush()
        self.log("Handshake OK")

    def download_shim(self, shim: bytes, ram_base: int = RAM_SHIM_BASE):
        self.log("Uploading RAM flash-driver shim...")
        header = struct.pack("<BII", 0x00, ram_base, len(shim))
        self._write(with_checksum(header))
        r = self._read(1)
        if r[0] != 0x01:
            raise IspError("shim header rejected")

        self._write(with_checksum(shim))
        r = self._read(1)
        if r[0] != 0x01:
            raise IspError("shim body rejected")

        self.log("Starting shim...")
        self._write(bytes([0xC0, 0, 0, 0, 0, 0, 0, 0, 0, 0xC0]))
        self._read(11)
        self.log("Shim running")

    def erase_chip(self):
        self.log("Erasing chip...")
        msg = with_checksum(bytes([0x49, 0x02, 0, 0, 0, 0, 0, 0]))
        self._write(msg)
        r = self._read(9)
        if r[0] != 0x49 or checksum8(r[:8]) != r[8]:
            raise IspError(f"erase failed: {r.hex()}")
        self.log("Erase OK")

    def blank_check_segment(self, address: int, page_size: int = DEFAULT_BLANKCHECK_PAGE):
        header = bytes([0x49, 0x07]) + struct.pack("<I", address) + bytes([4, 0]) + struct.pack("<I", page_size)
        self._write(with_checksum(header))
        r = self._read(10)
        if r[0] != 0x49 or r[6] != 1 or r[7] > 0 or checksum8(r[:9]) != r[9]:
            raise IspError(f"blank check failed at 0x{address:08X}: {r.hex()}")

    def blank_check_full(self, start: int = 0, page_size: int = DEFAULT_BLANKCHECK_PAGE,
                          page_count: int = DEFAULT_BLANKCHECK_PAGES):
        self.log("Blank-checking erased flash...")
        for i in range(page_count):
            self.blank_check_segment(start + i * page_size, page_size)
        self.log("Blank check OK")

    def write_page(self, address: int, data: bytes):
        header = bytes([0x49, 0x04]) + struct.pack("<I", address) + struct.pack("<H", len(data))
        self._write(with_checksum(header + data))
        r = self._read(9)
        if r[0] != 0x49 or checksum8(r[:8]) != r[8]:
            raise IspError(f"page write failed at 0x{address:08X}: {r.hex()}")

    def write_binary(self, address: int, data: bytes, page_size: int = DEFAULT_WRITE_PAGE,
                      progress: Optional[Callable[[int, int], None]] = None):
        total = len(data)
        for i in range(0, total, page_size):
            chunk = data[i:i + page_size]
            self.write_page(address + i, chunk)
            if progress:
                progress(i + len(chunk), total)

    def reboot_to_app(self):
        self.log("Rebooting into application firmware...")
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.010)
        self.ser.rts = False
        self.ser.dtr = False
        time.sleep(0.100)

    def flash(self, firmware: bytes, shim: bytes, page_size: int = DEFAULT_WRITE_PAGE,
              progress: Optional[Callable[[int, int], None]] = None,
              do_blank_check: bool = True):
        self.open()
        try:
            self.reset_mcu()
            self.handshake()
            self.download_shim(shim)
            self.erase_chip()
            if do_blank_check:
                self.blank_check_full()
            self.write_binary(0x00000000, firmware, page_size=page_size, progress=progress)
            self.reboot_to_app()
            self.log("Flash complete.")
        finally:
            self.close()
