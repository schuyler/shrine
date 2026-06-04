import os
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest
import serial

from scripts.discover_nodes import create_symlinks, find_esp32_ports, main, read_node_id

# CP210x VID/PID constants (match what the implementation must use)
CP210X_VID = 0x10C4
CP210X_PID = 0xEA60


def _make_port(device="/dev/ttyUSB0", vid=CP210X_VID, pid=CP210X_PID):
    """Return a mock port info object resembling ListPortInfo."""
    port = MagicMock()
    port.device = device
    port.vid = vid
    port.pid = pid
    return port


def _make_serial_mock(lines):
    """Return a mock Serial whose readline() yields the given strings as bytes.

    After all lines are exhausted, readline() returns b"" (mimicking
    a serial timeout with no data).
    """
    mock_serial = MagicMock()
    encoded = [line.encode() for line in lines]
    # After exhausting lines, return empty bytes indefinitely
    mock_serial.readline = MagicMock(side_effect=encoded + [b""] * 100)
    mock_serial.__enter__ = MagicMock(return_value=mock_serial)
    mock_serial.__exit__ = MagicMock(return_value=False)
    return mock_serial


class TestFindEsp32Ports:
    def test_filters_by_vid_pid(self):
        cp210x = _make_port("/dev/ttyUSB0", vid=CP210X_VID, pid=CP210X_PID)
        other = _make_port("/dev/ttyUSB1", vid=0x1234, pid=0x5678)
        with patch("serial.tools.list_ports.comports", return_value=[cp210x, other]):
            result = find_esp32_ports()
        assert result == [cp210x]

    def test_no_devices(self):
        with patch("serial.tools.list_ports.comports", return_value=[]):
            result = find_esp32_ports()
        assert result == []

    def test_ignores_non_cp210x(self):
        non_cp210x = _make_port("/dev/ttyUSB0", vid=0xABCD, pid=0x1234)
        with patch("serial.tools.list_ports.comports", return_value=[non_cp210x]):
            result = find_esp32_ports()
        assert result == []

    def test_returns_all_matching_ports(self):
        port0 = _make_port("/dev/ttyUSB0", vid=CP210X_VID, pid=CP210X_PID)
        port1 = _make_port("/dev/ttyUSB1", vid=CP210X_VID, pid=CP210X_PID)
        non_match = _make_port("/dev/ttyUSB2", vid=0x0403, pid=0x6001)
        with patch("serial.tools.list_ports.comports", return_value=[port0, non_match, port1]):
            result = find_esp32_ports()
        assert len(result) == 2
        assert port0 in result
        assert port1 in result


