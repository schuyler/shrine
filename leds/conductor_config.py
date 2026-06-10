"""Config loader for the conductor state machine."""

import logging
from pathlib import Path

import yaml

from leds.state_machine import State

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent / "conductor.yaml"


def validate_state_mappings(config: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Validate and return (programs, palettes) from a conductor config dict.

    Raises ValueError if either section is missing, has wrong types, or is
    missing entries for any State enum member.
    """
    programs_raw = config["programs"]
    palettes_raw = config["palettes"]

    if not isinstance(programs_raw, dict):
        raise ValueError(
            f"'programs' must be a dict, got {type(programs_raw).__name__}"
        )
    if not isinstance(palettes_raw, dict):
        raise ValueError(
            f"'palettes' must be a dict, got {type(palettes_raw).__name__}"
        )

    known_keys = {s.name.lower() for s in State}

    # Warn on unrecognized keys
    for key in programs_raw:
        if key not in known_keys:
            logger.warning("programs: unrecognized key %r (not a State member)", key)
    for key in palettes_raw:
        if key not in known_keys:
            logger.warning("palettes: unrecognized key %r (not a State member)", key)

    # Validate every State member has a valid entry in both maps
    for s in State:
        key = s.name.lower()

        if key not in programs_raw:
            raise ValueError(
                f"'programs' is missing entry for state '{key}'"
            )
        val = programs_raw[key]
        if not isinstance(val, str):
            raise ValueError(
                f"'programs[{key!r}]' must be a non-empty string, got {type(val).__name__}"
            )
        if not val:
            raise ValueError(
                f"'programs[{key!r}]' must be a non-empty string"
            )

        if key not in palettes_raw:
            raise ValueError(
                f"'palettes' is missing entry for state '{key}'"
            )
        val = palettes_raw[key]
        if not isinstance(val, str):
            raise ValueError(
                f"'palettes[{key!r}]' must be a non-empty string, got {type(val).__name__}"
            )
        if not val:
            raise ValueError(
                f"'palettes[{key!r}]' must be a non-empty string"
            )

    return dict(programs_raw), dict(palettes_raw)


def validate_tempo_config(config: dict) -> dict:
    """Validate and return the tempo section from a conductor config dict.

    Each State enum member must have an entry: either a scalar (fixed BPM)
    or a two-element [lo, hi] list (interpolated range).

    Raises ValueError on missing keys, wrong types, or invalid ranges.
    """
    if "tempo" not in config:
        raise ValueError("'tempo' section missing from conductor config")

    tempo = config["tempo"]
    if not isinstance(tempo, dict):
        raise ValueError(
            f"'tempo' must be a dict, got {type(tempo).__name__}"
        )

    known_keys = {s.name.lower() for s in State}
    for key in tempo:
        if key not in known_keys:
            logger.warning("tempo: unrecognized key %r (not a State member)", key)

    for s in State:
        key = s.name.lower()
        if key not in tempo:
            raise ValueError(f"'tempo' is missing entry for state '{key}'")

        val = tempo[key]
        if isinstance(val, list):
            if len(val) != 2:
                raise ValueError(
                    f"'tempo[{key!r}]' range must have exactly 2 elements, got {len(val)}"
                )
            if not all(isinstance(v, (int, float)) for v in val):
                raise ValueError(
                    f"'tempo[{key!r}]' range elements must be numeric"
                )
        elif not isinstance(val, (int, float)):
            raise ValueError(
                f"'tempo[{key!r}]' must be a number or [lo, hi] list, "
                f"got {type(val).__name__}"
            )

    return dict(tempo)


def load_conductor_config(path: str | Path | None = None) -> dict:
    """Load conductor.yaml, returning a plain dict.

    Loads from the repo-root conductor.yaml by default. Pass path to override.
    """
    source = Path(path) if path is not None else _DEFAULT_PATH
    if not source.exists():
        raise FileNotFoundError(f"Conductor config not found: {source}")
    with open(source, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
