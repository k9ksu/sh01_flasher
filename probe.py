#!/usr/bin/env python3
"""
Diagnostics for the SH01 / HC32F005 ISP link.

    python probe.py COM5              # baud sweep + handshake
    python probe.py COM5 --loopback   # adapter self-test (jumper TXD to RXD first)

Reading the output:
  "11111111..."  the bootloader answered -- that baud works
  "00"           RX saw a break during reset: reset works, RX is wired, but
                 the bootloader did not answer at this baud
  "(nothing)"    RX never toggled -- check TX/RX, power, or reset
"""
import sys
import time

import serial

HANDSHAKE = bytes([0x18, 0xFF]) * 10
BAUDS = (9600, 19200, 38400, 57600, 115200, 128000, 230400, 256000)


def loopback(port: str) -> None:
    s = serial.Serial(port, 115200, timeout=0.5)
    s.write(b"hello")
    got = s.read(5)
    s.close()
    print(f"loopback -> {got!r}  ({'OK' if got == b'hello' else 'FAIL: jumper TXD to RXD on the adapter'})")


def try_baud(port: str, baud: int, window: float = 1.5) -> bytes:
    s = serial.Serial(port, baud, timeout=0.02)
    s.rts = True
    s.dtr = True
    time.sleep(0.010)
    s.reset_input_buffer()
    s.write(HANDSHAKE)
    s.flush()
    s.rts = False
    s.dtr = False
    got = bytearray()
    t0 = time.monotonic()
    while time.monotonic() - t0 < window:
        s.write(HANDSHAKE)
        got += s.read(64)
        if 0x11 in got:
            break
    s.close()
    return bytes(got)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    port = sys.argv[1]
    if "--loopback" in sys.argv:
        loopback(port)
        return
    found = None
    for baud in BAUDS:
        got = try_baud(port, baud)
        print(f"{baud:7d} -> {got.hex() or '(nothing)'}")
        if 0x11 in got and found is None:
            found = baud
    print()
    if found:
        print(f"Bootloader answers at {found} baud.")
    else:
        print("No bootloader response at any baud. See notes at top of this file.")


if __name__ == "__main__":
    main()
