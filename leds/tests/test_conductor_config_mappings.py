"""Tests for config-driven state-program/palette mappings and hot reload.

These tests are written RED: they import functions and classes that do not exist
yet. All tests are expected to fail until the green phase implements:
  - leds.conductor_config.validate_state_mappings()
  - leds.conductor._get_mappings() / _set_mappings()
  - leds.conductor._ConfigReloadHandler
"""

import threading
import time
import textwrap

import pytest
import yaml

from leds.state_machine import State

# ---------------------------------------------------------------------------
# These imports will fail (ImportError) until the green phase.
# ---------------------------------------------------------------------------
from leds.conductor_config import validate_state_mappings, validate_tempo_config, validate_program_params, validate_subdiv_config  # noqa: E402
from leds.conductor import _get_mappings, _set_mappings, _ConfigReloadHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_states_programs() -> dict:
    """Return a programs dict with a valid entry for every State member."""
    return {s.name.lower(): "breathe" for s in State}


def _all_states_palettes() -> dict:
    """Return a palettes dict with a valid entry for every State member."""
    return {s.name.lower(): "default" for s in State}


def _write_yaml(path, content: str):
    """Write YAML content to a file and return the path."""
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _valid_conductor_yaml() -> str:
    """Return a minimal conductor.yaml string with programs and palettes sections."""
    programs = "\n".join(
        f"  {s.name.lower()}: breathe" for s in State
    )
    palettes = "\n".join(
        f"  {s.name.lower()}: default" for s in State
    )
    return f"programs:\n{programs}\npalettes:\n{palettes}\n"


# ---------------------------------------------------------------------------
# validate_state_mappings — valid input
# ---------------------------------------------------------------------------

class TestValidateStateMappingsValid:
    def test_valid_config_returns_programs_and_palettes(self):
        config = {
            "programs": _all_states_programs(),
            "palettes": _all_states_palettes(),
        }
        programs, palettes = validate_state_mappings(config)
        assert isinstance(programs, dict)
        assert isinstance(palettes, dict)

    def test_valid_config_programs_keys_are_lowercase_state_names(self):
        config = {
            "programs": _all_states_programs(),
            "palettes": _all_states_palettes(),
        }
        programs, _ = validate_state_mappings(config)
        expected_keys = {s.name.lower() for s in State}
        assert set(programs.keys()) >= expected_keys

    def test_valid_config_palettes_keys_are_lowercase_state_names(self):
        config = {
            "programs": _all_states_programs(),
            "palettes": _all_states_palettes(),
        }
        _, palettes = validate_state_mappings(config)
        expected_keys = {s.name.lower() for s in State}
        assert set(palettes.keys()) >= expected_keys

    def test_valid_config_values_are_returned_verbatim(self):
        programs_in = {s.name.lower(): f"prog_{s.name.lower()}" for s in State}
        palettes_in = {s.name.lower(): f"pal_{s.name.lower()}" for s in State}
        config = {"programs": programs_in, "palettes": palettes_in}
        programs_out, palettes_out = validate_state_mappings(config)
        for s in State:
            key = s.name.lower()
            assert programs_out[key] == programs_in[key]
            assert palettes_out[key] == palettes_in[key]


# ---------------------------------------------------------------------------
# validate_state_mappings — missing sections
# ---------------------------------------------------------------------------

class TestValidateStateMappingsMissingSections:
    def test_missing_programs_section_raises(self):
        config = {"palettes": _all_states_palettes()}
        with pytest.raises((ValueError, KeyError)):
            validate_state_mappings(config)

    def test_missing_palettes_section_raises(self):
        config = {"programs": _all_states_programs()}
        with pytest.raises((ValueError, KeyError)):
            validate_state_mappings(config)

    def test_empty_config_raises(self):
        with pytest.raises((ValueError, KeyError)):
            validate_state_mappings({})

    def test_programs_is_none_raises(self):
        config = {"programs": None, "palettes": _all_states_palettes()}
        with pytest.raises((ValueError, KeyError, TypeError)):
            validate_state_mappings(config)

    def test_palettes_is_none_raises(self):
        config = {"programs": _all_states_programs(), "palettes": None}
        with pytest.raises((ValueError, KeyError, TypeError)):
            validate_state_mappings(config)


