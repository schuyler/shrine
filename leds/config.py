"""Configuration loader for the leds package."""

from pathlib import Path

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"


def load_config(path=None) -> dict:
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if path is not None:
        custom_path = Path(path)
        if not custom_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(custom_path, encoding="utf-8") as f:
            custom = yaml.safe_load(f) or {}
        config.update(custom)

    return config
