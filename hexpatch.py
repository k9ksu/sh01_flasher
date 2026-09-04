"""
Intel HEX loader + parameter patcher for the Sovol SH01 dryer firmware
(HC32F005 / HC32L110-compatible).

OFFSET_TEMP_C (0x2C8E): single byte, raw degrees Celsius, in the
fw-v2.hex lineage. Changing it from 0x32 (50) to 0x46 (70) is the
entire diff between stock fw-v2.hex and a "70C" variant.
"""
from __future__ import annotations
from dataclasses import dataclass

OFFSET_TEMP_C = 0x2C8E


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
    temp_c: int = 50


def apply_params(base: bytes, params: Params) -> bytearray:
    if not (0 <= params.temp_c <= 99):
        raise ValueError("temp_c must be 0-99 (single raw byte field)")
    out = bytearray(base)
    out[OFFSET_TEMP_C] = params.temp_c
    return out


if __name__ == "__main__":
    import sys
    base = parse_ihex("fw-v2-base.hex")
    patched = apply_params(base, Params(temp_c=int(sys.argv[1]) if len(sys.argv) > 1 else 50))
    write_ihex("patched.hex", patched)
    print(f"Wrote patched.hex, temp byte = {patched[OFFSET_TEMP_C]}")
