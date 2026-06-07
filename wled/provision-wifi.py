#!/usr/bin/env python3
"""Provision WiFi credentials and hostname on a WLED device.

Usage: python provision-wifi.py <hostname> <ssid> <password> [port]

Sends WiFi credentials over the serial connection using the Improv
WiFi protocol, then sets the mDNS hostname via the WLED JSON API
once the device connects to the network.

Reference: https://www.improv-wifi.com/serial/
"""

import json
import sys
import time
import urllib.parse
import urllib.request

import serial


IMPROV_HEADER = b"IMPROV"
IMPROV_VERSION = 0x01

# Packet types
TYPE_CURRENT_STATE = 0x01
TYPE_ERROR_STATE = 0x02
TYPE_RPC_COMMAND = 0x03
TYPE_RPC_RESULT = 0x04

# RPC commands
CMD_WIFI_SETTINGS = 0x01

STATE_NAMES = {
    0x01: "ready", 0x02: "ready", 0x03: "authorized",
    0x04: "provisioning", 0x05: "provisioned",
}


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build_rpc_wifi(ssid: str, password: str) -> bytes:
    ssid_bytes = ssid.encode("utf-8")
    pass_bytes = password.encode("utf-8")
    inner_data = (
        bytes([len(ssid_bytes)]) + ssid_bytes
        + bytes([len(pass_bytes)]) + pass_bytes
    )
    rpc_data = (
        bytes([CMD_WIFI_SETTINGS, len(inner_data)])
        + inner_data
    )
    packet = (
        IMPROV_HEADER
        + bytes([IMPROV_VERSION, TYPE_RPC_COMMAND, len(rpc_data)])
        + rpc_data
    )
    packet += bytes([checksum(packet)])
    return packet


def read_packet(ser, timeout=10):
    """Read an Improv packet from serial."""
    end = time.time() + timeout
    buf = b""
    while time.time() < end:
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting)
            idx = buf.find(IMPROV_HEADER)
            if idx >= 0:
                buf = buf[idx:]
                if len(buf) >= 9:
                    data_len = buf[8]
                    total = 9 + data_len + 1
                    if len(buf) >= total:
                        packet = buf[:total]
                        ptype = packet[7]
                        payload = packet[9:9 + data_len]
                        return ptype, payload
        time.sleep(0.05)
    return None, None


def set_hostname(ip: str, hostname: str) -> bool:
    """Set WLED mDNS hostname via the settings form.

    The /settings/wifi endpoint persists the config and triggers a
    proper reboot. The /json/cfg endpoint saves but doesn't reload
    the mDNS name on reboot.
    """
    url = f"http://{ip}/settings/wifi"
    data = urllib.parse.urlencode({"CM": hostname}).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return "settings saved" in body.lower()
    except Exception as e:
        print(f"Failed to set hostname: {e}", file=sys.stderr)
        return False


def find_device_ip(mac_suffix: str, timeout: float = 30) -> str | None:
    """Wait for a device to appear in the neighbor table."""
    import subprocess
    end = time.time() + timeout
    while time.time() < end:
        result = subprocess.run(
            ["ip", "neigh"], capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if mac_suffix.lower() in line.lower() and "REACHABLE" in line:
                return line.split()[0]
        time.sleep(2)
    return None


def main():
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <hostname> <ssid> <password> [port]",
              file=sys.stderr)
        sys.exit(1)

    hostname = sys.argv[1]
    ssid = sys.argv[2]
    password = sys.argv[3]
    port = sys.argv[4] if len(sys.argv) > 4 else "/dev/ttyUSB0"

    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(1.0)
    ser.reset_input_buffer()

    # Drain pending state packets
    while True:
        ptype, payload = read_packet(ser, timeout=2)
        if ptype is None:
            break
        if ptype == TYPE_CURRENT_STATE:
            state = payload[0] if payload else 0
            print(f"Device state: {STATE_NAMES.get(state, f'{state:#x}')}")

    print(f"Sending WiFi credentials for '{ssid}' to {port}...")
    packet = build_rpc_wifi(ssid, password)
    ser.write(packet)
    ser.flush()

    print("Waiting for response...")
    ptype = None
    payload = None
    device_url = None
    end = time.time() + 30
    while time.time() < end:
        ptype, payload = read_packet(ser, timeout=10)
        if ptype is None:
            break
        if ptype == TYPE_CURRENT_STATE:
            state = payload[0] if payload else 0
            print(f"Device state: {STATE_NAMES.get(state, f'{state:#x}')}")
            continue
        break

    if ptype == TYPE_RPC_RESULT:
        print("WiFi provisioned successfully.")
        if payload:
            i = 1
            while i < len(payload):
                slen = payload[i]
                i += 1
                if slen > 0 and i + slen <= len(payload):
                    device_url = payload[i:i + slen].decode("utf-8", errors="replace")
                    print(f"  Device URL: {device_url}")
                i += slen
    elif ptype == TYPE_ERROR_STATE:
        error_codes = {
            0x01: "invalid RPC packet", 0x02: "unknown RPC command",
            0x03: "unable to connect", 0x04: "not authorized",
        }
        code = payload[0] if payload else 0xFE
        print(f"Error: {error_codes.get(code, f'unknown ({code:#x})')}", file=sys.stderr)
        sys.exit(1)
    elif ptype is None:
        # Device may have connected and rebooted before sending result.
        # Try to find it on the network anyway.
        print("No Improv response (device may have rebooted).")
    else:
        print(f"Unexpected response type: {ptype:#x}", file=sys.stderr)
        sys.exit(1)

    ser.close()

    # Extract IP from device URL or find via neighbor table
    ip = None
    if device_url and device_url.startswith("http://"):
        ip = device_url.replace("http://", "").rstrip("/")

    if not ip:
        print("Waiting for device on network...")
        # Read MAC from WLED info if we have an IP, otherwise scan
        # Use the esptool chip_id or scan neighbor table
        ip = find_device_ip("70:4b:ca", timeout=30)

    if ip:
        print(f"Device found at {ip}")
        print(f"Setting mDNS hostname to '{hostname}'...")
        if set_hostname(ip, hostname):
            print(f"Hostname set. Device rebooting as {hostname}.local...")
        else:
            print("Failed to set hostname.", file=sys.stderr)
            sys.exit(1)
    else:
        print("Could not find device on network. Set hostname manually.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
