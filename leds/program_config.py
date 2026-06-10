"""Thread-safe, hot-reloadable per-program LED effect parameters."""

import threading

_DEFAULTS = {
    "sx": {"base": 128, "scale": 0.0},
    "ix": {"base": 128, "scale": 0.0},
}

_params: dict[str, dict] = {}
_lock = threading.Lock()


def get_program_params(name: str) -> dict:
    """Returns nested params for the named program, with defaults merged in."""
    with _lock:
        raw = _params.get(name, {})
    return {
        "sx": {**_DEFAULTS["sx"], **raw.get("sx", {})},
        "ix": {**_DEFAULTS["ix"], **raw.get("ix", {})},
    }


def set_program_params(params: dict[str, dict]) -> None:
    """Atomically replace the params dict. Never mutate in place."""
    global _params
    with _lock:
        _params = params


def resolve_sx(params: dict, bpm: float) -> int:
    sx = params["sx"]
    return max(0, min(255, int(sx["base"] + sx["scale"] * bpm)))


def resolve_ix(params: dict, bpm: float) -> int:
    ix = params["ix"]
    return max(0, min(255, int(ix["base"] + ix["scale"] * bpm)))