# ---------------------------------------------------------------------------
# validate_state_mappings — missing state entries
# ---------------------------------------------------------------------------

class TestValidateStateMappingsMissingEntries:
    def _programs_missing_one(self) -> dict:
        d = _all_states_programs()
        # Remove one entry — pick the last State member
        last_key = list(State)[-1].name.lower()
        del d[last_key]
        return d

    def _palettes_missing_one(self) -> dict:
        d = _all_states_palettes()
        last_key = list(State)[-1].name.lower()
        del d[last_key]
        return d

    def test_missing_state_in_programs_raises_value_error(self):
        config = {
            "programs": self._programs_missing_one(),
            "palettes": _all_states_palettes(),
        }
        with pytest.raises(ValueError):
            validate_state_mappings(config)

    def test_missing_state_in_palettes_raises_value_error(self):
        config = {
            "programs": _all_states_programs(),
            "palettes": self._palettes_missing_one(),
        }
        with pytest.raises(ValueError):
            validate_state_mappings(config)

    def test_error_message_names_missing_state(self):
        missing = list(State)[-1].name.lower()
        programs = _all_states_programs()
        del programs[missing]
        config = {"programs": programs, "palettes": _all_states_palettes()}
        with pytest.raises(ValueError, match=missing):
            validate_state_mappings(config)


# ---------------------------------------------------------------------------
# validate_state_mappings — bad value types
# ---------------------------------------------------------------------------

class TestValidateStateMappingsBadTypes:
    def test_non_string_program_value_raises(self):
        programs = _all_states_programs()
        programs[list(State)[0].name.lower()] = 42  # integer, not string
        config = {"programs": programs, "palettes": _all_states_palettes()}
        with pytest.raises((ValueError, TypeError)):
            validate_state_mappings(config)

    def test_non_string_palette_value_raises(self):
        palettes = _all_states_palettes()
        palettes[list(State)[0].name.lower()] = ["not", "a", "string"]
        config = {"programs": _all_states_programs(), "palettes": palettes}
        with pytest.raises((ValueError, TypeError)):
            validate_state_mappings(config)

    def test_empty_string_program_value_raises(self):
        programs = _all_states_programs()
        programs[list(State)[0].name.lower()] = ""
        config = {"programs": programs, "palettes": _all_states_palettes()}
        with pytest.raises(ValueError):
            validate_state_mappings(config)

    def test_empty_string_palette_value_raises(self):
        palettes = _all_states_palettes()
        palettes[list(State)[0].name.lower()] = ""
        config = {"programs": _all_states_programs(), "palettes": palettes}
        with pytest.raises(ValueError):
            validate_state_mappings(config)

    def test_none_program_value_raises(self):
        programs = _all_states_programs()
        programs[list(State)[0].name.lower()] = None
        config = {"programs": programs, "palettes": _all_states_palettes()}
        with pytest.raises((ValueError, TypeError)):
            validate_state_mappings(config)


# ---------------------------------------------------------------------------
# validate_state_mappings — extra/unknown keys
# ---------------------------------------------------------------------------

class TestValidateStateMappingsExtraKeys:
    def test_extra_key_in_programs_does_not_raise(self):
        programs = _all_states_programs()
        programs["bogus_state"] = "pulse"
        config = {"programs": programs, "palettes": _all_states_palettes()}
        # Must not raise — extra keys are tolerated with a warning
        programs_out, palettes_out = validate_state_mappings(config)
        assert programs_out is not None

    def test_extra_key_in_palettes_does_not_raise(self):
        palettes = _all_states_palettes()
        palettes["bogus_state"] = "default"
        config = {"programs": _all_states_programs(), "palettes": palettes}
        programs_out, palettes_out = validate_state_mappings(config)
        assert palettes_out is not None

    def test_extra_key_logs_warning(self, caplog):
        import logging
        programs = _all_states_programs()
        programs["typo_state"] = "pulse"
        config = {"programs": programs, "palettes": _all_states_palettes()}
        with caplog.at_level(logging.WARNING):
            validate_state_mappings(config)
        warning_text = " ".join(caplog.messages)
        assert "typo_state" in warning_text


# ---------------------------------------------------------------------------
# validate_state_mappings — case handling
# ---------------------------------------------------------------------------

