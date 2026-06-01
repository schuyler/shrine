#!/bin/sh
#
# Flash NVS partition from a CSV in the current directory's nvs/ folder.
#
# Usage: flash-nvs.sh <node_id> [port]
#   node_id: 0-3
#   port:    serial port (default: /dev/ttyUSB0)
#
# Requires: esptool and esp-idf-nvs-partition-gen (pip packages).
# Run from a project directory containing nvs/nodeN.csv files.

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <node_id> [port]" >&2
    exit 1
fi

NODE_ID="$1"
PORT="${2:-/dev/ttyUSB0}"
CSV="nvs/node${NODE_ID}.csv"
BIN="/tmp/nvs_node${NODE_ID}.bin"

if [ ! -f "$CSV" ]; then
    echo "Error: $CSV not found (run from a project directory with nvs/ folder)" >&2
    exit 1
fi

uv run python -m esp_idf_nvs_partition_gen generate "$CSV" "$BIN" 0x6000
uv run python -m esptool --port "$PORT" write_flash 0x9000 "$BIN"
rm -f "$BIN"
