# sh01-flasher

Cross-platform (Windows / Linux / Raspberry Pi) Python tool to raise the
temperature ceiling on a **Sovol / Comgrow SH01 filament dryer** and flash it
over a $10 USB-serial adapter. No Windows-only vendor ISP tool, no debug probe.

The SH01 runs an HDSC **HC32F005** Cortex-M0+ whose factory ROM bootloader
speaks a simple UART protocol over the pads silkscreened as SWD. This tool
implements that protocol directly.

## What you need

- DSD TECH **SH-U09C5** (FT232RL) USB-serial adapter, jumper set to **3.3 V**.
  RTS must be broken out — it drives the MCU reset. Other adapters known to
  work or not are listed in [rcambrj/sovol-dryer-firmware](https://github.com/rcambrj/sovol-dryer-firmware).
- Python 3.9+ with `pyserial` (`pip install -r requirements.txt`)
- The stock v2 firmware as patch base: `python get_firmware.py`

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

Both patch the single temperature byte in the stock v2 image and run the
full sequence: reset → handshake → upload RAM flash driver → chip erase →
blank check → page writes → reboot. About a minute at 9600 baud.

The patched byte is the wraparound ceiling of the front-panel temperature
button, so after flashing you cycle the button up to the new maximum.

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

The temperature offset (`0x2C8E` in the v2 image) was confirmed by byte-diff:
patching that single byte reproduces the community "70C" hex file exactly.
The community "72h" runtime variants differ in ~9 other bytes that look like
packed timer constants; the runtime limit isn't exposed here yet.

## Hardware notes

Q4 (SOT-23 MOSFET) is the only heater switch and has no heatsink copper.
Higher setpoints mean a higher heater duty cycle; check it after the first
long run. The stock 40 W heater may plateau below a high setpoint regardless.

## Credits

- Protocol and RAM flash driver: [jeffreyabecker/hc32.tool](https://github.com/jeffreyabecker/hc32.tool) (MIT)
- Pinout, adapter compatibility, and firmware images: [rcambrj/sovol-dryer-firmware](https://github.com/rcambrj/sovol-dryer-firmware)

## License

MIT. `m_flash.hc005` is redistributed from hc32.tool under its MIT license.
The Sovol firmware image is not bundled; `get_firmware.py` fetches it.
