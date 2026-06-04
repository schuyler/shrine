"""Capture ESP32 boot log after DTR reset. Diagnostic script."""
import serial
import time

s = serial.Serial("/dev/ttyUSB0", 115200, timeout=1)
s.setDTR(False)
time.sleep(0.1)
s.setDTR(True)
deadline = time.time() + 30
i = 0
while time.time() < deadline:
    line = s.readline()
    if line:
        i += 1
        text = line.decode(errors="replace").rstrip()
        print(f"{i}: {text}")
        if text.startswith("mag="):
            break
else:
    print(f"TIMEOUT after {i} lines, no node_id found")
s.close()
