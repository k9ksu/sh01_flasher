import serial, time
HS = bytes([0x18, 0xFF]) * 10
for baud in (9600, 19200, 38400, 57600, 115200, 128000, 230400, 256000):
    s = serial.Serial("COM5", baud, timeout=0.02)
    s.rts = True; s.dtr = True; time.sleep(0.01)
    s.reset_input_buffer(); s.write(HS); s.flush()
    s.rts = False; s.dtr = False
    got = bytearray(); t0 = time.monotonic()
    while time.monotonic() - t0 < 1.5:
        s.write(HS); got += s.read(64)
        if 0x11 in got: break
    s.close()
    print(f"{baud:7d} -> {got.hex() or '(nothing)'}")