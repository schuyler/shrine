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
            if val[0] > val[1]:
                raise ValueError(
                    f"'tempo[{key!r}]' range [lo, hi] must satisfy lo <= hi, "
                    f"got [{val[0]}, {val[1]}]"
                )
        elif not isinstance(val, (int, float)):
            raise ValueError(
                f"'tempo[{key!r}]' must be a number or [lo, hi] list, "
                f"got {type(val).__name__}"
            )

    return dict(tempo)


_ALLOWED_SUBDIV = {1, 2, 4, 8, 16}


def validate_subdiv_config(config: dict) -> dict:
    """Validate and return the subdiv section from a conductor config dict.

    The melodic re-fire grid, expressed in clock ticks per re-fire (the clock
    runs a 16th-note tick grid, 4 ticks/beat): 16=bar, 8=half, 4=quarter,
    2=eighth, 1=sixteenth. Smaller = denser.

    Each State member must have an entry: either a scalar power-of-two tick
    count, or a two-element [calm, agitated] list of such values (interpolated
    by bucket fill). Values must be in {1, 2, 4, 8, 16}.

    This section is OPTIONAL. Returns {} if absent — the conductor then skips
    broadcasting /shrine/cue/refire and the Pd gate falls back to its default
    grid. When present, every State member must have an entry (a partial
    section is a config error, matching tempo's strictness).
    """
    if "subdiv" not in config:
        return {}

    subdiv = config["subdiv"]
    if not isinstance(subdiv, dict):
        raise ValueError(
            f"'subdiv' must be a dict, got {type(subdiv).__name__}"
        )

    known_keys = {s.name.lower() for s in State}
    for key in subdiv:
        if key not in known_keys:
            logger.warning("subdiv: unrecognized key %r (not a State member)", key)

    def _check_value(v, ctx: str) -> None:
        # bool is an int subclass; reject it explicitly.
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"'subdiv[{ctx}]' must be an integer, got {v!r}")
        if v not in _ALLOWED_SUBDIV:
            raise ValueError(
                f"'subdiv[{ctx}]' must be a power of two in "
                f"{sorted(_ALLOWED_SUBDIV)}, got {v}"
            )

    for s in State:
        key = s.name.lower()
        if key not in subdiv:
            raise ValueError(f"'subdiv' is missing entry for state '{key}'")

        val = subdiv[key]
        if isinstance(val, list):
            if len(val) != 2:
                raise ValueError(
                    f"'subdiv[{key!r}]' must have exactly 2 elements "
                    f"[calm, agitated], got {len(val)}"
                )
            for v in val:
                _check_value(v, repr(key))
        else:
            _check_value(val, repr(key))

    return dict(subdiv)


def validate_program_params(config: dict) -> dict[str, dict]:
    """Validate and return the program_params section from a conductor config dict.

    Returns {} if the section is absent (optional section).
    If present, must be a dict of program_name → {sx: {base, scale}, ix: {base, scale}}.
    sx and ix sub-dicts are each optional; absent keys fall back to defaults at read time.
    base and scale must be numbers (int or float).
    Raises ValueError on structural errors.
    """
    if "program_params" not in config:
        return {}

    raw = config["program_params"]
    if not isinstance(raw, dict):
        raise ValueError(
            f"'program_params' must be a dict, got {type(raw).__name__}"
        )

    result: dict[str, dict] = {}
    for prog_name, prog_val in raw.items():
        if not isinstance(prog_val, dict):
            raise ValueError(
                f"'program_params[{prog_name!r}]' must be a dict, got {type(prog_val).__name__}"
            )
        prog_result: dict[str, dict] = {}
        for dim in ("sx", "ix"):
            if dim not in prog_val:
                continue
            sub = prog_val[dim]
            if not isinstance(sub, dict):
                raise ValueError(
                    f"'program_params[{prog_name!r}][{dim!r}]' must be a dict, got {type(sub).__name__}"
                )
            sub_result: dict[str, float | int] = {}
            for key in ("base", "scale"):
                if key not in sub:
                    continue
                val = sub[key]
                if not isinstance(val, (int, float)):
                    raise ValueError(
                        f"'program_params[{prog_name!r}][{dim!r}][{key!r}]' must be numeric, "
                        f"got {type(val).__name__}"
                    )
                sub_result[key] = val
            # Warn on unrecognized keys within the sx/ix sub-dict
            for k in sub:
                if k not in ("base", "scale"):
                    logger.warning(
                        "program_params[%r][%r]: unrecognized key %r (ignored)",
                        prog_name, dim, k,
                    )
            prog_result[dim] = sub_result
        # Warn on unrecognized keys at the program-entry level (e.g. typo 'iz' instead of 'ix')
        for k in prog_val:
            if k not in ("sx", "ix"):
                logger.warning(
                    "program_params[%r]: unrecognized key %r (ignored)",
                    prog_name, k,
                )
        result[prog_name] = prog_result

    return result


def load_conductor_config(path: str | Path | None = None) -> dict:
    """Load conductor.yaml, returning a plain dict.

    Loads from the repo-root conductor.yaml by default. Pass path to override.
    """
    source = Path(path) if path is not None else _DEFAULT_PATH
    if not source.exists():
        raise FileNotFoundError(f"Conductor config not found: {source}")
    with open(source, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