class TestReadNodeId:
    def test_parses_node_id_from_boot_log(self):
        lines = [
            "I (123) boot: ESP-IDF v5.0\r\n",
            "I (456) main: node_id=2 base_k=1234\r\n",
            "I (789) main: tasks started\r\n",
        ]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial):
            result = read_node_id("/dev/ttyUSB0", timeout=5.0)
        assert result == 2

    def test_parses_node_id_zero(self):
        lines = ["I (100) main: node_id=0 base_k=999\r\n"]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial):
            result = read_node_id("/dev/ttyUSB0", timeout=5.0)
        assert result == 0

    def test_returns_none_on_timeout(self):
        """Verify the function exits after the timeout, not just when lines run out."""
        # readline() always returns empty bytes (no data), simulating a device
        # that boots but never prints the node_id line. time.time() advances
        # past the deadline to trigger the timeout exit path.
        mock_serial = _make_serial_mock([])
        call_count = 0

        def advancing_time():
            nonlocal call_count
            call_count += 1
            # First call: start time. Subsequent calls: past deadline.
            if call_count <= 1:
                return 100.0
            return 200.0  # well past any reasonable timeout

        with patch("serial.Serial", return_value=mock_serial), \
             patch("time.time", side_effect=advancing_time):
            result = read_node_id("/dev/ttyUSB0", timeout=5.0)
        assert result is None
        # Verify the read loop was entered before timeout fired
        assert mock_serial.readline.call_count >= 1

    def test_resets_device_via_dtr(self):
        lines = ["I (100) main: node_id=1 base_k=100\r\n"]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial):
            read_node_id("/dev/ttyUSB0", timeout=5.0)
        # Verify DTR was toggled: False then True
        dtr_calls = mock_serial.setDTR.call_args_list
        assert call(False) in dtr_calls
        assert call(True) in dtr_calls
        false_idx = dtr_calls.index(call(False))
        true_idx = dtr_calls.index(call(True))
        assert false_idx < true_idx

    def test_opens_serial_at_115200_baud(self):
        lines = ["I (100) main: node_id=3 base_k=200\r\n"]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial) as mock_cls:
            read_node_id("/dev/ttyUSB0", timeout=5.0)
        args, kwargs = mock_cls.call_args
        device_arg = args[0] if args else kwargs.get("port")
        baud_arg = args[1] if len(args) > 1 else kwargs.get("baudrate")
        assert device_arg == "/dev/ttyUSB0"
        assert baud_arg == 115200

    def test_parses_fdm_bench_format(self):
        """fdm-bench firmware logs 'node=N k=...' without ESP log tag."""
        lines = [
            "I (334) fdm-bench: nvs_flash_init: ESP_OK (0x0)\r\n",
            "node=3 k=550 f_exc_req=54999.8 f_exc_actual=55006 fs=179999.3\r\n",
            "mag=51.2 sd=685 mean=1643 n=1800\r\n",
        ]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial):
            result = read_node_id("/dev/ttyUSB0", timeout=5.0)
        assert result == 3

    def test_skips_non_matching_lines_before_match(self):
        lines = [
            "I (100) boot: ESP-IDF v5.1\r\n",
            "I (200) heap_init: Initializing heap\r\n",
            "I (300) main: something else\r\n",
            "I (400) main: node_id=7 base_k=300\r\n",
        ]
        mock_serial = _make_serial_mock(lines)
        with patch("serial.Serial", return_value=mock_serial):
            result = read_node_id("/dev/ttyUSB0", timeout=5.0)
        assert result == 7


class TestCreateSymlinks:
    def test_creates_directory_and_symlinks(self, tmp_path):
        link_dir = str(tmp_path / "nodes")
        mapping = {1: "/dev/ttyUSB0", 2: "/dev/ttyUSB1"}
        create_symlinks(mapping, link_dir)
        assert os.path.isdir(link_dir)
        link1 = os.path.join(link_dir, "1")
        link2 = os.path.join(link_dir, "2")
        assert os.path.islink(link1)
        assert os.path.islink(link2)
        assert os.readlink(link1) == "/dev/ttyUSB0"
        assert os.readlink(link2) == "/dev/ttyUSB1"

    def test_symlink_names_are_string_node_ids(self, tmp_path):
        link_dir = str(tmp_path / "nodes")
        mapping = {3: "/dev/ttyUSB2"}
        create_symlinks(mapping, link_dir)
        assert os.path.islink(os.path.join(link_dir, "3"))

    def test_clears_existing_directory(self, tmp_path):
        link_dir = str(tmp_path / "nodes")
        os.makedirs(link_dir)
        stale = os.path.join(link_dir, "stale.txt")
        with open(stale, "w") as f:
            f.write("old")
        mapping = {1: "/dev/ttyUSB0"}
        create_symlinks(mapping, link_dir)
        assert not os.path.exists(stale)
        assert os.path.islink(os.path.join(link_dir, "1"))

    def test_clears_existing_symlinks(self, tmp_path):
        link_dir = str(tmp_path / "nodes")
        os.makedirs(link_dir)
        old_link = os.path.join(link_dir, "9")
        os.symlink("/dev/ttyUSB9", old_link)
        mapping = {1: "/dev/ttyUSB0"}
        create_symlinks(mapping, link_dir)
        assert not os.path.lexists(old_link)
        assert os.path.islink(os.path.join(link_dir, "1"))

    def test_handles_empty_mapping(self, tmp_path):
        link_dir = str(tmp_path / "nodes")
        create_symlinks({}, link_dir)
        assert os.path.isdir(link_dir)
        assert os.listdir(link_dir) == []

    def test_creates_nested_directory(self, tmp_path):
        link_dir = str(tmp_path / "a" / "b" / "nodes")
        create_symlinks({1: "/dev/ttyUSB0"}, link_dir)
        assert os.path.isdir(link_dir)
        assert os.path.islink(os.path.join(link_dir, "1"))


