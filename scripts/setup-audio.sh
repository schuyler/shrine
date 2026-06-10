#!/usr/bin/env bash
# setup-audio.sh — MiniCAT art installation system setup
# Target: Debian 13 (trixie)
# Usage: sudo ./setup-audio.sh [--check]

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
AUDIO_USER="sderle"
INSTALL_SERVICES=true

# ---------------------------------------------------------------------------
# Derived paths (repo root is one level up from scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SHRINE_SYSTEMD_DIR="${REPO_DIR}/systemd"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ok()      { echo "[OK]      $*"; }
install() { echo "[INSTALL] $*"; }
skip()    { echo "[SKIP]    $*"; }
info()    { echo "[INFO]    $*"; }
warn()    { echo "[WARN]    $*"; }

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        echo "ERROR: This script must be run as root (or via sudo)." >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Section 1: Package installation
# ---------------------------------------------------------------------------
install_packages() {
    info "=== Package installation ==="

    local pkgs=(
        puredata
        alsa-utils
    )

    local missing=()
    for pkg in "${pkgs[@]}"; do
        if dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null | grep -q "install ok installed"; then
            ok "${pkg} already installed"
        else
            missing+=("${pkg}")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        install "Installing: ${missing[*]}"
        apt-get update -qq
        apt-get install -y "${missing[@]}"
    fi

    # RT kernel — attempt install, don't fail if unavailable
    local rt_pkg="linux-image-rt-amd64"
    if dpkg-query -W -f='${Status}' "${rt_pkg}" 2>/dev/null | grep -q "install ok installed"; then
        ok "${rt_pkg} already installed"
    else
        install "Attempting to install ${rt_pkg} (non-fatal if unavailable)..."
        if apt-get install -y "${rt_pkg}" 2>/dev/null; then
            ok "${rt_pkg} installed"
        else
            warn "${rt_pkg} not available — stock PREEMPT_DYNAMIC kernel may suffice"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Section 2: Realtime audio privileges
# ---------------------------------------------------------------------------
configure_audio_group() {
    info "=== Realtime audio privileges ==="

    if id -nG "${AUDIO_USER}" | grep -qw audio; then
        ok "${AUDIO_USER} already in audio group"
    else
        install "Adding ${AUDIO_USER} to audio group"
        usermod -aG audio "${AUDIO_USER}"
    fi

    local limits_file="/etc/security/limits.d/99-audio.conf"
    local limits_content
    limits_content="$(cat <<'EOF'
@audio - rtprio 95
@audio - memlock unlimited
EOF
)"
    if [[ -f "${limits_file}" ]] && diff -q <(echo "${limits_content}") "${limits_file}" &>/dev/null; then
        ok "${limits_file} already up to date"
    else
        mkdir -p "$(dirname "${limits_file}")"
        echo "${limits_content}" > "${limits_file}"
        ok "Wrote ${limits_file}"
    fi
}

# ---------------------------------------------------------------------------
# Section 3: Journal log retention
# ---------------------------------------------------------------------------
configure_journald() {
    info "=== Journal log retention ==="

    local src="${SHRINE_SYSTEMD_DIR}/journald-shrine.conf"
    local dst="/etc/systemd/journald.conf.d/shrine.conf"
    if [[ ! -f "${src}" ]]; then
        warn "${src} not found — skipping"
        return
    fi
    mkdir -p "$(dirname "${dst}")"
    if [[ -f "${dst}" ]] && diff -q "${src}" "${dst}" &>/dev/null; then
        ok "${dst} already up to date"
    else
        install "Installing ${dst}"
        cp "${src}" "${dst}"
        systemctl restart systemd-journald
    fi
}

# ---------------------------------------------------------------------------
# Section 4: systemd units
# ---------------------------------------------------------------------------
install_systemd_units() {
    if [[ "${INSTALL_SERVICES}" != "true" ]]; then
        skip "INSTALL_SERVICES=false — skipping systemd unit installation"
        return
    fi

    info "=== systemd units ==="

    local units=(shrine-pd shrine-conductor shrine-leds)
    local changed=false

    for unit in "${units[@]}"; do
        local src="${SHRINE_SYSTEMD_DIR}/${unit}.service"
        local dst="/etc/systemd/system/${unit}.service"
        if [[ ! -f "${src}" ]]; then
            warn "${src} not found — skipping"
            continue
        fi
        if [[ -f "${dst}" ]] && diff -q "${src}" "${dst}" &>/dev/null; then
            ok "${unit}.service already up to date"
        else
            install "Installing ${unit}.service"
            cp "${src}" "${dst}"
            changed=true
        fi
    done

    if [[ "${changed}" == "true" ]]; then
        install "Running systemctl daemon-reload"
        systemctl daemon-reload
    fi

    for unit in "${units[@]}"; do
        if [[ ! -f "/etc/systemd/system/${unit}.service" ]]; then
            continue
        fi
        if systemctl is-enabled --quiet "${unit}.service" 2>/dev/null; then
            ok "${unit}.service already enabled"
        else
            install "Enabling ${unit}.service"
            systemctl enable "${unit}.service"
        fi
    done

    # Start (or restart if config changed)
    for unit in "${units[@]}"; do
        if [[ ! -f "/etc/systemd/system/${unit}.service" ]]; then
            continue
        fi
        if [[ "${changed}" == "true" ]] || ! systemctl is-active --quiet "${unit}.service" 2>/dev/null; then
            install "Starting ${unit}.service"
            systemctl restart "${unit}.service"
        else
            ok "${unit}.service already running"
        fi
    done
}

