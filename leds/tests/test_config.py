import os
import tempfile

import pytest

from leds.config import load_config

# Keys that must be present in the new config schema
NEW_KEYS = [
    "osc_listen_host",
    "osc_listen_port",
    "wled_host",
    "wled_port",
    "wled_timeout",
    "update_rate_hz",
    "pads",
    "default_program",
    "default_palette",
    "latency_offset_ms",
]

# Keys from the old schema that must NOT appear in the new config
OLD_KEYS = [
    "idle_color",
    "warm_color",
    "gsr_shared_color",
    "min_brightness",
    "max_brightness",
    "idle_effect",
    "gsr_effect",
    "gsr_threshold",
    "speed_min",
    "speed_max",
]


class TestDefaultConfig:
    def test_returns_dict(self):
        config = load_config()
        assert isinstance(config, dict)

    @pytest.mark.parametrize("key", NEW_KEYS)
    def test_default_config_has_key(self, key):
        config = load_config()
        assert key in config, f"Expected key {key!r} not found in default config"

    def test_pads_is_list(self):
        config = load_config()
        assert isinstance(config["pads"], list)

    def test_pads_contains_ints(self):
        config = load_config()
        assert all(isinstance(p, int) for p in config["pads"])

    def test_default_program_is_string(self):
        config = load_config()
        assert isinstance(config["default_program"], str)

    def test_default_palette_is_string(self):
        config = load_config()
        assert isinstance(config["default_palette"], str)

    def test_latency_offset_ms_is_auto_or_numeric(self):
        config = load_config()
        value = config["latency_offset_ms"]
        assert value == "auto" or isinstance(value, (int, float)), (
            f"latency_offset_ms must be 'auto' or numeric, got {value!r}"
        )

    def test_update_rate_hz_is_numeric(self):
        config = load_config()
        assert isinstance(config["update_rate_hz"], (int, float))

    def test_default_pads_value(self):
        config = load_config()
        assert config["pads"] == [0, 1, 2, 3]

    def test_default_program_value(self):
        config = load_config()
        assert config["default_program"] == "breathe"

    def test_default_palette_value(self):
        config = load_config()
        assert config["default_palette"] == "default"

    def test_default_update_rate_hz_value(self):
        config = load_config()
        assert config["update_rate_hz"] == 30

    @pytest.mark.parametrize("key", OLD_KEYS)
    def test_old_key_absent(self, key):
        config = load_config()
        assert key not in config, f"Old key {key!r} must not be present in new config"


class TestCustomConfigOverrides:
    def _write_yaml(self, content):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_custom_value_overrides_default(self):
        path = self._write_yaml("update_rate_hz: 60\n")
        try:
            config = load_config(path)
            assert config["update_rate_hz"] == 60
        finally:
            os.unlink(path)

    def test_non_overridden_keys_retain_defaults(self):
        path = self._write_yaml("update_rate_hz: 60\n")
        try:
            config = load_config(path)
            default_config = load_config()
            assert config["wled_host"] == default_config["wled_host"]
        finally:
            os.unlink(path)

    def test_custom_pads_override(self):
        path = self._write_yaml("pads: [0, 1]\n")
        try:
            config = load_config(path)
            assert config["pads"] == [0, 1]
        finally:
            os.unlink(path)

    def test_custom_default_program_override(self):
        path = self._write_yaml("default_program: pulse\n")
        try:
            config = load_config(path)
            assert config["default_program"] == "pulse"
        finally:
            os.unlink(path)

    def test_empty_custom_file_uses_all_defaults(self):
        path = self._write_yaml("")
        try:
            config = load_config(path)
            default_config = load_config()
            for key in NEW_KEYS:
                assert config[key] == default_config[key]
        finally:
            os.unlink(path)


class TestMissingFile:
    def test_missing_file_raises_error(self):
        with pytest.raises((FileNotFoundError, OSError)):
            load_config("/nonexistent/path/config.yaml")

    def test_missing_file_path_in_error(self):
        bad_path = "/nonexistent/path/config.yaml"
        with pytest.raises(Exception) as exc_info:
            load_config(bad_path)
        assert bad_path in str(exc_info.value) or "nonexistent" in str(exc_info.value)
