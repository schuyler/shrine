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

# Generate partition table binary
PARTITIONS_CSV="$SCRIPT_DIR/partitions.csv"
PARTITIONS_BIN="$SCRIPT_DIR/partitions.bin"
if [ -f "$PARTITIONS_CSV" ]; then
    echo "Generating partition table..."
    uv run python "$SCRIPT_DIR/gen_esp32part.py" "$PARTITIONS_CSV" "$PARTITIONS_BIN"
fi

echo "Done. Flash with: ./install-wled.sh WLED_${VERSION}_ESP32.bin"
