#!/usr/bin/env python3
"""
Command-line flasher.

    python cli.py COM5 --temp 70            # HH defaults to 75
    python cli.py COM5 --temp 70 --hh 80
    python cli.py /dev/ttyUSB0 --temp 90 --base fw-v2-base.hex
"""
import argparse
import os
import sys

from hexpatch import parse_ihex, apply_params, Params, STOCK_HH_C
from hc32isp import HC32Programmer

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    ap = argparse.ArgumentParser(description="Flash a Sovol SH01 dryer with a patched temperature ceiling.")
    ap.add_argument("port", help="serial port, e.g. COM5 or /dev/ttyUSB0")
    ap.add_argument("--temp", type=int, required=True, help="button temperature ceiling in C (0-99)")
    ap.add_argument("--hh", type=int, default=None,
                    help=f"HH over-temperature trip in C (default: ceiling + 5; stock {STOCK_HH_C})")
    ap.add_argument("--base", default=os.path.join(HERE, "fw-v2-base.hex"), help="stock v2 firmware hex")
    ap.add_argument("--shim", default=os.path.join(HERE, "m_flash.hc005"), help="RAM flash driver")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--no-blank-check", action="store_true")
    args = ap.parse_args()

    if args.hh is None:
        args.hh = args.temp + 5
    if not os.path.exists(args.base):
        print(f"{args.base} not found -- downloading...")
        import get_firmware
        get_firmware.download(args.base)

    if args.hh <= args.temp:
        print(f"warning: HH trip ({args.hh} C) is not above the ceiling ({args.temp} C); the dryer will fault before reaching the setpoint")
    firmware = apply_params(parse_ihex(args.base), Params(temp_c=args.temp, hh_c=args.hh))
    with open(args.shim, "rb") as f:
        shim = f.read()

    def progress(done: int, total: int) -> None:
        print(f"\r  writing {done}/{total} bytes", end="", flush=True)
        if done >= total:
            print()

    prog = HC32Programmer(args.port, baud=args.baud)
    prog.flash(bytes(firmware), shim, progress=progress, do_blank_check=not args.no_blank_check)
    print(f"Ceiling {args.temp} C, HH trip {args.hh} C.")


if __name__ == "__main__":
    main()
