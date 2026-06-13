#!/usr/bin/env bash
# Install shrine network config files on corazon.
# Installs dnsmasq config, DHCP host reservations, and /etc/hosts entries.
# WiFi/ethernet mode is managed separately by shrine-network.sh.
# Requires root. Idempotent — safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

DNSMASQ_CONF="/etc/NetworkManager/dnsmasq-shared.d/shrine-dnsmasq.conf"
DHCP_HOSTS="/etc/NetworkManager/shrine-dhcp-hosts"
ETC_HOSTS="/etc/hosts"

MANAGED_TARGETS=("$DNSMASQ_CONF" "$DHCP_HOSTS")
HOSTS_MARKER_BEGIN="# BEGIN shrine"
HOSTS_MARKER_END="# END shrine"

if [[ $EUID -ne 0 ]]; then
    echo "Error: must run as root." >&2
    exit 1
fi

# --- Warn on placeholder MACs ---
if grep -q 'XX:XX:XX:XX:XX:XX' "$SCRIPT_DIR/shrine-dhcp-hosts"; then
    echo "WARNING: shrine-dhcp-hosts contains placeholder MAC addresses." >&2
    echo "  Fill in real MACs or DHCP reservations will not work." >&2
fi

# --- Rollback on failure ---
rollback() {
    trap - ERR
    echo "Install failed. Restoring backups." >&2
    for f in "${MANAGED_TARGETS[@]}"; do
        if [[ -f "${f}.bak" ]]; then
            mv -v "${f}.bak" "$f"
        else
            rm -f "$f"
        fi
    done
    if [[ -f "${ETC_HOSTS}.bak" ]]; then
        mv -v "${ETC_HOSTS}.bak" "$ETC_HOSTS"
    fi
    systemctl restart NetworkManager || true
}
trap rollback ERR

# --- Back up existing files ---
for f in "${MANAGED_TARGETS[@]}"; do
    if [[ -f "$f" ]]; then
        cp -v "$f" "${f}.bak"
    fi
done
cp -v "$ETC_HOSTS" "${ETC_HOSTS}.bak"

# --- Ensure target directories exist ---
mkdir -p "$(dirname "$DNSMASQ_CONF")"

# --- Install dnsmasq and DHCP config ---
cp -v "$SCRIPT_DIR/shrine-dnsmasq.conf" "$DNSMASQ_CONF"
cp -v "$SCRIPT_DIR/shrine-dhcp-hosts" "$DHCP_HOSTS"

# --- Splice shrine hosts into /etc/hosts ---
# Remove any existing shrine block, then append the new one.
sed -i "/$HOSTS_MARKER_BEGIN/,/$HOSTS_MARKER_END/d" "$ETC_HOSTS"
{
    echo "$HOSTS_MARKER_BEGIN"
    cat "$SCRIPT_DIR/hosts"
    echo "$HOSTS_MARKER_END"
} >> "$ETC_HOSTS"

# --- Restart NetworkManager (which restarts its managed dnsmasq) ---
systemctl restart NetworkManager
sleep 2
if ! systemctl is-active --quiet NetworkManager; then
    echo "ERROR: NetworkManager failed to restart." >&2
    trap - ERR
    rollback
    exit 1
fi

# --- Clean up backups on success ---
trap - ERR
for f in "${MANAGED_TARGETS[@]}"; do
    rm -f "${f}.bak"
done
rm -f "${ETC_HOSTS}.bak"

echo "Done. Network config installed."
