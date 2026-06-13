import os
import tempfile

import pytest

from leds.config import load_config

# Keys that must be present in the new config schema
NEW_KEYS = [
    "osc_listen_host",
    "osc_listen_port",
    "wled_targets",
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
        assert config["update_rate_hz"] == 1

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
            assert config["wled_targets"] == default_config["wled_targets"]
        finally:
            os.unlink(path)

    def test_custom_pads_override(self):
        path = self._write_yaml(
            "pads: [0, 1]\n"
            "wled_targets:\n"
            "  - host: wled-a.local\n"
            "    pad: 0\n"
            "  - host: wled-b.local\n"
            "    pad: 1\n"
        )
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


# ---------------------------------------------------------------------------
# wled_targets validation (not yet implemented — expected to fail Red TDD)
# ---------------------------------------------------------------------------

class TestWledTargetsValidation:
    """Tests for _validate_wled_targets() and load_config() target validation.

    These tests expect load_config() to perform structural validation of
    wled_targets. The validation logic does not exist yet.
    """

    def _write_yaml(self, content):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def _valid_targets_yaml(self):
        return (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "  - host: 192.168.1.11\n"
            "    port: 80\n"
            "    pad: 1\n"
            "pads: [0, 1]\n"
        )

    def test_valid_wled_targets_passes_validation(self):
        path = self._write_yaml(self._valid_targets_yaml())
        try:
            config = load_config(path)
            assert "wled_targets" in config
        finally:
            os.unlink(path)

    def test_missing_wled_targets_raises_value_error(self):
        # A config that explicitly unsets wled_targets (overrides default to None/absent)
        path = self._write_yaml("wled_targets: null\npads: [0, 1]\n")
        try:
            with pytest.raises(ValueError, match="wled_targets"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_target_missing_host_raises_value_error(self):
        yaml_content = (
            "wled_targets:\n"
            "  - port: 80\n"
            "    pad: 0\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="host"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_target_missing_pad_raises_value_error(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="pad"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_duplicate_pad_values_raises_value_error(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "  - host: 192.168.1.11\n"
            "    port: 80\n"
            "    pad: 0\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError):
                load_config(path)
        finally:
            os.unlink(path)

    def test_color_not_three_element_int_list_raises_value_error(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "    color: [255, 0]\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="color"):
                load_config(path)
        finally:
            os.unlink(path)

    def test_color_null_is_valid(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "    color: null\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            config = load_config(path)
            assert config["wled_targets"][0]["color"] is None
        finally:
            os.unlink(path)

    def test_color_absent_is_valid(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            config = load_config(path)
            assert "wled_targets" in config
        finally:
            os.unlink(path)

    def test_pad_set_in_targets_must_match_config_pads(self):
        """Pad numbers in wled_targets must exactly match config['pads']."""
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 5\n"
            "pads: [0, 1, 2, 3]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError):
                load_config(path)
        finally:
            os.unlink(path)

    def test_color_non_integer_elements_raises_value_error(self):
        yaml_content = (
            "wled_targets:\n"
            "  - host: 192.168.1.10\n"
            "    port: 80\n"
            "    pad: 0\n"
            "    color: [255, 'red', 0]\n"
            "pads: [0]\n"
        )
        path = self._write_yaml(yaml_content)
        try:
            with pytest.raises(ValueError, match="color"):
                load_config(path)
        finally:
            os.unlink(path)
