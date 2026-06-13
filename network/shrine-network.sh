#!/usr/bin/env bash
# shrine-network.sh — switch corazon between WiFi AP mode and ethernet client mode.
# Network: 10.0.42.0/24, corazon is always 10.0.42.1.
#
# Usage:
#   shrine-network.sh ap --ssid NAME --password PASS
#   shrine-network.sh client
#   shrine-network.sh status
set -euo pipefail

SHRINE_IP="10.0.42.1/24"
SHRINE_DNSMASQ_CONF="/tmp/shrine-dnsmasq.conf"
SHRINE_DNSMASQ_PID="/run/shrine-dnsmasq.pid"
DHCP_HOSTS="/etc/NetworkManager/shrine-dhcp-hosts"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "Error: must run as root." >&2
        exit 1
    fi
}

detect_wifi() {
    local dev
    dev=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi" {print $1; exit}')
    if [[ -z "$dev" ]]; then
        echo "Error: no WiFi interface found." >&2
        exit 1
    fi
    echo "$dev"
}

detect_ethernet() {
    local dev
    dev=$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="ethernet" {print $1; exit}')
    if [[ -z "$dev" ]]; then
        echo "Error: no ethernet interface found." >&2
        exit 1
    fi
    echo "$dev"
}

kill_shrine_dnsmasq() {
    if [[ -f "$SHRINE_DNSMASQ_PID" ]]; then
        local pid
        pid=$(<"$SHRINE_DNSMASQ_PID") || return 0
        kill "$pid" 2>/dev/null || true
        # Wait for process to exit and release port 53
        local i
        for i in {1..10}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.2
        done
        if kill -0 "$pid" 2>/dev/null; then
            echo "Warning: dnsmasq ($pid) did not exit after SIGTERM; sending SIGKILL" >&2
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$SHRINE_DNSMASQ_PID"
    fi
}

deactivate_connection() {
    local con="$1"
    if nmcli connection show "$con" &>/dev/null; then
        nmcli connection down "$con" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# ap
# ---------------------------------------------------------------------------

cmd_ap() {
    require_root
    local ssid="" password=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --ssid)     ssid="$2";     shift 2 ;;
            --password) password="$2"; shift 2 ;;
            *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
        esac
    done

    if [[ -z "$ssid" || -z "$password" ]]; then
        echo "Error: --ssid and --password are required." >&2
        exit 1
    fi

    local WIFI_IF
    WIFI_IF=$(detect_wifi)

    echo "Switching to AP mode on $WIFI_IF (SSID: $ssid)..."

    kill_shrine_dnsmasq
    deactivate_connection shrine-client

    nmcli radio wifi on

    echo "Configuring shrine-ap connection..."
    nmcli connection delete shrine-ap 2>/dev/null || true
    nmcli connection add \
        type wifi \
        con-name shrine-ap \
        ifname "$WIFI_IF" \
        ssid "$ssid" \
        wifi.mode ap \
        wifi.band bg \
        wifi.channel 6 \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$password" \
        ipv4.method shared \
        ipv4.addresses "$SHRINE_IP"

    echo "Activating WiFi hotspot on $WIFI_IF..."
    nmcli connection up shrine-ap

    echo "Disabling WiFi power save on $WIFI_IF..."
    iw dev "$WIFI_IF" set power_save off

    echo "AP mode active. SSID: $ssid  IP: ${SHRINE_IP%/*}"
}

# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

cmd_client() {
    require_root
    local ETH_IF
    ETH_IF=$(detect_ethernet)

    echo "Switching to ethernet client mode on $ETH_IF..."

    deactivate_connection shrine-ap
    nmcli radio wifi off
    kill_shrine_dnsmasq

    # Free port 53 if systemd-resolved is running
    if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
        echo "Stopping systemd-resolved (conflicts with dnsmasq on port 53)..."
        systemctl stop systemd-resolved
    fi

    echo "Configuring shrine-client connection..."
    nmcli connection delete shrine-client 2>/dev/null || true
    nmcli connection add \
        type ethernet \
        con-name shrine-client \
        ifname "$ETH_IF" \
        ipv4.method manual \
        ipv4.addresses "$SHRINE_IP"

    echo "Activating ethernet connection on $ETH_IF..."
    nmcli connection up shrine-client

    echo "Writing dnsmasq config to $SHRINE_DNSMASQ_CONF..."
    cat > "$SHRINE_DNSMASQ_CONF" <<EOF
interface=$ETH_IF
bind-interfaces
dhcp-range=10.0.42.100,10.0.42.199,255.255.255.0,12h
dhcp-hostsfile=$DHCP_HOSTS
EOF

    echo "Starting dnsmasq..."
    dnsmasq --conf-file="$SHRINE_DNSMASQ_CONF" --pid-file="$SHRINE_DNSMASQ_PID"

    echo "Client mode active on $ETH_IF  IP: ${SHRINE_IP%/*}"
}

# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

cmd_status() {
    local ap_active client_active
    ap_active=$(nmcli -t -f NAME,STATE connection show --active 2>/dev/null \
        | awk -F: '$1=="shrine-ap" {print $2}')
    client_active=$(nmcli -t -f NAME,STATE connection show --active 2>/dev/null \
        | awk -F: '$1=="shrine-client" {print $2}')

    if [[ -n "$ap_active" ]]; then
        local WIFI_IF
        WIFI_IF=$(detect_wifi)
        local ip
        ip=$(ip -4 addr show "$WIFI_IF" 2>/dev/null \
            | awk '/inet / {print $2; exit}')
        echo "Mode:      ap"
        echo "Interface: $WIFI_IF"
        echo "IP:        ${ip:-unknown}"
        local ssid
        ssid=$(nmcli -t -f 802-11-wireless.ssid connection show shrine-ap 2>/dev/null \
            | awk -F: '{print $2}')
        echo "SSID:      ${ssid:-unknown}"
    elif [[ -n "$client_active" ]]; then
        local ETH_IF
        ETH_IF=$(detect_ethernet)
        local ip
        ip=$(ip -4 addr show "$ETH_IF" 2>/dev/null \
            | awk '/inet / {print $2; exit}')
        echo "Mode:      client"
        echo "Interface: $ETH_IF"
        echo "IP:        ${ip:-unknown}"
    else
        echo "Mode:      inactive (neither shrine-ap nor shrine-client is up)"
    fi
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 {ap --ssid NAME --password PASS | client | status}" >&2
    exit 1
fi

SUBCOMMAND="$1"
shift

case "$SUBCOMMAND" in
    ap)     cmd_ap "$@" ;;
    client) cmd_client "$@" ;;
    status) cmd_status "$@" ;;
    *)
        echo "Error: unknown subcommand: $SUBCOMMAND" >&2
        echo "Usage: $0 {ap --ssid NAME --password PASS | client | status}" >&2
        exit 1
        ;;
esac
