import pytest

from leds.palettes import Palette, load_palettes


class TestPaletteName:
    def test_name_property_returns_name(self):
        p = Palette("default", {"idle": [0, 0, 255]})
        assert p.name == "default"

    def test_name_property_arbitrary_string(self):
        p = Palette("fire", {"idle": [255, 50, 0]})
        assert p.name == "fire"


class TestPaletteGet:
    def test_get_returns_correct_color(self):
        p = Palette("default", {"idle": [0, 0, 255], "warm": [255, 180, 0]})
        assert p.get("idle") == [0, 0, 255]

    def test_get_returns_second_color(self):
        p = Palette("default", {"idle": [0, 0, 255], "warm": [255, 180, 0]})
        assert p.get("warm") == [255, 180, 0]

    def test_get_with_unknown_key_returns_provided_default(self):
        p = Palette("default", {"idle": [0, 0, 255]})
        assert p.get("missing", [128, 128, 128]) == [128, 128, 128]

    def test_get_with_unknown_key_and_no_default_returns_black(self):
        p = Palette("default", {"idle": [0, 0, 255]})
        assert p.get("missing") == [0, 0, 0]

    def test_get_accent_color(self):
        p = Palette("default", {"idle": [0, 0, 255], "warm": [255, 180, 0], "accent": [200, 0, 200]})
        assert p.get("accent") == [200, 0, 200]


class TestLoadPalettes:
    def test_load_palettes_returns_dict(self):
        result = load_palettes()
        assert isinstance(result, dict)

    def test_load_palettes_default_palette_exists(self):
        result = load_palettes()
        assert "default" in result

    def test_load_palettes_values_are_palette_instances(self):
        result = load_palettes()
        for v in result.values():
            assert isinstance(v, Palette)

    def test_load_palettes_default_has_idle_color(self):
        result = load_palettes()
        assert result["default"].get("idle") == [0, 0, 255]

    def test_load_palettes_default_has_warm_color(self):
        result = load_palettes()
        assert result["default"].get("warm") == [255, 180, 0]

    def test_load_palettes_default_has_accent_color(self):
        result = load_palettes()
        assert result["default"].get("accent") == [200, 0, 200]

    def test_load_palettes_custom_yaml_overrides(self, tmp_path):
        yaml_file = tmp_path / "palettes.yaml"
        yaml_file.write_text("custom:\n  idle: [10, 20, 30]\n  warm: [40, 50, 60]\n")
        result = load_palettes(yaml_file)
        assert "custom" in result
        assert result["custom"].get("idle") == [10, 20, 30]

    def test_load_palettes_custom_yaml_unknown_name_absent(self, tmp_path):
        yaml_file = tmp_path / "palettes.yaml"
        yaml_file.write_text("custom:\n  idle: [10, 20, 30]\n")
        result = load_palettes(yaml_file)
        assert "default" not in result
