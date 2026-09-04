#!/usr/bin/env python3
"""
SH01 dryer parameter flasher -- simple GUI.

    pip install -r requirements.txt
    python get_firmware.py
    python gui.py

Wiring:
    adapter VCC (3.3V) -> board 3V3
    adapter GND        -> board GND
    adapter TX         -> board SWDIO
    adapter RX         -> board SWDCK
    adapter RTS        -> board NRST
Board must be unplugged from mains while flashing.
"""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import serial.tools.list_ports

from hexpatch import parse_ihex, apply_params, Params, OFFSET_TEMP_C
from hc32isp import HC32Programmer

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_HEX = os.path.join(HERE, "fw-v2-base.hex")
SHIM_PATH = os.path.join(HERE, "m_flash.hc005")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SH01 Dryer Flasher")
        self.geometry("560x420")
        self.log_queue: "queue.Queue[str]" = queue.Queue()

        row = ttk.Frame(self)
        row.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(row, text="Serial port:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, width=30, state="readonly")
        self.port_combo.pack(side="left", padx=6)
        ttk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left")
        self.refresh_ports()

        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=10, pady=4)
        ttk.Label(row2, text="Target temperature (\u00b0C):").pack(side="left")
        self.temp_var = tk.IntVar(value=50)
        self.temp_spin = ttk.Spinbox(row2, from_=0, to=99, textvariable=self.temp_var, width=6)
        self.temp_spin.pack(side="left", padx=6)
        ttk.Label(row2, text=f"(patches offset 0x{OFFSET_TEMP_C:04X} in the stock v2 firmware)").pack(side="left")

        row3 = ttk.Frame(self)
        row3.pack(fill="x", padx=10, pady=8)
        self.flash_btn = ttk.Button(row3, text="Flash", command=self.on_flash)
        self.flash_btn.pack(side="left")
        self.progress = ttk.Progressbar(row3, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(side="left", padx=10)

        self.log_box = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self.after(100, self._drain_log_queue)

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def log(self, msg: str):
        self.log_queue.put(msg)

    def _drain_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self._drain_log_queue)

    def on_flash(self):
        port = self.port_var.get()
        if not port:
            messagebox.showerror("No port", "Select a serial port first.")
            return
        temp = self.temp_var.get()
        if not messagebox.askyesno(
            "Confirm",
            f"Flash SH01 with target temperature {temp}\u00b0C on {port}?\n\n"
            "Make sure the dryer is unplugged from mains power.",
        ):
            return
        self.flash_btn.configure(state="disabled")
        self.progress["value"] = 0
        threading.Thread(target=self._flash_worker, args=(port, temp), daemon=True).start()

    def _flash_worker(self, port: str, temp: int):
        try:
            if not os.path.exists(BASE_HEX):
                raise FileNotFoundError("fw-v2-base.hex not found -- run get_firmware.py first")
            base = parse_ihex(BASE_HEX)
            patched = apply_params(base, Params(temp_c=temp))
            with open(SHIM_PATH, "rb") as f:
                shim = f.read()

            prog = HC32Programmer(port, log=self.log)

            def on_progress(done, total):
                self.progress["value"] = int(done * 100 / total)

            prog.flash(bytes(patched), shim, progress=on_progress)
            self.log(f"Done. Target temperature is now {temp}\u00b0C.")
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Flash failed", str(e))
        finally:
            self.flash_btn.configure(state="normal")


if __name__ == "__main__":
    App().mainloop()
