Tools for flashing and provisioning WLED on ESP32 LED controllers.

## Bring-up sequence

### 1. Download firmware

```
./download-firmware.sh [version]
```

Fetches `WLED_<version>_ESP32.bin` and `esp32_bootloader_v4.bin` from GitHub
releases, then generates `partitions.bin` from `partitions.csv`. Default
version: `16.0.0`.

### 2. Flash

```
./install-wled.sh [firmware.bin]
```

Erases the ESP32 flash, then writes:

- Bootloader at `0x0000`
- Partition table at `0x8000`
- WLED firmware at `0x10000`

Default firmware: `WLED_16.0.0_ESP32.bin`. Requires `esptool` (via `uv`).
Auto-generates `partitions.bin` from `partitions.csv` if missing.

### 3. Provision WiFi + hostname

```
python provision-wifi.py <hostname> <ssid> <password> [port]
```

Sends WiFi credentials over serial using the [Improv WiFi
protocol](https://www.improv-wifi.com/serial/), waits for the device to
connect, then sets the mDNS hostname via the WLED settings API. Default serial
port: `/dev/ttyUSB0`.

After this step the device is reachable at `<hostname>.local`.

### 4. Set hostname on an already-connected device (optional)

```
python set-hostname.py <ip> <hostname> <ssid> <password>
```

Sets the mDNS hostname on a device that already has WiFi. SSID and password are
required because `/settings/wifi` is a form handler — omitted fields are written
as empty, which would wipe the credentials from flash.

## Partition layout

`partitions.csv` defines the 4MB flash layout (from the WLED project):

| Name    | Type | Offset     | Size      |
|---------|------|------------|-----------|
| nvs     | data | `0x9000`   | `0x5000`  |
| otadata | data | `0xe000`   | `0x2000`  |
| app0    | app  | `0x10000`  | `0x180000`|
| app1    | app  | `0x190000` | `0x180000`|
| spiffs  | data | `0x310000` | `0xF0000` |

`gen_esp32part.py` converts the CSV to a binary. `install-wled.sh` runs this
automatically if `partitions.bin` is absent.

## WLED segment configuration

Each WLED box must be pre-configured with two segments at indices 0 and 1 before
use. The LED controller duplicates its output to both segment indices on every
render frame. Configure this in the WLED web UI under LED Preferences → Segments.
