#!/bin/bash
# Flash WLED firmware to an ESP32.
#
# Usage: ./install-wled.sh <firmware.bin>
#
# Requires: bootloader (esp32_bootloader_v4.bin) and partition table
# (partitions.bin) in the same directory. Generate partitions.bin from
# partitions.csv with gen_esp32part.py if missing.
#
# Flash layout:
#   0x0000  bootloader
#   0x8000  partition table
#   0x10000 application firmware

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTLOADER="$SCRIPT_DIR/esp32_bootloader_v4.bin"
PARTITIONS="$SCRIPT_DIR/partitions.bin"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <firmware.bin>" >&2
    exit 1
fi

FIRMWARE="$1"

for f in "$BOOTLOADER" "$PARTITIONS" "$FIRMWARE"; do
    if [ ! -f "$f" ]; then
        echo "Missing: $f" >&2
        exit 1
    fi
done

echo "Erasing flash..."
uv run esptool erase-flash

echo "Flashing bootloader..."
uv run esptool write-flash 0x0 "$BOOTLOADER"

echo "Flashing partition table..."
uv run esptool write-flash 0x8000 "$PARTITIONS"

echo "Flashing firmware..."
uv run esptool write-flash 0x10000 "$FIRMWARE"

echo "Done. Look for WLED-AP in your WiFi networks."
