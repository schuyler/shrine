"""Palette definitions and loader."""

from pathlib import Path

import yaml


class Palette:
    def __init__(self, name: str, colors: dict[str, list[int]]):
        self._name = name
        self._colors = colors

    @property
    def name(self) -> str:
        return self._name

    def get(self, key: str, default: list[int] | None = None) -> list[int]:
        if key in self._colors:
            return self._colors[key]
        if default is not None:
            return default
        return [0, 0, 0]


_DEFAULT_PALETTES_PATH = Path(__file__).parent / "default_palettes.yaml"


def load_palettes(path: Path | None = None) -> dict[str, "Palette"]:
    """Load palettes from YAML.

    When path is None, loads from leds/default_palettes.yaml.
    When path is given, loads only from that file (full replacement).
    Returns {name: Palette} dict.
    """
    source = path if path is not None else _DEFAULT_PALETTES_PATH
    with open(source) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Palette file {source} must contain a YAML mapping")
    return {name: Palette(name, colors) for name, colors in data.items()}
