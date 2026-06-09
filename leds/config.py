"""Configuration loader for the leds package."""

from pathlib import Path

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"


def _validate_wled_targets(targets, pads) -> None:
    seen_pads = set()
    for entry in targets:
        if "host" not in entry:
            raise ValueError("Each wled_targets entry must have a 'host' field")
        if "pad" not in entry:
            raise ValueError("Each wled_targets entry must have a 'pad' field")
        pad = entry["pad"]
        if pad in seen_pads:
            raise ValueError(f"Duplicate pad value {pad!r} in wled_targets")
        seen_pads.add(pad)
        color = entry.get("color")
        if color is not None:
            if not isinstance(color, list) or len(color) != 3 or not all(isinstance(c, int) for c in color):
                raise ValueError(
                    f"color in wled_targets entry must be a 3-element list of ints, got {color!r}"
                )
    pads_set = set(pads) if pads else set()
    if seen_pads != pads_set:
        raise ValueError(
            f"Pad values in wled_targets {sorted(seen_pads)} must exactly match "
            f"config pads {sorted(pads_set)}"
        )


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

    if not config.get("wled_targets"):
        raise ValueError("'wled_targets' must be present and non-empty in config")

    _validate_wled_targets(config["wled_targets"], config.get("pads", []))

    return config
