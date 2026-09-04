#!/usr/bin/env python3
"""
Command-line flasher.

    python cli.py COM5 --temp 70
    python cli.py /dev/ttyUSB0 --temp 90 --base fw-v2-base.hex
"""
import argparse
import os
import sys

from hexpatch import parse_ihex, apply_params, Params
from hc32isp import HC32Programmer

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    ap = argparse.ArgumentParser(description="Flash a Sovol SH01 dryer with a patched temperature ceiling.")
    ap.add_argument("port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--temp", type=int, required=True, help="target temperature ceiling in C (0-99)")
    ap.add_argument("--base", default=os.path.join(HERE, "fw-v2-base.hex"), help="stock v2 firmware hex")
    ap.add_argument("--shim", default=os.path.join(HERE, "m_flash.hc005"), help="RAM flash driver")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--no-blank-check", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.base):
        sys.exit(f"{args.base} not found -- run get_firmware.py first")

    firmware = apply_params(parse_ihex(args.base), Params(temp_c=args.temp))
    with open(args.shim, "rb") as f:
        shim = f.read()

    def progress(done: int, total: int) -> None:
        print(f"\r  writing {done}/{total} bytes", end="", flush=True)
        if done >= total:
            print()

    prog = HC32Programmer(args.port, baud=args.baud)
    prog.flash(bytes(firmware), shim, progress=progress, do_blank_check=not args.no_blank_check)
    print(f"Target temperature ceiling is now {args.temp} C.")


if __name__ == "__main__":
    main()
