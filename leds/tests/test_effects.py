import pytest

from leds.effects import EFFECTS, effect_names, resolve_effect


class TestResolveByName:
    def test_known_name(self):
        assert resolve_effect("rainbow") == 9

    def test_solid_is_zero(self):
        assert resolve_effect("solid") == 0

    def test_case_insensitive(self):
        assert resolve_effect("Rainbow") == 9

    def test_spaces_fold_to_underscores(self):
        assert resolve_effect("chase rainbow") == EFFECTS["chase_rainbow"]

    def test_hyphens_fold_to_underscores(self):
        assert resolve_effect("chase-rainbow") == EFFECTS["chase_rainbow"]

    def test_surrounding_whitespace_stripped(self):
        assert resolve_effect("  chase  ") == 28

    def test_unknown_name_returns_none(self):
        assert resolve_effect("definitely_not_an_effect") is None


class TestResolveByNumber:
    def test_int_passthrough(self):
        assert resolve_effect(42) == 42

    def test_numeric_string(self):
        assert resolve_effect("42") == 42

    def test_zero(self):
        assert resolve_effect(0) == 0

    def test_negative_int_rejected(self):
        assert resolve_effect(-1) is None

    def test_bool_rejected(self):
        # bool is an int subclass; must not be treated as fx 0/1
        assert resolve_effect(True) is None
        assert resolve_effect(False) is None


class TestEffectNames:
    def test_returns_sorted_list(self):
        names = effect_names()
        assert names == sorted(names)

    def test_all_names_resolve(self):
        for name in effect_names():
            assert resolve_effect(name) == EFFECTS[name]
