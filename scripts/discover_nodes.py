import argparse
import os
import re
import shutil
import sys
import time

import serial
import serial.tools.list_ports

CP210X_VID = 0x10C4
CP210X_PID = 0xEA60

# Coupled to the ESP-IDF log tag in edge-node/src/main.c (line 48).
# Same pattern used in edge-node/test/test_on_device.py.
NODE_ID_RE = re.compile(r"main: node_id=(\d+)")


def find_esp32_ports() -> list:
    return [
        p for p in serial.tools.list_ports.comports()
        if p.vid == CP210X_VID and p.pid == CP210X_PID
    ]


def read_node_id(port_device: str, timeout: float) -> int | None:
    with serial.Serial(port_device, 115200, timeout=1) as ser:
        ser.setDTR(False)
        time.sleep(0.1)
        ser.setDTR(True)
        deadline = time.time() + timeout
        while True:
            line = ser.readline().decode(errors="replace")
            m = NODE_ID_RE.search(line)
            if m:
                return int(m.group(1))
            if time.time() >= deadline:
                return None


def create_symlinks(mapping: dict, path: str):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    for node_id, device in mapping.items():
        os.symlink(device, os.path.join(path, str(node_id)))


def main():
    parser = argparse.ArgumentParser(description="Discover ESP32 sensor nodes on USB")
    parser.add_argument("path", nargs="?", default="/tmp/shrine/node")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    ports = find_esp32_ports()
    if not ports:
        print("error: no CP210x devices found", file=sys.stderr)
        sys.exit(1)

    mapping = {}
    seen_ids = {}
    duplicate = False

    for port in ports:
        try:
            node_id = read_node_id(port.device, timeout=args.timeout)
        except serial.SerialException as e:
            print(f"warning: {port.device}: {e}", file=sys.stderr)
            continue
        if node_id is None:
            continue
        if node_id in seen_ids:
            print(
                f"error: duplicate node_id={node_id} on {seen_ids[node_id]} and {port.device}",
                file=sys.stderr,
            )
            duplicate = True
        else:
            seen_ids[node_id] = port.device
            mapping[node_id] = port.device

    if duplicate:
        sys.exit(1)

    if not mapping:
        print("error: no nodes responded within timeout", file=sys.stderr)
        sys.exit(1)

    create_symlinks(mapping, args.path)

    for node_id, device in sorted(mapping.items()):
        print(f"node {node_id} -> {device}")


if __name__ == "__main__":
    main()
