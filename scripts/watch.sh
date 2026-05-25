#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

while true; do
    pio run -t upload -t monitor &
    PIO_PID=$!

    inotifywait -q -e modify,create -r src/ platformio.ini
    echo "Files changed, restarting..."

    kill "$PIO_PID" 2>/dev/null || true
    wait "$PIO_PID" 2>/dev/null || true
done
