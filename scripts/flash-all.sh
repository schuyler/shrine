#!/bin/sh
#
# Discover all connected ESP32 nodes, then flash firmware and NVS to each.
#
# Usage: flash-all.sh [--nvs-only] [--firmware-only]
#
# Runs discover_nodes.py to find nodes and create /tmp/shrine/node/{id}
# symlinks, builds firmware once, then flashes each node's firmware and
# NVS partition.  Run from the repository root.
#
# Requires: uv, platformio, esptool, esp-idf-nvs-partition-gen.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NODE_DIR="/tmp/shrine/node"
EDGE_DIR="$REPO_DIR/edge-node"

flash_nvs=true
flash_firmware=true

for arg in "$@"; do
    case "$arg" in
        --nvs-only)      flash_firmware=false ;;
        --firmware-only)  flash_nvs=false ;;
        *)
            echo "Usage: $0 [--nvs-only] [--firmware-only]" >&2
            exit 1
            ;;
    esac
done

# 1. Discover nodes
echo "==> Discovering nodes..."
uv run python "$SCRIPT_DIR/discover_nodes.py" "$NODE_DIR"
echo

# 2. Collect discovered node IDs
nodes=""
for symlink in "$NODE_DIR"/*; do
    [ -L "$symlink" ] || continue
    nodes="$nodes $(basename "$symlink")"
done

if [ -z "$nodes" ]; then
    echo "error: no nodes discovered" >&2
    exit 1
fi

echo "==> Found nodes:$nodes"

# 3. Build firmware once (if flashing firmware)
if $flash_firmware; then
    echo
    echo "==> Building firmware..."
    cd "$EDGE_DIR"
    pio run
fi

# 4. Flash each node
for node_id in $nodes; do
    port="$NODE_DIR/$node_id"
    echo
    echo "==> Flashing node $node_id via $port ($(readlink "$port"))"

    if $flash_firmware; then
        echo "    Uploading firmware..."
        cd "$EDGE_DIR"
        pio run -t upload --upload-port "$port"
    fi

    if $flash_nvs; then
        echo "    Flashing NVS..."
        cd "$EDGE_DIR"
        "$SCRIPT_DIR/flash-nvs.sh" "$node_id" "$port"
    fi
done

echo
echo "==> Done. Flashed $(echo $nodes | wc -w | tr -d ' ') node(s):$nodes"
