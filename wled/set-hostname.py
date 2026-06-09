#!/usr/bin/env python3
"""Set the mDNS hostname on a WLED device.

Usage: python set-hostname.py <ip> <hostname> <ssid> <password>

SSID and password must be provided because the /settings/wifi endpoint
is a form handler — missing fields are treated as empty, which would
wipe the WiFi credentials from flash.
"""

import sys
import urllib.parse
import urllib.request


def main():
    if len(sys.argv) < 5:
        print(f"Usage: {sys.argv[0]} <ip> <hostname> <ssid> <password>",
              file=sys.stderr)
        sys.exit(1)

    ip = sys.argv[1]
    hostname = sys.argv[2]
    ssid = sys.argv[3]
    password = sys.argv[4]

    url = f"http://{ip}/settings/wifi"
    data = urllib.parse.urlencode({"CS0": ssid, "PW0": password, "CM": hostname}).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if "settings saved" in body.lower():
                print(f"Hostname set to '{hostname}'. Device rebooting as {hostname}.local...")
            else:
                print("Unexpected response.", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
