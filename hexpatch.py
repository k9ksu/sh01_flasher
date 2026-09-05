"""
Intel HEX loader + parameter patcher for the Sovol SH01 dryer firmware
(HC32F005, stock v2 image lineage).

Patchable parameters, located by disassembly of fw-v2.hex:

  OFFSET_TEMP_C (0x2C8E), 1 byte, degrees C
      Immediate in `cmp r1, #50` -- the front-panel temperature button's
      wraparound ceiling. Stock 50.

  OFFSET_HH_TENTHS (0x2720), 4 bytes little-endian, tenths of a degree C
      Literal-pool constant compared against the chamber temperature in the
      fault classifier at 0x26C0. At or above it, fault code 4 is raised and
      the display shows "HH", the heater is cut and the beeper sounds.
      Stock 530 (53.0 C). This is the only high-temperature guard in the
      firmware, so raise it deliberately.
"""
from __future__ import annotations
import struct
from dataclasses import dataclass

OFFSET_TEMP_C = 0x2C8E
OFFSET_HH_TENTHS = 0x2720

STOCK_TEMP_C = 50
STOCK_HH_C = 53


def parse_ihex(path: str) -> bytearray:
    mem: dict[int, int] = {}
    base = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            raw = bytes.fromhex(line[1:])
            length, addr_hi, addr_lo, rtype = raw[0], raw[1], raw[2], raw[3]
            addr = (addr_hi << 8) | addr_lo
            data = raw[4:4 + length]
            if rtype == 0x04:
                base = (data[0] << 8 | data[1]) << 16
            elif rtype == 0x00:
                full = base + addr
                for i, b in enumerate(data):
                    mem[full + i] = b
    size = max(mem) + 1
    buf = bytearray(size)
    for a, v in mem.items():
        buf[a] = v
    return buf


def write_ihex(path: str, data: bytes, bytes_per_line: int = 16) -> None:
    lines = []
    for offset in range(0, len(data), bytes_per_line):
        chunk = data[offset:offset + bytes_per_line]
        record = bytes([len(chunk), (offset >> 8) & 0xFF, offset & 0xFF, 0x00]) + chunk
        checksum = (-sum(record)) & 0xFF
        lines.append(":" + record.hex().upper() + f"{checksum:02X}")
    lines.append(":00000001FF")
    with open(path, "w", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")


@dataclass
class Params:
    temp_c: int = STOCK_TEMP_C   # button ceiling, degrees C
    hh_c: int = STOCK_HH_C       # over-temperature trip, degrees C


def check_base(base: bytes) -> None:
    """Refuse to patch an image that doesn't carry the stock values where we expect them."""
    if len(base) <= OFFSET_TEMP_C:
        raise ValueError("image too small -- not the stock v2 firmware")
    if base[OFFSET_TEMP_C] != STOCK_TEMP_C:
        raise ValueError(f"byte at 0x{OFFSET_TEMP_C:04X} is {base[OFFSET_TEMP_C]}, expected {STOCK_TEMP_C}")
    hh = struct.unpack_from("<I", base, OFFSET_HH_TENTHS)[0]
    if hh != STOCK_HH_C * 10:
        raise ValueError(f"word at 0x{OFFSET_HH_TENTHS:04X} is {hh}, expected {STOCK_HH_C * 10}")


def apply_params(base: bytes, params: Params) -> bytearray:
    check_base(base)
    if not (0 <= params.temp_c <= 99):
        raise ValueError("temp_c must be 0-99 (single byte, two-digit display)")
    if not (0 <= params.hh_c <= 150):
        raise ValueError("hh_c must be 0-150")
    out = bytearray(base)
    out[OFFSET_TEMP_C] = params.temp_c
    struct.pack_into("<I", out, OFFSET_HH_TENTHS, params.hh_c * 10)
    return out


if __name__ == "__main__":
    import sys
    t = int(sys.argv[1]) if len(sys.argv) > 1 else STOCK_TEMP_C
    h = int(sys.argv[2]) if len(sys.argv) > 2 else STOCK_HH_C
    base = parse_ihex("fw-v2-base.hex")
    patched = apply_params(base, Params(temp_c=t, hh_c=h))
    write_ihex("patched.hex", patched)
    print(f"Wrote patched.hex: ceiling {t} C, HH trip {h} C")
