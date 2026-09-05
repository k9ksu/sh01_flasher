# sh01-flasher

Cross-platform (Windows / Linux / Raspberry Pi) Python tool to raise the
temperature ceiling on a **Sovol / Comgrow SH01 filament dryer** and flash it
over a $10 USB-serial adapter. No Windows-only vendor ISP tool, no debug probe.

The SH01 runs an HDSC **HC32F005** Cortex-M0+ whose factory ROM bootloader
speaks a simple UART protocol over the pads silkscreened as SWD. This tool
implements that protocol directly.

<img width="490" alt="SH01 Dryer Flasher GUI" src="https://github.com/user-attachments/assets/f6b68e06-a686-4e40-b54e-fcae6685e2f0" />

## What you need

- DSD TECH **SH-U09C5** (FT232RL) USB-serial adapter, jumper set to **3.3 V**.
  RTS must be broken out — it drives the MCU reset. Other adapters known to
  work or not are listed in [rcambrj/sovol-dryer-firmware](https://github.com/rcambrj/sovol-dryer-firmware).
- Python 3.9+ with `pyserial` (`pip install -r requirements.txt`)
- The stock v2 firmware (`fw-v2-base.hex`) is included as the patch base.
  If it's ever missing, the GUI and CLI offer to re-download it
  (checksum-verified); `python get_firmware.py` does the same.

## Wiring

| SH01 J1 pad | adapter pin |
|-------------|-------------|
| 3V3         | VCC (3.3 V) |
| GND         | GND         |
| SWDIO       | TXD         |
| SWDCK       | RXD         |
| NRST        | RTS         |

The dryer is powered from the adapter's 3.3 V during flashing. **Unplug it
from mains for the whole session**, and unplug the adapter before powering
the dryer back up — opening the COM port toggles RTS, which resets the MCU.

## Use

GUI:

    python gui.py

CLI:

    python cli.py COM5 --temp 70          # Windows
    python cli.py /dev/ttyUSB0 --temp 70  # Linux / Pi

Both patch two values in the stock v2 image and run the full sequence:
reset → handshake → upload RAM flash driver → chip erase → blank check →
page writes → reboot. About a minute at 9600 baud.

| parameter | stock | what it is |
|-----------|-------|------------|
| ceiling (`--temp`) | 50 °C | wraparound ceiling of the front-panel temperature button — cycle the button up to reach the new maximum |
| HH trip (`--hh`) | 53 °C | chamber over-temperature fault: heater off, beeper on, display shows **HH**. This is the firmware's **only** high-temperature guard. |

Stock firmware trips HH at 53 °C, so raising the ceiling alone gets you a
fault in the mid-50s. By default the trip follows the ceiling (+5 °C); untick
"auto" in the GUI or pass `--hh` to set it yourself. Either way you have
moved the safety limit — see Hardware notes.

The stock v2 image also allows up to 48 h runtime (v1 stopped at 24 h);
that comes with the base image, not from a patch.

The GUI's **Tools** menu also has: a link probe (baud sweep), an adapter
loopback test, base-firmware download/verify, export of the patched `.hex`
(usable with the vendor ISP tool), and a byte-level diff against stock.

## If it doesn't talk

    python probe.py COM5              # sweep bauds, show what the chip says
    python probe.py COM5 --loopback   # adapter self-test (jumper TXD-RXD)

The probe output tells you which of three things is wrong: the bootloader
answered at some baud (fix the baud), RX saw a break during reset but no
answer (reset and RX are wired, TX or baud is off), or nothing at all
(power / TX-RX swap / reset not reaching NRST).

## Findings worth knowing

Two things differ from the HC32L110 reference implementation this was
ported from, and both cost an afternoon:

- **The SH01 bootloader runs at 9600 baud**, not 115200.
- The blank-check command's page-size field is **4 bytes** (the reference
  passes a C# `int`), not 2 like the page-write length field. A 2-byte
  field is silently ignored by the flash driver.

Both parameters were located by disassembling fw-v2.hex (Cortex-M0+ Thumb,
via capstone) rather than guessing:

- `0x2C8E` is the immediate in a `cmp r1, #50` — the button wraparound.
  Patching it reproduces the community "70C" hex byte-for-byte.
- `0x2720` is a 32-bit literal-pool constant (530, tenths of a degree) used
  by the fault classifier at `0x26C0`, which writes fault code 4 when the
  chamber reading is at or above it. The same function raises code 3 for a
  reading below −10 °C and code 1 on the raw-ADC sentinels 1499/999 (open or
  shorted thermistor); those are left untouched.

The patcher refuses to run unless the base image carries the stock values at
both offsets, so it can't silently mangle a different firmware lineage.
The community "72h" runtime variants differ in ~9 other bytes that look like
packed timer constants; the runtime limit isn't exposed here yet.

## Hardware notes

Q4 (SOT-23 MOSFET) is the only heater switch and has no heatsink copper.
Higher setpoints mean a higher heater duty cycle; check it after the first
long run. The stock 40 W heater may plateau below a high setpoint regardless.
Once the HH trip is raised there is no firmware limit protecting the
enclosure or the filament — the chamber goes wherever the heater can take it.

## Credits

- Protocol and RAM flash driver: [jeffreyabecker/hc32.tool](https://github.com/jeffreyabecker/hc32.tool) (MIT)
- Pinout, adapter compatibility, and firmware images: [rcambrj/sovol-dryer-firmware](https://github.com/rcambrj/sovol-dryer-firmware)

## License

MIT. `m_flash.hc005` is redistributed from hc32.tool under its MIT license.
`fw-v2-base.hex` is Sovol's stock firmware, included unmodified so the tool
works standalone (SHA-256
`48f19f5310733296f7bec79a53382579969b921d1846a1a37d87b07fd79603d3`);
`get_firmware.py` re-fetches it from rcambrj/sovol-dryer-firmware.
