import pytest

import leds.effects as effects_mod
from leds.effects import (
    EFFECTS,
    EffectIndex,
    effect_names,
    fetch_effect_names,
    resolve_effect,
)


class _FakeResponse:
    def __init__(self, json_data=None, exc=None):
        self._json = json_data
        self._exc = exc

    def raise_for_status(self):
        pass

    def json(self):
        if self._exc is not None:
            raise self._exc
        return self._json


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


class TestFetchEffectNames:
    def test_fetches_and_returns_list(self, monkeypatch):
        payload = ["Solid", "Blink", "Breathe"]
        monkeypatch.setattr(
            effects_mod.requests, "get",
            lambda *a, **k: _FakeResponse(json_data=payload))
        assert fetch_effect_names("wled.local") == ["Solid", "Blink", "Breathe"]

    def test_network_error_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise effects_mod.requests.RequestException("down")
        monkeypatch.setattr(effects_mod.requests, "get", boom)
        assert fetch_effect_names("wled.local") is None

    def test_non_list_payload_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            effects_mod.requests, "get",
            lambda *a, **k: _FakeResponse(json_data={"not": "a list"}))
        assert fetch_effect_names("wled.local") is None


class TestEffectIndex:
    def test_seeded_with_static_table(self):
        idx = EffectIndex()
        assert idx.resolve("rainbow") == 9

    def test_numeric_still_works(self):
        idx = EffectIndex()
        assert idx.resolve(42) == 42

    def test_live_names_indexed_by_position(self):
        idx = EffectIndex()
        idx.update_from_names(["Solid", "Custom Sparkle", "Mystery FX"])
        assert idx.resolve("mystery fx") == 2

    def test_live_names_take_precedence(self):
        # Firmware reports a different ID than the static table — live wins.
        idx = EffectIndex()
        idx.update_from_names(["X"] * 9 + ["NotRainbow"])  # index 9 = "NotRainbow"
        assert idx.resolve("notrainbow") == 9

    def test_update_returns_count_and_skips_blanks(self):
        idx = EffectIndex()
        added = idx.update_from_names(["Solid", "", "Wipe"])
        assert added == 2

    def test_names_includes_live_additions(self):
        idx = EffectIndex()
        idx.update_from_names(["Totally New FX"])
        assert "totally_new_fx" in idx.names()
