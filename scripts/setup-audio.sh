#!/usr/bin/env bash
# setup-audio.sh — MiniCAT art installation audio system setup
# Target: Debian 13 (trixie)
# Usage: sudo ./setup-audio.sh [--check]

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
AUDIO_USER="sderle"
JACK_SAMPLE_RATE=48000
JACK_BUFFER_SIZE=256
JACK_PERIODS=2
PRIMARY_DEVICE=""            # e.g. "hw:1,0" — first USB stereo interface
SECONDARY_DEVICE=""          # e.g. "hw:2,0" — second USB stereo interface
SPEAKER_1_PORT=""            # e.g. "system:playback_1" (primary L)
SPEAKER_2_PORT=""            # e.g. "system:playback_2" (primary R)
SPEAKER_3_PORT=""            # e.g. "alsa_out:playback_1" (secondary L)
SPEAKER_4_PORT=""            # e.g. "alsa_out:playback_2" (secondary R)
SC_DIR="/home/${AUDIO_USER}/shrine/sc"
INSTALL_SERVICES=true

# ---------------------------------------------------------------------------
# Derived paths (repo root is one level up from scripts/)
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AUDIO_DIR="${REPO_DIR}/audio"
SYSTEMD_DIR="${AUDIO_DIR}/systemd"

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

# Write a file only if its content differs from the desired content.
# $1 = destination path, rest of args = content via heredoc passed on stdin.
write_if_changed() {
    local dest="$1"
    local content="$2"
    local dir
    dir="$(dirname "${dest}")"
    mkdir -p "${dir}"
    if [[ -f "${dest}" ]] && diff -q <(echo "${content}") "${dest}" &>/dev/null; then
        ok "${dest} already up to date"
    else
        echo "${content}" > "${dest}"
        ok "Wrote ${dest}"
    fi
}

# ---------------------------------------------------------------------------
# Section 1: Package installation
# ---------------------------------------------------------------------------
install_packages() {
    info "=== Package installation ==="

    # Preseed jackd2 debconf to avoid interactive prompt about realtime privileges
    if command -v debconf-set-selections &>/dev/null; then
        echo "jackd2 jackd/tweak_rt_limits boolean true" | debconf-set-selections
    fi

    local pkgs=(
        jackd2
        supercollider
        supercollider-common
        supercollider-language
        supercollider-server
        sc3-plugins-server
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
    write_if_changed "${limits_file}" "${limits_content}"
}

# ---------------------------------------------------------------------------
# Section 3: JACK startup wrapper
# ---------------------------------------------------------------------------
write_jack_start() {
    info "=== JACK startup wrapper ==="

    mkdir -p "${AUDIO_DIR}"

    local jack_start="${AUDIO_DIR}/jack-start.sh"
    local device_arg=""
    if [[ -n "${PRIMARY_DEVICE}" ]]; then
        device_arg="-P ${PRIMARY_DEVICE}"
    fi

    local content
    content="$(cat <<EOF
#!/usr/bin/env bash
# jack-start.sh — Start JACK audio server for MiniCAT
# Generated by setup-audio.sh — edit setup-audio.sh to regenerate
set -euo pipefail

export JACK_NO_AUDIO_RESERVATION=1

exec jackd \\
    -R \\
    -P 70 \\
    -d alsa \\
    ${device_arg:+${device_arg} }\\
    -r ${JACK_SAMPLE_RATE} \\
    -p ${JACK_BUFFER_SIZE} \\
    -n ${JACK_PERIODS}
EOF
)"
    write_if_changed "${jack_start}" "${content}"
    chmod +x "${jack_start}"
}

# ---------------------------------------------------------------------------
# Section 4: Secondary device aggregation
# ---------------------------------------------------------------------------
write_alsa_out_secondary() {
    info "=== Secondary device aggregation ==="

    mkdir -p "${AUDIO_DIR}"

    local alsa_out_script="${AUDIO_DIR}/alsa-out-secondary.sh"
    local content
    content="$(cat <<'OUTER'
#!/usr/bin/env bash
# alsa-out-secondary.sh — Add secondary USB interface to JACK graph
# Generated by setup-audio.sh — edit setup-audio.sh to regenerate
set -euo pipefail

SECONDARY_DEVICE="PLACEHOLDER_SECONDARY_DEVICE"

if [[ -z "${SECONDARY_DEVICE}" ]]; then
    echo "SECONDARY_DEVICE is not set; nothing to do." >&2
    exit 0
fi

exec alsa_out -d "${SECONDARY_DEVICE}"
OUTER
)"
    # Substitute the actual value
    content="${content/PLACEHOLDER_SECONDARY_DEVICE/${SECONDARY_DEVICE}}"

    write_if_changed "${alsa_out_script}" "${content}"
    chmod +x "${alsa_out_script}"
}

