#!/usr/bin/env python3
"""
SH01 dryer flasher -- GUI.

    pip install -r requirements.txt
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
import struct
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

import serial.tools.list_ports

from hexpatch import (parse_ihex, write_ihex, apply_params, check_base, Params,
                      OFFSET_TEMP_C, OFFSET_HH_TENTHS, STOCK_TEMP_C, STOCK_HH_C)
from hc32isp import HC32Programmer
import get_firmware
import probe
import risk

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_HEX = os.path.join(HERE, "fw-v2-base.hex")
SHIM_PATH = os.path.join(HERE, "m_flash.hc005")
HH_MARGIN = 5


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SH01 Dryer Flasher")
        self.geometry("620x480")
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.busy = False

        # ---- menu ----
        menubar = tk.Menu(self)
        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label="Probe link (baud sweep)", command=self.on_probe)
        tools.add_command(label="Adapter loopback test", command=self.on_loopback)
        tools.add_separator()
        tools.add_command(label="Download base firmware", command=self.on_download)
        tools.add_command(label="Verify base firmware", command=self.on_verify)
        tools.add_separator()
        tools.add_command(label="Export patched .hex...", command=self.on_export)
        tools.add_command(label="Show patch diff", command=self.on_diff)
        menubar.add_cascade(label="Tools", menu=tools)
        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Wiring", command=lambda: messagebox.showinfo("Wiring", __doc__.split("Wiring:")[1].strip()))
        menubar.add_cascade(label="Help", menu=helpm)
        self.config(menu=menubar)

        # ---- port ----
        row = ttk.Frame(self)
        row.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(row, text="Serial port:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, width=30, state="readonly")
        self.port_combo.pack(side="left", padx=6)
        ttk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left")
        self.refresh_ports()

        # ---- ceiling ----
        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=10, pady=4)
        ttk.Label(row2, text="Temperature ceiling (\u00b0C):").pack(side="left")
        self.temp_var = tk.IntVar(value=STOCK_TEMP_C)
        self.temp_spin = ttk.Spinbox(row2, from_=0, to=99, textvariable=self.temp_var, width=6,
                                     command=self.sync_hh)
        self.temp_spin.pack(side="left", padx=6)
        self.temp_spin.bind("<KeyRelease>", lambda e: self.sync_hh())
        ttk.Label(row2, text=f"(button wraparound, stock {STOCK_TEMP_C})").pack(side="left")

        # ---- HH ----
        row3 = ttk.Frame(self)
        row3.pack(fill="x", padx=10, pady=4)
        ttk.Label(row3, text="HH over-temp trip (\u00b0C):").pack(side="left")
        self.hh_var = tk.IntVar(value=STOCK_HH_C)
        self.hh_spin = ttk.Spinbox(row3, from_=0, to=150, textvariable=self.hh_var, width=6)
        self.hh_spin.pack(side="left", padx=6)
        self.hh_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text=f"auto (ceiling + {HH_MARGIN})", variable=self.hh_auto,
                        command=self.sync_hh).pack(side="left", padx=6)
        ttk.Label(row3, text=f"(stock {STOCK_HH_C})").pack(side="left")
        self.sync_hh()

        # ---- action ----
        row4 = ttk.Frame(self)
        row4.pack(fill="x", padx=10, pady=8)
        self.flash_btn = ttk.Button(row4, text="Flash", command=self.on_flash)
        self.flash_btn.pack(side="left")
        self.progress = ttk.Progressbar(row4, orient="horizontal", length=360, mode="determinate")
        self.progress.pack(side="left", padx=10)

        self.log_box = scrolledtext.ScrolledText(self, height=16, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self.after(100, self._drain_log_queue)
        self.after(300, self.startup_check)

    # ---------- helpers ----------
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def sync_hh(self):
        if self.hh_auto.get():
            try:
                self.hh_var.set(self.temp_var.get() + HH_MARGIN)
            except tk.TclError:
                pass
            self.hh_spin.configure(state="disabled")
        else:
            self.hh_spin.configure(state="normal")

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

    def need_port(self):
        port = self.port_var.get()
        if not port:
            messagebox.showerror("No port", "Select a serial port first.")
        return port

    def run_bg(self, fn, *args):
        if self.busy:
            messagebox.showwarning("Busy", "Another operation is still running.")
            return
        self.busy = True
        self.flash_btn.configure(state="disabled")

        def wrapper():
            try:
                fn(*args)
            except Exception as e:
                self.log(f"ERROR: {e}")
                messagebox.showerror("Failed", str(e))
            finally:
                self.busy = False
                self.flash_btn.configure(state="normal")
        threading.Thread(target=wrapper, daemon=True).start()

    def ensure_base(self) -> bool:
        """Return True if fw-v2-base.hex is present, offering to download it if not."""
        if os.path.exists(BASE_HEX):
            return True
        if messagebox.askyesno("Base firmware missing",
                               "fw-v2-base.hex is not in the flasher folder.\n\n"
                               "Download it now from rcambrj/sovol-dryer-firmware (GitHub)?"):
            try:
                get_firmware.download(BASE_HEX)
                self.log("Downloaded fw-v2-base.hex (sha256 verified).")
                return True
            except Exception as e:
                messagebox.showerror("Download failed", str(e))
        return False

    def startup_check(self):
        if not os.path.exists(BASE_HEX):
            self.log("Base firmware not found -- you'll be offered a download when you flash "
                     "(or use Tools > Download base firmware).")

    def build_patched(self):
        base = parse_ihex(BASE_HEX)
        return apply_params(base, Params(temp_c=self.temp_var.get(), hh_c=self.hh_var.get())), base

    # ---------- actions ----------
    def on_flash(self):
        port = self.need_port()
        if not port or not self.ensure_base():
            return
        temp, hh = self.temp_var.get(), self.hh_var.get()
        if hh <= temp and not messagebox.askyesno(
            "HH trip at or below ceiling",
            f"The HH trip ({hh}\u00b0C) is not above the ceiling ({temp}\u00b0C); the dryer will "
            "fault before it can reach the setpoint. Flash anyway?"):
            return
        if hh > STOCK_HH_C and not self.acknowledge_risk():
            return
        if not messagebox.askyesno(
            "Confirm",
            f"Flash SH01 on {port}?\n\n  ceiling {temp}\u00b0C\n  HH trip {hh}\u00b0C\n\n"
            "Make sure the dryer is unplugged from mains power."):
            return
        self.progress["value"] = 0
        self.run_bg(self._flash_worker, port, temp, hh)

    def acknowledge_risk(self) -> bool:
        """Modal: user must type the acknowledgement phrase to proceed."""
        dlg = tk.Toplevel(self)
        dlg.title("Raising the over-temperature trip")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        ttk.Label(dlg, text=risk.TEXT, justify="left", font=("TkDefaultFont", 10)).pack(padx=16, pady=(14, 8))
        ttk.Label(dlg, text=f"Type  {risk.PHRASE}  to continue:").pack(padx=16, anchor="w")
        var = tk.StringVar()
        entry = ttk.Entry(dlg, textvariable=var, width=32)
        entry.pack(padx=16, pady=(2, 10), anchor="w")
        entry.focus_set()
        result = {"ok": False}
        btns = ttk.Frame(dlg)
        btns.pack(padx=16, pady=(0, 14), anchor="e")
        ok = ttk.Button(btns, text="Continue", state="disabled",
                        command=lambda: (result.update(ok=True), dlg.destroy()))
        ok.pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right")
        var.trace_add("write", lambda *_: ok.configure(
            state="normal" if var.get().strip().upper() == risk.PHRASE else "disabled"))
        entry.bind("<Return>", lambda e: ok.invoke() if str(ok["state"]) == "normal" else None)
        self.wait_window(dlg)
        if result["ok"]:
            self.log("Risk acknowledgement accepted for HH above stock.")
        return result["ok"]

    def _flash_worker(self, port, temp, hh):
        patched, _ = self.build_patched()
        with open(SHIM_PATH, "rb") as f:
            shim = f.read()
        prog = HC32Programmer(port, log=self.log)

        def on_progress(done, total):
            self.progress["value"] = int(done * 100 / total)
        prog.flash(bytes(patched), shim, progress=on_progress)
        self.log(f"Done. Ceiling {temp}\u00b0C, HH trip {hh}\u00b0C.")

    def on_probe(self):
        port = self.need_port()
        if not port:
            return
        self.log(f"--- probing {port}: baud sweep ---")

        def work():
            found = None
            for baud in probe.BAUDS:
                got = probe.try_baud(port, baud)
                self.log(f"  {baud:7d} -> {got.hex() or '(nothing)'}")
                if 0x11 in got and found is None:
                    found = baud
            if found:
                self.log(f"Bootloader answers at {found} baud.")
            else:
                self.log("No bootloader response. '00' = reset and RX work but no answer; "
                         "'(nothing)' = check TX/RX, power, or NRST wiring.")
        self.run_bg(work)

    def on_loopback(self):
        port = self.need_port()
        if not port:
            return
        if not messagebox.askokcancel("Loopback", "Disconnect the adapter from the dryer and jumper "
                                      "its TXD pin to its RXD pin, then press OK."):
            return

        def work():
            s = serial.Serial(port, 115200, timeout=0.5)
            s.write(b"hello")
            got = s.read(5)
            s.close()
            self.log(f"loopback -> {got!r}  {'OK' if got == b'hello' else 'FAIL'}")
        self.run_bg(work)

    def on_download(self):
        def work():
            get_firmware.download(BASE_HEX)
            self.log("Downloaded fw-v2-base.hex (sha256 verified).")
        self.run_bg(work)

    def on_verify(self):
        if not os.path.exists(BASE_HEX):
            self.log("fw-v2-base.hex not present.")
            return
        try:
            sha = get_firmware.sha256_of(BASE_HEX)
            base = parse_ihex(BASE_HEX)
            check_base(base)
            hh = struct.unpack_from("<I", base, OFFSET_HH_TENTHS)[0]
            self.log(f"fw-v2-base.hex: {len(base)} bytes, sha256 {sha[:16]}... "
                     f"{'(matches known)' if sha == get_firmware.SHA256 else '(UNKNOWN checksum)'}")
            self.log(f"  ceiling byte @0x{OFFSET_TEMP_C:04X} = {base[OFFSET_TEMP_C]}, "
                     f"HH word @0x{OFFSET_HH_TENTHS:04X} = {hh} ({hh/10:.1f} C)  -- stock values present")
        except Exception as e:
            self.log(f"verify failed: {e}")

    def on_export(self):
        if not self.ensure_base():
            return
        temp, hh = self.temp_var.get(), self.hh_var.get()
        path = filedialog.asksaveasfilename(defaultextension=".hex",
                                            initialfile=f"sh01-{temp}c-hh{hh}.hex",
                                            filetypes=[("Intel HEX", "*.hex")])
        if not path:
            return
        patched, _ = self.build_patched()
        write_ihex(path, patched)
        self.log(f"Exported {path} (ceiling {temp}, HH {hh}). Flashable with the vendor ISP tool too.")

    def on_diff(self):
        if not self.ensure_base():
            return
        patched, base = self.build_patched()
        diffs = [i for i in range(len(base)) if base[i] != patched[i]]
        self.log(f"Patch diff vs stock ({len(diffs)} bytes):")
        for i in diffs:
            self.log(f"  0x{i:04X}: {base[i]:02X} -> {patched[i]:02X}")


if __name__ == "__main__":
    App().mainloop()
