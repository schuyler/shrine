import os
import tempfile

import pytest

from leds.config import load_config

# Keys that must always be present in a loaded config
EXPECTED_KEYS = [
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


class TestLoadDefaultConfig:
    def test_returns_dict(self):
        config = load_config()
        assert isinstance(config, dict)

    @pytest.mark.parametrize("key", EXPECTED_KEYS)
    def test_default_config_has_key(self, key):
        config = load_config()
        assert key in config, f"Expected key {key!r} not found in default config"

    def test_idle_color_is_list_of_3(self):
        config = load_config()
        assert isinstance(config["idle_color"], list)
        assert len(config["idle_color"]) == 3

    def test_warm_color_is_list_of_3(self):
        config = load_config()
        assert isinstance(config["warm_color"], list)
        assert len(config["warm_color"]) == 3

    def test_gsr_shared_color_is_list_of_3(self):
        config = load_config()
        assert isinstance(config["gsr_shared_color"], list)
        assert len(config["gsr_shared_color"]) == 3

    def test_min_brightness_is_int(self):
        config = load_config()
        assert isinstance(config["min_brightness"], int)

    def test_max_brightness_is_int(self):
        config = load_config()
        assert isinstance(config["max_brightness"], int)

    def test_min_brightness_less_than_max(self):
        config = load_config()
        assert config["min_brightness"] < config["max_brightness"]

    def test_brightness_values_in_range(self):
        config = load_config()
        assert 0 <= config["min_brightness"] <= 255
        assert 0 <= config["max_brightness"] <= 255

    def test_gsr_threshold_is_float_or_int(self):
        config = load_config()
        assert isinstance(config["gsr_threshold"], (float, int))

    def test_speed_min_less_than_speed_max(self):
        config = load_config()
        assert config["speed_min"] < config["speed_max"]


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
        path = self._write_yaml("min_brightness: 5\n")
        try:
            config = load_config(path)
            assert config["min_brightness"] == 5
        finally:
            os.unlink(path)

    def test_non_overridden_keys_retain_defaults(self):
        path = self._write_yaml("min_brightness: 5\n")
        try:
            config = load_config(path)
            # max_brightness was not overridden; should come from defaults
            default_config = load_config()
            assert config["max_brightness"] == default_config["max_brightness"]
        finally:
            os.unlink(path)

    def test_custom_color_override(self):
        path = self._write_yaml("idle_color: [255, 0, 0]\n")
        try:
            config = load_config(path)
            assert config["idle_color"] == [255, 0, 0]
        finally:
            os.unlink(path)

    def test_multiple_overrides(self):
        content = "min_brightness: 10\nmax_brightness: 200\n"
        path = self._write_yaml(content)
        try:
            config = load_config(path)
            assert config["min_brightness"] == 10
            assert config["max_brightness"] == 200
        finally:
            os.unlink(path)

    def test_empty_custom_file_uses_all_defaults(self):
        path = self._write_yaml("")
        try:
            config = load_config(path)
            default_config = load_config()
            for key in EXPECTED_KEYS:
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