# ---------------------------------------------------------------------------
# Section 5: SuperCollider startup
# ---------------------------------------------------------------------------
write_supercollider_startup() {
    info "=== SuperCollider startup ==="

    if [[ ! -d "${SC_DIR}" ]]; then
        install "Creating ${SC_DIR}"
        mkdir -p "${SC_DIR}"
        chown "${AUDIO_USER}:${AUDIO_USER}" "${SC_DIR}"
    else
        ok "${SC_DIR} already exists"
    fi

    local startup_scd="${SC_DIR}/startup.scd"
    local content
    content="$(cat <<EOF
// startup.scd — MiniCAT SuperCollider startup
// Generated by setup-audio.sh — edit to add SynthDefs and OSC handlers

(
    // Boot the server connected to JACK with 4 output channels
    // Sample rate and block size are determined by JACK, not SC.
    s = Server.default;

    s.options.numOutputBusChannels = 4;
    s.options.numInputBusChannels  = 0;

    // Speaker port assignments (for reference / patching)
    // SPEAKER_1_PORT = "${SPEAKER_1_PORT}"
    // SPEAKER_2_PORT = "${SPEAKER_2_PORT}"
    // SPEAKER_3_PORT = "${SPEAKER_3_PORT}"
    // SPEAKER_4_PORT = "${SPEAKER_4_PORT}"

    s.waitForBoot({
        // OSC listener on default port 57120
        thisProcess.openUDPPort(57120);
        ("SuperCollider listening on OSC port 57120").postln;

        // ---------------------------------------------------------------
        // SynthDefs go here
        // ---------------------------------------------------------------


        // ---------------------------------------------------------------
        // OSC handlers go here
        // ---------------------------------------------------------------


        ("MiniCAT startup complete.").postln;
    });
)
EOF
)"
    write_if_changed "${startup_scd}" "${content}"
    chown "${AUDIO_USER}:${AUDIO_USER}" "${startup_scd}"
}

# ---------------------------------------------------------------------------
# Section 6: systemd units
# ---------------------------------------------------------------------------
write_systemd_units() {
    if [[ "${INSTALL_SERVICES}" != "true" ]]; then
        skip "INSTALL_SERVICES=false — skipping systemd unit installation"
        return
    fi

    info "=== systemd units ==="

    mkdir -p "${SYSTEMD_DIR}"

    # --- jack.service ---
    local jack_service_content
    jack_service_content="$(cat <<EOF
[Unit]
Description=JACK Audio Connection Kit
After=sound.target
Wants=sound.target

[Service]
Type=simple
User=${AUDIO_USER}
Environment=JACK_NO_AUDIO_RESERVATION=1
ExecStart=${AUDIO_DIR}/jack-start.sh
Restart=on-failure
RestartSec=3
LimitRTPRIO=95
LimitMEMLOCK=infinity

[Install]
WantedBy=multi-user.target
EOF
)"
    write_if_changed "${SYSTEMD_DIR}/jack.service" "${jack_service_content}"

    # --- alsa-out-secondary.service ---
    local alsa_service_content
    alsa_service_content="$(cat <<EOF
[Unit]
Description=ALSA secondary USB audio interface bridge to JACK
After=jack.service
Requires=jack.service
ConditionPathExists=${AUDIO_DIR}/alsa-out-secondary.sh

[Service]
Type=simple
User=${AUDIO_USER}
ExecStart=${AUDIO_DIR}/alsa-out-secondary.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
)"
    write_if_changed "${SYSTEMD_DIR}/alsa-out-secondary.service" "${alsa_service_content}"

    # --- supercollider.service ---
    local sc_service_content
    sc_service_content="$(cat <<EOF
[Unit]
Description=SuperCollider audio engine (headless)
After=jack.service alsa-out-secondary.service
Requires=jack.service

[Service]
Type=simple
User=${AUDIO_USER}
Environment=DISPLAY=
Environment=QT_QPA_PLATFORM=offscreen
ExecStart=/usr/bin/sclang ${SC_DIR}/startup.scd
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
)"
    write_if_changed "${SYSTEMD_DIR}/supercollider.service" "${sc_service_content}"

    # --- Install to /etc/systemd/system/ ---
    local units=(jack alsa-out-secondary supercollider)
    local changed=false
    for unit in "${units[@]}"; do
        local src="${SYSTEMD_DIR}/${unit}.service"
        local dst="/etc/systemd/system/${unit}.service"
        if [[ -f "${dst}" ]] && diff -q "${src}" "${dst}" &>/dev/null; then
            ok "/etc/systemd/system/${unit}.service already up to date"
        else
            install "Installing /etc/systemd/system/${unit}.service"
            cp "${src}" "${dst}"
            changed=true
        fi
    done

    if [[ "${changed}" == "true" ]]; then
        install "Running systemctl daemon-reload"
        systemctl daemon-reload
    fi

    # Enable but don't start
    for unit in "${units[@]}"; do
        if systemctl is-enabled --quiet "${unit}.service" 2>/dev/null; then
            ok "${unit}.service already enabled"
        else
            install "Enabling ${unit}.service"
            systemctl enable "${unit}.service"
        fi
    done
}

# ---------------------------------------------------------------------------
# Section 7: Verification / status check
# ---------------------------------------------------------------------------
check_status() {
    echo "=== MiniCAT Audio System Status ==="
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
        jackd2
        supercollider
        supercollider-common
        supercollider-language
        supercollider-server
        sc3-plugins-server
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

    echo "--- systemd units ---"
    local units=(jack alsa-out-secondary supercollider)
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
    write_jack_start
    echo
    write_alsa_out_secondary
    echo
    write_supercollider_startup
    echo
    write_systemd_units
    echo

    info "=== Setup complete ==="
    info "Review configuration constants at the top of this script,"
    info "then set PRIMARY_DEVICE and SECONDARY_DEVICE for your hardware."
    info "Run with --check to verify system state."
}

main "$@"