class TestValidateStateMappingsCaseHandling:
    def test_lowercase_keys_accepted(self):
        """YAML keys are lowercase; State enum names are UPPER. Mapping must work."""
        config = {
            "programs": _all_states_programs(),
            "palettes": _all_states_palettes(),
        }
        # Keys in _all_states_programs are already lowercase (s.name.lower())
        programs_out, _ = validate_state_mappings(config)
        for s in State:
            assert s.name.lower() in programs_out

    def test_uppercase_keys_raises_or_fails_lookup(self):
        """If YAML has uppercase keys they don't match and validation should fail."""
        # Build a dict with uppercase keys instead of lowercase
        programs = {s.name: "breathe" for s in State}  # UPPER case keys
        palettes = {s.name: "default" for s in State}
        config = {"programs": programs, "palettes": palettes}
        # The spec says keys are lowercase. Uppercase keys are like missing entries.
        with pytest.raises((ValueError, KeyError)):
            validate_state_mappings(config)


# ---------------------------------------------------------------------------
# load_conductor_config integration
# ---------------------------------------------------------------------------

class TestLoadConductorConfigIntegration:
    def test_load_config_with_programs_palettes_returns_them(self, tmp_path):
        cfg_file = tmp_path / "conductor.yaml"
        _write_yaml(cfg_file, _valid_conductor_yaml())
        from leds.conductor_config import load_conductor_config
        config = load_conductor_config(cfg_file)
        assert "programs" in config
        assert "palettes" in config

    def test_round_trip_validate(self, tmp_path):
        """Write YAML with programs/palettes, load, validate — correct values."""
        # Use distinct program/palette names per state
        programs_in = {s.name.lower(): f"prog_{i}" for i, s in enumerate(State)}
        palettes_in = {s.name.lower(): f"pal_{i}" for i, s in enumerate(State)}
        content = yaml.dump({"programs": programs_in, "palettes": palettes_in})
        cfg_file = tmp_path / "conductor.yaml"
        cfg_file.write_text(content, encoding="utf-8")

        from leds.conductor_config import load_conductor_config
        config = load_conductor_config(cfg_file)
        programs_out, palettes_out = validate_state_mappings(config)

        for s in State:
            key = s.name.lower()
            assert programs_out[key] == programs_in[key]
            assert palettes_out[key] == palettes_in[key]


# ---------------------------------------------------------------------------
# _get_mappings / _set_mappings
# ---------------------------------------------------------------------------

class TestGetSetMappings:
    def test_empty_dicts_set_and_retrieved(self):
        """_set_mappings({}, {}) followed by _get_mappings returns empty dicts."""
        # NOTE: the pre-init invariant (no get before set) is enforced by
        # startup ordering, not by a runtime guard (see design doc). This test
        # verifies the round-trip contract with empty input only.
        _set_mappings({}, {})
        programs, palettes = _get_mappings()
        assert programs == {}
        assert palettes == {}

    def test_set_then_get_returns_same_values(self):
        programs = _all_states_programs()
        palettes = _all_states_palettes()
        _set_mappings(programs, palettes)
        got_programs, got_palettes = _get_mappings()
        assert got_programs == programs
        assert got_palettes == palettes

    def test_second_set_replaces_first(self):
        programs_v1 = {s.name.lower(): "v1_prog" for s in State}
        palettes_v1 = {s.name.lower(): "v1_pal" for s in State}
        _set_mappings(programs_v1, palettes_v1)

        programs_v2 = {s.name.lower(): "v2_prog" for s in State}
        palettes_v2 = {s.name.lower(): "v2_pal" for s in State}
        _set_mappings(programs_v2, palettes_v2)

        got_programs, got_palettes = _get_mappings()
        for s in State:
            assert got_programs[s.name.lower()] == "v2_prog"
            assert got_palettes[s.name.lower()] == "v2_pal"

    def test_set_does_not_mutate_previous_refs(self):
        """After second _set_mappings, refs returned by first _get_mappings unchanged."""
        programs_v1 = {s.name.lower(): "original" for s in State}
        palettes_v1 = {s.name.lower(): "original" for s in State}
        _set_mappings(programs_v1, palettes_v1)

        # Hold a reference to the dicts returned by the first get
        ref_programs, ref_palettes = _get_mappings()

        # Now swap to new values
        programs_v2 = {s.name.lower(): "replaced" for s in State}
        palettes_v2 = {s.name.lower(): "replaced" for s in State}
        _set_mappings(programs_v2, palettes_v2)

        # The old references must not have changed
        for s in State:
            assert ref_programs[s.name.lower()] == "original"
            assert ref_palettes[s.name.lower()] == "original"

    def test_get_mappings_thread_safe(self):
        """Concurrent reads and writes must not raise or return partial state."""
        errors = []

        def writer():
            for _ in range(50):
                _set_mappings(
                    {s.name.lower(): "w" for s in State},
                    {s.name.lower(): "w" for s in State},
                )
                time.sleep(0.001)

        def reader():
            for _ in range(50):
                try:
                    programs, palettes = _get_mappings()
                    # Both dicts must be consistent (same generation)
                    assert isinstance(programs, dict)
                    assert isinstance(palettes, dict)
                except Exception as exc:
                    errors.append(exc)
                time.sleep(0.001)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# _ConfigReloadHandler
