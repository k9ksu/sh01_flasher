import serial, time
s = serial.Serial("COM5", 115200)
s.dtr = False; s.rts = False
input("Meter on NRST vs GND. Press Enter to assert RTS for 5 s...")
s.rts = True; s.dtr = True
time.sleep(5)
s.rts = False; s.dtr = False
print("released")