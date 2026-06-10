"""WLED built-in effect name → ID lookup.

WLED addresses its built-in effects by numeric ``fx`` ID in the JSON API.
This module maps human-friendly names to those IDs so the controller can be
told to run e.g. "rainbow" rather than ``9``.

The named table is a curated subset of the most commonly used WLED effects.
Their IDs are stable across firmware versions (WLED only appends to the
effect list).  Any effect not in the table is still reachable by passing its
numeric ID directly — see :func:`resolve_effect`.
"""

# Canonical, stable WLED FX_MODE IDs for popular effects.
EFFECTS: dict[str, int] = {
    "solid": 0,
    "blink": 1,
    "breathe": 2,
    "wipe": 3,
    "wipe_random": 4,
    "random_colors": 5,
    "sweep": 6,
    "dynamic": 7,
    "colorloop": 8,
    "rainbow": 9,
    "scan": 10,
    "dual_scan": 11,
    "fade": 12,
    "theater": 13,
    "theater_rainbow": 14,
    "running": 15,
    "saw": 16,
    "twinkle": 17,
    "dissolve": 18,
    "sparkle": 20,
    "strobe": 23,
    "blink_rainbow": 26,
    "chase": 28,
    "chase_rainbow": 30,
    "rainbow_runner": 33,
    "colorful": 34,
    "fire_flicker": 45,
    "fire_2012": 66,
}


def _normalize(name: str) -> str:
    """Fold spaces/hyphens to underscores and lowercase for lenient matching."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def resolve_effect(token) -> int | None:
    """Resolve a name or numeric ID to a WLED ``fx`` integer.

    Accepts a known effect name (case- and separator-insensitive, so
    "Chase Rainbow", "chase-rainbow" and "chase_rainbow" all match) or a
    numeric ID as ``int`` or string.  Returns ``None`` if the token is
    neither a known name nor a non-negative integer.
    """
    if isinstance(token, bool):  # bool is an int subclass; reject explicitly
        return None
    if isinstance(token, int):
        return token if token >= 0 else None

    text = str(token).strip()
    if text.isdigit():
        return int(text)

    return EFFECTS.get(_normalize(text))


def effect_names() -> list[str]:
    """Sorted list of known effect names."""
    return sorted(EFFECTS)
