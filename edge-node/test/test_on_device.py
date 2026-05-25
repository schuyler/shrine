#!/usr/bin/env python3
"""On-device integration test for ESP32 edge-node firmware.

Monitors serial output for expected boot sequence messages, then listens for
OSC UDP packets to verify the full sensing and transmission pipeline works.

Usage:
    python test_on_device.py [--port /dev/ttyACM0] [--baud 115200]
                             [--osc-port 57120] [--skip-osc]
"""

import argparse
import math
import re
import sys
import threading
import time

import serial
import serial.tools.list_ports
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


class SerialMonitor:
    """Opens a serial port in a background thread and accumulates lines."""

    def __init__(self, port, baud):
        self._port = serial.Serial(port, baud, timeout=1)
        self._lines = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while not self._stop_event.is_set():
            try:
                raw = self._port.readline()
                if raw:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    with self._lock:
                        self._lines.append(line)
            except serial.SerialException:
                break

    def wait_for(self, pattern, timeout):
        """Block until a line matching pattern appears or timeout expires.

        Returns the matching line, or None on timeout.
        """
        deadline = time.monotonic() + timeout
        seen = 0
        while time.monotonic() < deadline:
            with self._lock:
                current_lines = self._lines[seen:]
                seen = len(self._lines)
            for line in current_lines:
                if re.search(pattern, line):
                    return line
            time.sleep(0.05)
        # One final check after the sleep loop exits
        with self._lock:
            for line in self._lines[seen:]:
                if re.search(pattern, line):
                    return line
        return None

    def shutdown(self):
        self._stop_event.set()
        self._thread.join(timeout=2)
        try:
            self._port.close()
        except Exception:
            pass


class OscListener:
    """Collects OSC packets for a fixed duration using BlockingOSCUDPServer."""

    def __init__(self, osc_port):
        self._osc_port = osc_port
        self._packets = []
        self._lock = threading.Lock()

    def _handler(self, address, *args):
        with self._lock:
            self._packets.append((address, list(args)))

    def listen(self, duration):
        """Block for duration seconds collecting packets. Returns list of (address, args) tuples."""
        self._packets = []

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handler)

        server = BlockingOSCUDPServer(("0.0.0.0", self._osc_port), dispatcher)

        def _serve():
            server.serve_forever()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()
        time.sleep(duration)
        server.shutdown()
        thread.join(timeout=2)

        with self._lock:
            return list(self._packets)


def run_serial_checks(monitor):
    """Run serial boot-sequence checks.

    Returns list of (check_name, passed, detail) tuples.
    """
    results = []

    # 1. NVS loaded — matches main.c: ESP_LOGI(TAG, "node_id=...")
    timeout = 5
    line = monitor.wait_for(r"main: node_id=", timeout)
    if line is None:
        results.append(("NVS loaded", False, f"not seen within {timeout}s"))
    else:
        results.append(("NVS loaded", True, line))

    # 2. Calibration — matches sensing_task.c: ESP_LOGI(TAG, "calibration: ... sample_rate=...")
    timeout = 5
    line = monitor.wait_for(r"sensing:.*sample_rate=", timeout)
    if line is None:
        results.append(("Calibration", False, f"not seen within {timeout}s"))
    else:
        match = re.search(r"sample_rate=(\d+)", line)
        if match:
            rate = int(match.group(1))
            if rate > 10000:
                results.append(("Calibration", True, line))
            else:
                results.append(("Calibration", False, f"sample_rate={rate} is not > 10000"))
        else:
            results.append(("Calibration", False, f"could not extract sample_rate from: {line}"))

    # 3. WiFi connected — matches network_task.c: ESP_LOGI(TAG, "got IP: ...")
    timeout = 15
    line = monitor.wait_for(r"network: got IP:", timeout)
    if line is None:
        results.append(("WiFi connected", False, f"not seen within {timeout}s"))
    else:
        results.append(("WiFi connected", True, line))

    # 4. Tasks started — matches main.c: ESP_LOGI(TAG, "all tasks started")
    timeout = 5
    line = monitor.wait_for(r"main: all tasks started", timeout)
    if line is None:
        results.append(("Tasks started", False, f"not seen within {timeout}s"))
    else:
        results.append(("Tasks started", True, line))

    return results