# ---------------------------------------------------------------------------

class TestConfigReloadHandler:
    """Tests for the watchdog reload handler.

    _ConfigReloadHandler is instantiated directly and its internal methods
    called without a live watchdog Observer, to keep tests fast and
    deterministic.
    """

    def _make_handler(self, config_path, led_client=None, current_state=None):
        from unittest.mock import MagicMock
        if led_client is None:
            led_client = MagicMock()
        if current_state is None:
            current_state = State.QUIET
        return _ConfigReloadHandler(
            config_path=config_path,
            led_client=led_client,
            current_state_ref=lambda: current_state,
        )

    def _write_valid_config(self, path):
        path.write_text(
            yaml.dump({
                "programs": _all_states_programs(),
                "palettes": _all_states_palettes(),
            }),
            encoding="utf-8",
        )

    def test_reload_updates_mappings_on_valid_config(self, tmp_path):
        cfg_file = tmp_path / "conductor.yaml"
        new_programs = {s.name.lower(): "pulse" for s in State}
        new_palettes = {s.name.lower(): "ascending" for s in State}
        cfg_file.write_text(
            yaml.dump({"programs": new_programs, "palettes": new_palettes}),
            encoding="utf-8",
        )

        # Set initial mappings to something different
        _set_mappings(
            {s.name.lower(): "breathe" for s in State},
            {s.name.lower(): "default" for s in State},
        )

        handler = self._make_handler(cfg_file)
        handler._reload()

        programs, palettes = _get_mappings()
        for s in State:
            assert programs[s.name.lower()] == "pulse"
            assert palettes[s.name.lower()] == "ascending"

    def test_reload_on_invalid_yaml_preserves_previous_mappings(self, tmp_path):
        cfg_file = tmp_path / "conductor.yaml"
        cfg_file.write_text(": this is not valid yaml: :\n", encoding="utf-8")

        original_programs = {s.name.lower(): "original" for s in State}
        original_palettes = {s.name.lower(): "original" for s in State}
        _set_mappings(original_programs, original_palettes)

        handler = self._make_handler(cfg_file)
        handler._reload()

        programs, palettes = _get_mappings()
        for s in State:
            assert programs[s.name.lower()] == "original"
            assert palettes[s.name.lower()] == "original"

    def test_reload_on_missing_state_preserves_previous_mappings(self, tmp_path):
        """Validation failure (missing state entry) keeps previous mappings."""
        cfg_file = tmp_path / "conductor.yaml"
        # programs is missing the last state
        incomplete_programs = _all_states_programs()
        del incomplete_programs[list(State)[-1].name.lower()]
        cfg_file.write_text(
            yaml.dump({"programs": incomplete_programs, "palettes": _all_states_palettes()}),
            encoding="utf-8",
        )

        original_programs = {s.name.lower(): "kept" for s in State}
        original_palettes = {s.name.lower(): "kept" for s in State}
        _set_mappings(original_programs, original_palettes)

        handler = self._make_handler(cfg_file)
        handler._reload()

        programs, palettes = _get_mappings()
        for s in State:
            assert programs[s.name.lower()] == "kept"
            assert palettes[s.name.lower()] == "kept"

    def test_reload_resends_current_state_program_and_palette(self, tmp_path):
        from unittest.mock import MagicMock, call
        cfg_file = tmp_path / "conductor.yaml"
        new_programs = {s.name.lower(): f"new_{s.name.lower()}" for s in State}
        new_palettes = {s.name.lower(): f"newpal_{s.name.lower()}" for s in State}
        cfg_file.write_text(
            yaml.dump({"programs": new_programs, "palettes": new_palettes}),
            encoding="utf-8",
        )

        led_client = MagicMock()
        current_state = State.SEEKING
        handler = self._make_handler(cfg_file, led_client=led_client, current_state=current_state)
        _set_mappings(_all_states_programs(), _all_states_palettes())
        handler._reload()

        expected_program = new_programs[current_state.name.lower()]
        expected_palette = new_palettes[current_state.name.lower()]

        assert led_client.send_message.call_args_list == [
            call("/leds/program", expected_program),
            call("/leds/palette", expected_palette),
        ]

    def test_failed_reload_does_not_update_last_reload_timestamp(self, tmp_path):
        """After a failed reload, _last_reload must stay at 0.0 (not advanced)."""
        cfg_file = tmp_path / "conductor.yaml"
        cfg_file.write_text("not: valid: yaml:\n", encoding="utf-8")

        handler = self._make_handler(cfg_file)
        initial_last_reload = handler._last_reload
        handler._reload()

        assert handler._last_reload == initial_last_reload

    def test_successful_reload_updates_last_reload_timestamp(self, tmp_path):
        cfg_file = tmp_path / "conductor.yaml"
        self._write_valid_config(cfg_file)
        _set_mappings(_all_states_programs(), _all_states_palettes())

        handler = self._make_handler(cfg_file)
        assert handler._last_reload == 0.0

        handler._reload()

        assert handler._last_reload > 0.0


