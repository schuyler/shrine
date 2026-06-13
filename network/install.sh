#!/usr/bin/env bash
# Install shrine network config files on corazon.
# Requires root. Idempotent — safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

NM_CONF="/etc/NetworkManager/conf.d/wifi-powersave-off.conf"
DNSMASQ_CONF="/etc/dnsmasq.d/dhcp-leases.conf"

if [[ $EUID -ne 0 ]]; then
    echo "Error: must run as root." >&2
    exit 1
fi

# --- Back up existing files ---
for f in "$NM_CONF" "$DNSMASQ_CONF"; do
    if [[ -f "$f" ]]; then
        cp -v "$f" "${f}.bak"
    fi
done

# --- Install files ---
cp -v "$SCRIPT_DIR/wifi-powersave-off.conf" "$NM_CONF"
cp -v "$SCRIPT_DIR/dhcp-leases.conf" "$DNSMASQ_CONF"

# --- Validate dnsmasq config before restarting anything ---
if ! dnsmasq --test 2>&1; then
    echo "Error: dnsmasq config validation failed. Restoring backups." >&2
    for f in "$NM_CONF" "$DNSMASQ_CONF"; do
        if [[ -f "${f}.bak" ]]; then
            mv -v "${f}.bak" "$f"
        else
            rm -v "$f"
        fi
    done
    exit 1
fi

# --- Restart NetworkManager ---
systemctl restart NetworkManager
sleep 2
if ! systemctl is-active --quiet NetworkManager; then
    echo "WARNING: NetworkManager failed to restart." >&2
    echo "  Recovery: sudo cp ${NM_CONF}.bak $NM_CONF && sudo systemctl restart NetworkManager" >&2
fi

# --- Restart dnsmasq ---
systemctl restart dnsmasq
sleep 1
if ! systemctl is-active --quiet dnsmasq; then
    echo "WARNING: dnsmasq failed to restart." >&2
    echo "  Recovery: sudo cp ${DNSMASQ_CONF}.bak $DNSMASQ_CONF && sudo systemctl restart dnsmasq" >&2
fi

# --- Clean up backups on success ---
for f in "$NM_CONF" "$DNSMASQ_CONF"; do
    rm -f "${f}.bak"
done

echo "Done. Network config installed."
