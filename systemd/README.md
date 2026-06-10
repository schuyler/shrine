systemd service units for running Shrine in production. Three services, one environment file, one journald config.

## Services

**`shrine-pd.service`** — Pure Data sound engine. Runs `pd` with ALSA output at 48 kHz, 4 channels. Ordered after `graphical.target` and `sound.target` (soft dependency — needs ALSA and an X display for the Pd GUI). Reads `PD_AUDIO_OUTDEV` from `shrine.env`. Restarts on failure with a 5s delay.

**`shrine-conductor.service`** — Conductor state machine. Runs `python -m leds.conductor` from the project venv. Ordered after `network-online.target`. Restarts on failure with a 3s delay.

**`shrine-leds.service`** — LED renderer. Runs `python -m leds` from the project venv. Ordered after `network-online.target`. Restarts on failure with a 3s delay.

All three run as user `sderle` with `WorkingDirectory=/home/sderle/shrine`.

## Configuration

**`shrine.env`** — environment variables loaded by `shrine-pd.service`. Not tracked in git. Contains:

```
PD_AUDIO_OUTDEV="USB Audio"
```

Find valid device names with `pd -listdev`. `shrine.env.example` is the template; `setup-audio.sh` copies it to `shrine.env` on first run.

## Installation

`scripts/setup-audio.sh` handles everything: copies service files to `/etc/systemd/system/`, runs `daemon-reload`, enables and starts the services, and seeds `shrine.env`. Run it once on a fresh host.

To install manually:

```bash
sudo cp systemd/shrine-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable shrine-pd shrine-conductor shrine-leds
cp systemd/shrine.env.example systemd/shrine.env   # then edit PD_AUDIO_OUTDEV
sudo systemctl start shrine-pd shrine-conductor shrine-leds
```

## Logs

**`journald-shrine.conf`** — installed to `/etc/systemd/journald.conf.d/shrine.conf` by `setup-audio.sh`. Sets `MaxRetentionSec=1week`.

```bash
journalctl -u shrine-pd -f              # follow Pd output
journalctl -u shrine-conductor -f       # follow conductor
journalctl -u shrine-leds -f            # follow LED renderer
journalctl -u 'shrine-*' --since today  # all three since today
```