# ---------------------------------------------------------------------------
# Debounce behaviour
# ---------------------------------------------------------------------------

class TestConfigReloadHandlerDebounce:
    """Debounce: reload only triggers after 0.5 s since last *successful* reload."""

    def _make_file_event(self, path):
        """Return a minimal fake watchdog FileModifiedEvent for the given path."""
        from unittest.mock import MagicMock
        event = MagicMock()
        event.src_path = str(path)
        # No meaningful dest_path (simulate a simple MODIFIED event).
        # Set to None rather than deleting — del on a MagicMock does not
        # reliably remove the attribute. The handler checks
        # `hasattr(event, "dest_path") and event.dest_path`, so None
        # short-circuits the truthiness check correctly.
        event.dest_path = None
        return event

    def _make_valid_config_handler(self, tmp_path):
        from unittest.mock import MagicMock, patch
        cfg_file = tmp_path / "conductor.yaml"
        cfg_file.write_text(
            yaml.dump({
                "programs": _all_states_programs(),
                "palettes": _all_states_palettes(),
            }),
            encoding="utf-8",
        )
        _set_mappings(_all_states_programs(), _all_states_palettes())
        led_client = MagicMock()
        handler = _ConfigReloadHandler(
            config_path=cfg_file,
            led_client=led_client,
            current_state_ref=lambda: State.QUIET,
        )
        return handler, cfg_file

    def test_second_event_within_debounce_window_is_suppressed(self, tmp_path):
        from unittest.mock import patch
        handler, cfg_file = self._make_valid_config_handler(tmp_path)

        # Patch _reload so we can count calls
        reload_call_count = []
        original_reload = handler._reload

        def counting_reload():
            reload_call_count.append(1)
            original_reload()

        handler._reload = counting_reload

        event = self._make_file_event(cfg_file)

        # First event triggers reload
        handler.on_any_event(event)
        # Second event within 0.5 s must be suppressed
        handler.on_any_event(event)

        assert len(reload_call_count) == 1, (
            f"Expected 1 reload call, got {len(reload_call_count)}"
        )

    def test_event_after_debounce_window_is_not_suppressed(self, tmp_path):
        from unittest.mock import patch
        handler, cfg_file = self._make_valid_config_handler(tmp_path)

        reload_call_count = []
        original_reload = handler._reload

        def counting_reload():
            reload_call_count.append(1)
            original_reload()

        handler._reload = counting_reload
        event = self._make_file_event(cfg_file)

        # First event
        handler.on_any_event(event)
        # Advance _last_reload to simulate time passing beyond debounce window
        handler._last_reload -= 1.0  # move 1 second into the past

        # Second event after window should NOT be suppressed
        handler.on_any_event(event)

        assert len(reload_call_count) == 2, (
            f"Expected 2 reload calls, got {len(reload_call_count)}"
        )

    def test_failed_reload_does_not_start_debounce(self, tmp_path):
        """After a failed reload, the next event must NOT be suppressed."""
        from unittest.mock import MagicMock
        cfg_file = tmp_path / "conductor.yaml"

        # Write invalid config first
        cfg_file.write_text("invalid: yaml: :\n", encoding="utf-8")
        _set_mappings(_all_states_programs(), _all_states_palettes())

        led_client = MagicMock()
        handler = _ConfigReloadHandler(
            config_path=cfg_file,
            led_client=led_client,
            current_state_ref=lambda: State.QUIET,
        )

        reload_call_count = []
        original_reload = handler._reload

        def counting_reload():
            reload_call_count.append(1)
            original_reload()

        handler._reload = counting_reload
        event_invalid = self._make_file_event(cfg_file)

        # First event — reload fails
        handler.on_any_event(event_invalid)
        assert len(reload_call_count) == 1

        # Now write valid config and fire another event immediately
        cfg_file.write_text(
            yaml.dump({
                "programs": _all_states_programs(),
                "palettes": _all_states_palettes(),
            }),
            encoding="utf-8",
        )
        handler.on_any_event(event_invalid)  # same event object, path is same

        # Second call must NOT have been suppressed by debounce
        assert len(reload_call_count) == 2, (
            "Expected second reload to fire after failed first reload; debounce must not suppress it"
        )

    def test_debounce_ignores_events_for_other_files(self, tmp_path):
        """Events for files other than the config path must be silently ignored."""
        from unittest.mock import MagicMock
        cfg_file = tmp_path / "conductor.yaml"
        cfg_file.write_text(
            yaml.dump({
                "programs": _all_states_programs(),
                "palettes": _all_states_palettes(),
            }),
            encoding="utf-8",
        )
        _set_mappings(_all_states_programs(), _all_states_palettes())

        led_client = MagicMock()
        handler = _ConfigReloadHandler(
            config_path=cfg_file,
            led_client=led_client,
            current_state_ref=lambda: State.QUIET,
        )

        reload_call_count = []
        original_reload = handler._reload

        def counting_reload():
            reload_call_count.append(1)
            original_reload()

        handler._reload = counting_reload

        # Event for a DIFFERENT file
        other_event = MagicMock()
        other_event.src_path = str(tmp_path / "other.yaml")
        other_event.dest_path = None

        handler.on_any_event(other_event)

        assert len(reload_call_count) == 0, (
            "Events for other files must not trigger reload"
        )