# ---------------------------------------------------------------------------
# Section 4: Verification / status check
# ---------------------------------------------------------------------------
check_status() {
    echo "=== MiniCAT System Status ==="
    echo

    echo "--- Kernel ---"
    uname -r
    if uname -r | grep -q '\-rt'; then
        echo "  RT kernel: YES"
    else
        echo "  RT kernel: NO (PREEMPT_DYNAMIC may suffice)"
        grep -r PREEMPT /boot/config-"$(uname -r)" 2>/dev/null | grep -E '^CONFIG_PREEMPT' || true
    fi
    echo

    echo "--- Required packages ---"
    local pkgs=(
        puredata
        alsa-utils
        linux-image-rt-amd64
    )
    for pkg in "${pkgs[@]}"; do
        if dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null | grep -q "install ok installed"; then
            echo "  [INSTALLED] ${pkg}"
        else
            echo "  [MISSING]   ${pkg}"
        fi
    done
    echo

    echo "--- Audio group membership ---"
    if id -nG "${AUDIO_USER}" | grep -qw audio; then
        echo "  ${AUDIO_USER} in audio group: YES"
    else
        echo "  ${AUDIO_USER} in audio group: NO"
    fi
    echo

    echo "--- limits.conf ---"
    local limits_file="/etc/security/limits.d/99-audio.conf"
    if [[ -f "${limits_file}" ]]; then
        echo "  ${limits_file}: EXISTS"
        cat "${limits_file}"
    else
        echo "  ${limits_file}: MISSING"
    fi
    echo

    echo "--- Journal retention ---"
    local journald_dst="/etc/systemd/journald.conf.d/shrine.conf"
    if [[ -f "${journald_dst}" ]]; then
        echo "  ${journald_dst}: EXISTS"
        grep MaxRetentionSec "${journald_dst}" || true
    else
        echo "  ${journald_dst}: MISSING"
    fi
    echo

    echo "--- systemd units ---"
    local units=(shrine-pd shrine-conductor shrine-leds)
    for unit in "${units[@]}"; do
        local status="MISSING"
        if [[ -f "/etc/systemd/system/${unit}.service" ]]; then
            if systemctl is-enabled --quiet "${unit}.service" 2>/dev/null; then
                status="ENABLED"
            else
                status="INSTALLED (disabled)"
            fi
            if systemctl is-active --quiet "${unit}.service" 2>/dev/null; then
                status="${status}, RUNNING"
            else
                status="${status}, stopped"
            fi
        fi
        echo "  ${unit}.service: ${status}"
    done
    echo

    echo "--- USB audio devices ---"
    if command -v lsusb &>/dev/null; then
        lsusb | grep -i audio || echo "  (none detected via lsusb)"
    fi
    echo
    if command -v aplay &>/dev/null; then
        echo "  aplay -l:"
        aplay -l 2>/dev/null || echo "  (no ALSA devices listed)"
    fi
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
main() {
    if [[ "${1:-}" == "--check" ]]; then
        check_status
        exit 0
    fi

    require_root

    install_packages
    echo
    configure_audio_group
    echo
    configure_journald
    echo
    install_systemd_units
    echo

    # Seed shrine.env from example if it doesn't exist yet
    local env_file="${SHRINE_SYSTEMD_DIR}/shrine.env"
    local env_example="${SHRINE_SYSTEMD_DIR}/shrine.env.example"
    if [[ -f "${env_file}" ]]; then
        ok "${env_file} already exists"
    elif [[ -f "${env_example}" ]]; then
        install "Creating ${env_file} from example — edit PD_AUDIO_OUTDEV for your hardware"
        cp "${env_example}" "${env_file}"
        chown "${AUDIO_USER}:${AUDIO_USER}" "${env_file}"
    else
        warn "${env_example} not found — shrine-pd will fail without shrine.env"
    fi
    echo

    info "=== Setup complete ==="
    info "Verify PD_AUDIO_OUTDEV in ${env_file}"
    info "(run 'pd -listdev' to find valid device names)."
    info "Run with --check to verify system state."
}

main "$@"
