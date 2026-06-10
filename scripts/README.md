Deployment, firmware, and diagnostic scripts for Shrine. Most run from the repo root on the dev machine; firmware tools run on corazon (the production host) where PlatformIO and the ESP32 nodes live.

## Deployment

**`deploy.sh`** — rsync the repo to `corazon.local:shrine/`, then restart the three systemd services (`shrine-pd`, `shrine-conductor`, `shrine-leds`). Excludes `.venv/`, `__pycache__/`, `.pio/`, `.DS_Store`, `.envrc`, `nvs/*.csv`, `wled/*.bin`, and `pd/main.pd` (`main.pd` is GUI-edited on corazon and must not be overwritten). Uses mDNS (`corazon.local`).

## System setup

**`setup-audio.sh`** — one-shot system provisioning for Debian 13. Installs puredata, alsa-utils, RT kernel (optional), configures audio group and rtprio limits, installs journald retention config, copies systemd service units, enables and starts services, seeds `shrine.env` from the example.

```bash
sudo ./scripts/setup-audio.sh          # full install
sudo ./scripts/setup-audio.sh --check  # status report only
```

## Firmware

**`flash-nvs.sh <node_id> [port]`** — generate an NVS binary from `nvs/nodeN.csv` and flash it to the device. Requires `esptool` and `esp-idf-nvs-partition-gen` (both in `pyproject.toml`). Run from a project directory containing an `nvs/` folder. Default port: `/dev/ttyUSB0`.

**`flash-all.sh [--nvs-only] [--firmware-only]`** — discover all connected ESP32 nodes via `discover_nodes.py`, build firmware once, then flash firmware and NVS to each. Run from the repo root.

**`discover_nodes.py [path] [--timeout SECS]`** — find connected ESP32 nodes by toggling DTR on each CP210x USB serial device to trigger a reset, then reading the node_id from the boot log. Creates symlinks at `path` (default `/tmp/shrine/node/`) mapping node ID to serial device.

**`watch.sh`** — build-flash-monitor loop. Watches `src/` and `platformio.ini` for changes via `inotifywait`, rebuilds and re-flashes on change, runs `pio device monitor` in between. Run from a PlatformIO project directory (e.g., `edge-node/`).

## Diagnostics

**`plot_fdm_osc.py [--host HOST] [--port PORT]`** — real-time matplotlib plotter for FDM sensor data. Receives `/shrine/node/{0-3}` OSC messages and displays 6 pairwise I/Q magnitudes and 4 per-node stdev traces. Default port: 57120.

**`plot_fft_osc.py [--port PORT] [--sample-rate HZ]`** — real-time FFT spectrum viewer. Receives `/shrine/node/{0-3}/fft` blob messages and plots log-magnitude spectra with carrier frequency markers. Default sample rate: 180000 Hz.

**`set_effect.py <pad> <effect> [--bri N] [--sx N] [--ix N] [--pal N]`** — send a `/leds/effect` OSC message to the LED controller to force a WLED effect on a pad. Use `off` to release, `--clear-all` to release all, `--list` to show known effect names. Optional `--host` / `--port` to target a different LED controller (defaults: `127.0.0.1:9000`). `--wled-host` / `--wled-port` fetch live effect names from a WLED box instead of using the built-in table. The LED controller must be running.

**`boot_capture.py`** — capture an ESP32 boot log after DTR reset. Hardcoded to `/dev/ttyUSB0`. Prints numbered lines until it sees a `mag=` line or times out at 30 seconds.

**`capture_window.py <port> <output-file>`** — capture a raw ADC window dump from the fdm-bench firmware. Sends the `d` serial command and writes 1800 sample lines to a file.

## Network

**`wifi-clients.sh`** — dump connected WiFi clients via `iw dev wlp2s0 station dump`. Requires sudo.