# ---------------------------------------------------------------------------
# Helpers for validate_tempo_config
# ---------------------------------------------------------------------------

def _all_states_tempo() -> dict:
    """Return a tempo dict with a valid entry for every State member."""
    return {s.name.lower(): 60 for s in State}


# ---------------------------------------------------------------------------
# validate_tempo_config — valid input
# ---------------------------------------------------------------------------

class TestValidateTempoConfigValid:
    def test_scalar_values_accepted(self):
        config = {"tempo": _all_states_tempo()}
        result = validate_tempo_config(config)
        assert isinstance(result, dict)
        for s in State:
            assert s.name.lower() in result

    def test_range_values_accepted(self):
        tempo = {s.name.lower(): [60, 80] for s in State}
        config = {"tempo": tempo}
        result = validate_tempo_config(config)
        for s in State:
            assert result[s.name.lower()] == [60, 80]

    def test_mixed_scalar_and_range_accepted(self):
        tempo = _all_states_tempo()
        tempo["seeking"] = [60, 70]
        config = {"tempo": tempo}
        result = validate_tempo_config(config)
        assert result["seeking"] == [60, 70]

    def test_returns_copy_not_original(self):
        tempo = _all_states_tempo()
        config = {"tempo": tempo}
        result = validate_tempo_config(config)
        assert result is not tempo


# ---------------------------------------------------------------------------
# validate_tempo_config — missing / wrong type
# ---------------------------------------------------------------------------

