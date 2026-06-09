"""Config loader for the conductor state machine."""

from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).parent.parent / "conductor.yaml"


def load_conductor_config(path: str | Path | None = None) -> dict:
    """Load conductor.yaml, returning a plain dict.

    Loads from the repo-root conductor.yaml by default. Pass path to override.
    """
    source = Path(path) if path is not None else _DEFAULT_PATH
    if not source.exists():
        raise FileNotFoundError(f"Conductor config not found: {source}")
    with open(source, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
