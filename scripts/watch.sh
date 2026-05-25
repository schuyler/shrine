#!/usr/bin/env bash
set -euo pipefail

WATCHER_PID=""

kill_monitor() {
    pkill -f "pio device monitor" 2>/dev/null || true
    pkill -f "miniterm" 2>/dev/null || true
}

cleanup() {
    kill_monitor
    [ -n "$WATCHER_PID" ] && kill "$WATCHER_PID" 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM EXIT

if [[ ! -f platformio.ini || ! -d src ]]; then
    echo "Error: must be run from a directory containing platformio.ini and src/" >&2
    exit 1
fi

pio run -t upload || exit 1

while true; do
    # Watch for source changes in background; kill the monitor when triggered
    (
        inotifywait -q -e modify,create -r src/ platformio.ini
        kill_monitor
    ) &
    WATCHER_PID=$!

    # Monitor runs in foreground so it gets the TTY
    pio device monitor || true

    kill "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true

    echo "Files changed, rebuilding..."
    pio run -t upload || continue
done