class TestValidateTempoConfigMissing:
    def test_missing_tempo_section_raises(self):
        with pytest.raises(ValueError, match="tempo"):
            validate_tempo_config({})

    def test_tempo_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="dict"):
            validate_tempo_config({"tempo": "not a dict"})

    def test_missing_state_key_raises(self):
        tempo = _all_states_tempo()
        del tempo[list(State)[-1].name.lower()]
        with pytest.raises(ValueError, match="missing"):
            validate_tempo_config({"tempo": tempo})

    def test_error_message_names_missing_state(self):
        missing = list(State)[-1].name.lower()
        tempo = _all_states_tempo()
        del tempo[missing]
        with pytest.raises(ValueError, match=missing):
            validate_tempo_config({"tempo": tempo})


# ---------------------------------------------------------------------------
# validate_tempo_config — bad value types
# ---------------------------------------------------------------------------

class TestValidateTempoConfigBadTypes:
    def test_string_value_raises(self):
        tempo = _all_states_tempo()
        tempo["quiet"] = "fast"
        with pytest.raises(ValueError):
            validate_tempo_config({"tempo": tempo})

    def test_none_value_raises(self):
        tempo = _all_states_tempo()
        tempo["quiet"] = None
        with pytest.raises(ValueError):
            validate_tempo_config({"tempo": tempo})

    def test_list_with_one_element_raises(self):
        tempo = _all_states_tempo()
        tempo["seeking"] = [60]
        with pytest.raises(ValueError, match="2 elements"):
            validate_tempo_config({"tempo": tempo})

    def test_list_with_three_elements_raises(self):
        tempo = _all_states_tempo()
        tempo["seeking"] = [60, 70, 80]
        with pytest.raises(ValueError, match="2 elements"):
            validate_tempo_config({"tempo": tempo})

    def test_non_numeric_list_elements_raises(self):
        tempo = _all_states_tempo()
        tempo["seeking"] = ["fast", "slow"]
        with pytest.raises(ValueError, match="numeric"):
            validate_tempo_config({"tempo": tempo})

    def test_inverted_range_raises(self):
        tempo = _all_states_tempo()
        tempo["seeking"] = [90, 60]
        with pytest.raises(ValueError, match="lo <= hi"):
            validate_tempo_config({"tempo": tempo})


# ---------------------------------------------------------------------------
# validate_tempo_config — extra keys
# ---------------------------------------------------------------------------

class TestValidateTempoConfigExtraKeys:
    def test_extra_key_does_not_raise(self):
        tempo = _all_states_tempo()
        tempo["bogus_state"] = 42
        config = {"tempo": tempo}
        result = validate_tempo_config(config)
        assert result is not None

    def test_extra_key_logs_warning(self, caplog):
        import logging
        tempo = _all_states_tempo()
        tempo["typo_state"] = 42
        config = {"tempo": tempo}
        with caplog.at_level(logging.WARNING):
            validate_tempo_config(config)
        assert "typo_state" in " ".join(caplog.messages)


# ---------------------------------------------------------------------------
# validate_program_params
# ---------------------------------------------------------------------------