class TestCli:
    def test_default_path(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=1)
        mock_create = MagicMock()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stdout", new_callable=StringIO):
            main()
        mock_create.assert_called_once()
        _, path_arg = mock_create.call_args[0]
        assert path_arg == "/tmp/shrine/node"

    def test_custom_path(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=1)
        mock_create = MagicMock()
        custom = "/tmp/my_nodes"
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes", custom]), \
             patch("sys.stdout", new_callable=StringIO):
            main()
        mock_create.assert_called_once()
        _, path_arg = mock_create.call_args[0]
        assert path_arg == custom

    def test_timeout_default_is_10s(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=1)
        mock_create = MagicMock()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stdout", new_callable=StringIO):
            main()
        # read_node_id should be called with timeout=10.0 (the default)
        args, kwargs = mock_read.call_args
        timeout_val = kwargs.get("timeout") or args[1]
        assert timeout_val == pytest.approx(10.0)

    def test_timeout_flag_override(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=1)
        mock_create = MagicMock()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes", "--timeout", "20"]), \
             patch("sys.stdout", new_callable=StringIO):
            main()
        args, kwargs = mock_read.call_args
        timeout_val = kwargs.get("timeout") or args[1]
        assert timeout_val == pytest.approx(20.0)

    def test_prints_mapping_to_stdout(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=1)
        mock_create = MagicMock()
        captured = StringIO()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stdout", captured):
            main()
        output = captured.getvalue()
        assert "/dev/ttyUSB0" in output
        assert "/tmp/shrine/node/1" in output

    def test_exits_nonzero_when_no_devices(self):
        mock_find = MagicMock(return_value=[])
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0

    def test_exits_nonzero_when_all_timeout(self):
        port = _make_port("/dev/ttyUSB0")
        mock_find = MagicMock(return_value=[port])
        mock_read = MagicMock(return_value=None)
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0

    def test_exits_nonzero_on_duplicate_node_ids(self):
        port0 = _make_port("/dev/ttyUSB0")
        port1 = _make_port("/dev/ttyUSB1")
        mock_find = MagicMock(return_value=[port0, port1])
        mock_read = MagicMock(return_value=1)  # same ID for both
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", MagicMock()), \
             patch("sys.argv", ["discover_nodes"]), \
             patch("sys.stderr", new_callable=StringIO):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code != 0

    def test_partial_timeout_succeeds(self):
        """When some devices respond and some timeout, succeed with partial results."""
        port0 = _make_port("/dev/ttyUSB0")
        port1 = _make_port("/dev/ttyUSB1")
        mock_find = MagicMock(return_value=[port0, port1])
        mock_read = MagicMock(side_effect=[1, None])  # port1 times out
        mock_create = MagicMock()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes", "/tmp/test"]), \
             patch("sys.stdout", new_callable=StringIO):
            main()  # should not raise
        mock_create.assert_called_once_with({1: "/dev/ttyUSB0"}, "/tmp/test")

    def test_serial_exception_skips_device(self):
        """When a device raises SerialException, skip it and continue."""
        port0 = _make_port("/dev/ttyUSB0")
        port1 = _make_port("/dev/ttyUSB1")
        mock_find = MagicMock(return_value=[port0, port1])
        mock_read = MagicMock(side_effect=[serial.SerialException("disconnected"), 2])
        mock_create = MagicMock()
        with patch("scripts.discover_nodes.find_esp32_ports", mock_find), \
             patch("scripts.discover_nodes.read_node_id", mock_read), \
             patch("scripts.discover_nodes.create_symlinks", mock_create), \
             patch("sys.argv", ["discover_nodes", "/tmp/test"]), \
             patch("sys.stdout", new_callable=StringIO), \
             patch("sys.stderr", new_callable=StringIO):
            main()  # should not raise
        mock_create.assert_called_once_with({2: "/dev/ttyUSB1"}, "/tmp/test")
