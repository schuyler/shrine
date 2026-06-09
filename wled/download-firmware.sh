#!/bin/bash
# Download WLED firmware and bootloader for ESP32.
#
# Usage: ./download-firmware.sh [version]
#
# Default version: 16.0.0
# Downloads to the same directory as this script.

set -euo pipefail

VERSION="${1:-16.0.0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BOOTLOADER_URL="https://github.com/wled/WLED/releases/download/v0.13.1/esp32_bootloader_v4.bin"
FIRMWARE_URL="https://github.com/wled/WLED/releases/download/v${VERSION}/WLED_${VERSION}_ESP32.bin"

echo "Downloading bootloader..."
wget -q --show-progress -O "$SCRIPT_DIR/esp32_bootloader_v4.bin" "$BOOTLOADER_URL"

echo "Downloading WLED ${VERSION} firmware..."
wget -q --show-progress -O "$SCRIPT_DIR/WLED_${VERSION}_ESP32.bin" "$FIRMWARE_URL"

# Generate partition table binary if gen_esp32part.py is available
PARTITIONS_CSV="$SCRIPT_DIR/partitions.csv"
PARTITIONS_BIN="$SCRIPT_DIR/partitions.bin"
if [ -f "$PARTITIONS_CSV" ] && [ ! -f "$PARTITIONS_BIN" ]; then
    GEN_PART=$(find ~/.platformio -name 'gen_esp32part.py' 2>/dev/null | head -1)
    if [ -n "$GEN_PART" ]; then
        echo "Generating partition table..."
        uv run python "$GEN_PART" "$PARTITIONS_CSV" "$PARTITIONS_BIN"
    else
        echo "Warning: gen_esp32part.py not found. Generate partitions.bin manually." >&2
    fi
fi

echo "Done. Flash with: ./install-wled.sh WLED_${VERSION}_ESP32.bin"