class TestValidateProgramParams:
    def test_missing_section_returns_empty_dict(self):
        # config has no program_params key → returns {}
        result = validate_program_params({})
        assert result == {}

    def test_valid_section_round_trips(self):
        # Full valid section with known programs
        config = {
            "program_params": {
                "breathe": {
                    "sx": {"base": 100, "scale": 0.5},
                    "ix": {"base": 200, "scale": 0.0},
                }
            }
        }
        result = validate_program_params(config)
        assert result["breathe"]["sx"]["base"] == 100
        assert result["breathe"]["sx"]["scale"] == 0.5
        assert result["breathe"]["ix"]["base"] == 200

    def test_non_dict_section_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_program_params({"program_params": "not a dict"})

    def test_non_dict_program_entry_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_program_params({"program_params": {"breathe": "not a dict"}})

    def test_non_numeric_base_raises_value_error(self):
        config = {
            "program_params": {
                "breathe": {"sx": {"base": "fast", "scale": 0.0}}
            }
        }
        with pytest.raises(ValueError):
            validate_program_params(config)

    def test_non_numeric_scale_raises_value_error(self):
        config = {
            "program_params": {
                "breathe": {"sx": {"base": 128, "scale": "slow"}}
            }
        }
        with pytest.raises(ValueError):
            validate_program_params(config)

    def test_partial_params_accepted(self):
        # Only sx specified; ix absent — should not raise
        config = {
            "program_params": {
                "breathe": {"sx": {"base": 64, "scale": 0.0}}
            }
        }
        result = validate_program_params(config)
        assert result["breathe"]["sx"]["base"] == 64
        # ix key absent from result is fine — defaults applied at read time

    def test_empty_program_params_dict_accepted(self):
        config = {"program_params": {}}
        result = validate_program_params(config)
        assert result == {}

    def test_non_dict_sx_subkey_raises_value_error(self):
        # sx value is a scalar (42), not a dict — structural error
        config = {
            "program_params": {
                "breathe": {"sx": 42}
            }
        }
        with pytest.raises(ValueError):
            validate_program_params(config)

    def test_non_dict_ix_subkey_raises_value_error(self):
        # ix value is a scalar (42), not a dict — structural error
        config = {
            "program_params": {
                "breathe": {"ix": 42}
            }
        }
        with pytest.raises(ValueError):
            validate_program_params(config)


# ---------------------------------------------------------------------------
# Helpers for validate_subdiv_config
# ---------------------------------------------------------------------------

def _all_states_subdiv() -> dict:
    """Return a subdiv dict with a valid entry for every State member."""
    return {s.name.lower(): 4 for s in State}


# ---------------------------------------------------------------------------
# validate_subdiv_config — optional section
# ---------------------------------------------------------------------------

class TestValidateSubdivConfigOptional:
    def test_absent_section_returns_empty(self):
        # subdiv is optional; absent → {} so the conductor skips the cue.
        assert validate_subdiv_config({}) == {}

    def test_present_section_returned(self):
        config = {"subdiv": _all_states_subdiv()}
        result = validate_subdiv_config(config)
        for s in State:
            assert s.name.lower() in result


# ---------------------------------------------------------------------------
# validate_subdiv_config — valid input
# ---------------------------------------------------------------------------

class TestValidateSubdivConfigValid:
    def test_scalar_values_accepted(self):
        config = {"subdiv": _all_states_subdiv()}
        result = validate_subdiv_config(config)
        assert isinstance(result, dict)

    def test_calm_agitated_pair_accepted(self):
        subdiv = _all_states_subdiv()
        subdiv["seeking"] = [16, 8]
        config = {"subdiv": subdiv}
        result = validate_subdiv_config(config)
        assert result["seeking"] == [16, 8]

    def test_all_powers_of_two_accepted(self):
        for v in (1, 2, 4, 8, 16):
            subdiv = {s.name.lower(): v for s in State}
            assert validate_subdiv_config({"subdiv": subdiv})

    def test_returns_copy_not_original(self):
        subdiv = _all_states_subdiv()
        result = validate_subdiv_config({"subdiv": subdiv})
        assert result is not subdiv


# ---------------------------------------------------------------------------
# validate_subdiv_config — invalid input
# ---------------------------------------------------------------------------

class TestValidateSubdivConfigInvalid:
    def test_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="dict"):
            validate_subdiv_config({"subdiv": "nope"})

    def test_missing_state_key_raises(self):
        subdiv = _all_states_subdiv()
        del subdiv[list(State)[-1].name.lower()]
        with pytest.raises(ValueError, match="missing"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_non_power_of_two_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["quiet"] = 3
        with pytest.raises(ValueError, match="power of two"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_out_of_range_power_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["quiet"] = 32
        with pytest.raises(ValueError, match="power of two"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_float_value_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["quiet"] = 4.0
        with pytest.raises(ValueError, match="integer"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_bool_value_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["quiet"] = True
        with pytest.raises(ValueError, match="integer"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_pair_wrong_length_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["seeking"] = [8]
        with pytest.raises(ValueError, match="2 elements"):
            validate_subdiv_config({"subdiv": subdiv})

    def test_pair_with_bad_value_raises(self):
        subdiv = _all_states_subdiv()
        subdiv["seeking"] = [16, 5]
        with pytest.raises(ValueError, match="power of two"):
            validate_subdiv_config({"subdiv": subdiv})