def run_osc_checks(listener):
    """Listen for OSC packets and validate them.

    Returns list of (check_name, passed, detail) tuples.
    """
    results = []
    duration = 5
    packets = listener.listen(duration)

    # 1. Packet count
    count = len(packets)
    if count >= 10:
        results.append(("Packet count", True, f"{count} packets in {duration}s"))
    else:
        results.append(("Packet count", False, f"only {count} packets in {duration}s (need >= 10)"))

    # 2. Address format
    addr_pattern = re.compile(r"^/shrine/node/\d$")
    bad_addrs = [addr for addr, _args in packets if not addr_pattern.match(addr)]
    if not bad_addrs:
        results.append(("Address format", True, r"all match /shrine/node/\d"))
    else:
        results.append(("Address format", False, f"bad addresses: {bad_addrs[:5]}"))

    # 3. Argument count
    wrong_arg_count = [(addr, len(args)) for addr, args in packets if len(args) != 7]
    if not wrong_arg_count:
        results.append(("Argument count", True, "all packets have 7 args"))
    else:
        results.append(("Argument count", False, f"{len(wrong_arg_count)} packets with wrong arg count"))

    # 4. No NaN in self_cap_mag (first float arg)
    nan_packets = []
    for addr, args in packets:
        try:
            if args and math.isnan(float(args[0])):
                nan_packets.append(addr)
        except (TypeError, ValueError):
            nan_packets.append(addr)
    if not nan_packets:
        results.append(("No NaN", True, "no NaN values in self_cap_mag"))
    else:
        results.append(("No NaN", False, f"{len(nan_packets)} packets with NaN self_cap_mag"))

    return results


def _print_results(section_name, results):
    print(f"\n--- {section_name} ---")
    for check_name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {check_name}: {detail}")


def main():
    parser = argparse.ArgumentParser(
        description="On-device integration test for ESP32 edge-node firmware."
    )
    parser.add_argument("--port", help="Serial port (default: auto-detect)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument(
        "--osc-port", type=int, default=57120, help="UDP listen port for OSC (default: 57120)"
    )
    parser.add_argument(
        "--skip-osc", action="store_true", help="Skip OSC validation (for testing without WiFi)"
    )
    args = parser.parse_args()

    # Auto-detect port if not specified
    port = args.port
    if port is None:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("Error: no serial devices found and --port not specified")
            sys.exit(1)
        port = ports[0].device

    print("=== On-Device Integration Test ===")
    print(f"Serial port: {port}")

    monitor = None
    try:
        try:
            monitor = SerialMonitor(port, args.baud)
        except serial.SerialException as exc:
            print(f"Error opening serial port {port}: {exc}")
            sys.exit(1)

        # Serial checks
        serial_results = run_serial_checks(monitor)
        _print_results("Serial Checks", serial_results)

        all_results = list(serial_results)

        # OSC checks
        wifi_passed = any(name == "WiFi connected" and passed for name, passed, _ in serial_results)

        if args.skip_osc:
            print("\nOSC checks skipped")
        elif not wifi_passed:
            print("\nOSC checks skipped (WiFi not connected)")
        else:
            listener = OscListener(args.osc_port)
            osc_results = run_osc_checks(listener)
            _print_results("OSC Checks", osc_results)
            all_results.extend(osc_results)

        # Summary
        total = len(all_results)
        passed_count = sum(1 for _name, passed, _detail in all_results if passed)
        print(f"\n=== {passed_count}/{total} checks passed ===")

        sys.exit(0 if passed_count == total else 1)

    finally:
        if monitor is not None:
            monitor.shutdown()


if __name__ == "__main__":
    main()
