"""WLED built-in effect name → ID lookup.

WLED addresses its built-in effects by numeric ``fx`` ID in the JSON API.
This module maps human-friendly names to those IDs so the controller can be
told to run e.g. "rainbow" rather than ``9``.

The preferred source of truth is the node itself: :func:`fetch_effect_names`
pulls the live effect list from a WLED box (``GET /json/eff``), so names match
the running firmware exactly and the full effect set is covered.  The static
:data:`EFFECTS` table below is a curated fallback used when no node can be
reached (e.g. offline testing).  Either way, any effect is also reachable by
passing its numeric ID directly — see :func:`resolve_effect`.
"""

import logging

import requests

logger = logging.getLogger(__name__)

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


def resolve_effect(token, table: dict[str, int] = EFFECTS) -> int | None:
    """Resolve a name or numeric ID to a WLED ``fx`` integer.

    Accepts a known effect name (case- and separator-insensitive, so
    "Chase Rainbow", "chase-rainbow" and "chase_rainbow" all match) or a
    numeric ID as ``int`` or string.  ``table`` is the name→ID map to look
    names up in (defaults to the static :data:`EFFECTS`).  Returns ``None``
    if the token is neither a known name nor a non-negative integer.
    """
    if isinstance(token, bool):  # bool is an int subclass; reject explicitly
        return None
    if isinstance(token, int):
        return token if token >= 0 else None

    text = str(token).strip()
    if text.isdigit():
        return int(text)

    return table.get(_normalize(text))


def fetch_effect_names(host: str, port: int = 80, timeout: float = 2.0) -> list[str] | None:
    """Fetch the live effect list from a WLED node (``GET /json/eff``).

    Returns the effect names indexed by ``fx`` ID, or ``None`` if the node
    is unreachable or returns something unexpected.
    """
    url = f"http://{host}:{port}/json/eff"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not fetch WLED effects from %s: %s", url, exc)
        return None
    if not isinstance(data, list):
        logger.warning("Unexpected /json/eff payload from %s: %r", url, data)
        return None
    return [str(name) for name in data]


class EffectIndex:
    """Name→ID effect map, seeded from :data:`EFFECTS` and optionally
    augmented with names fetched live from a WLED node.

    Live names take precedence and extend coverage to the node's full effect
    set; the static seed keeps things working when no node is reachable.
    """

    def __init__(self):
        self._table = dict(EFFECTS)

    def update_from_names(self, names: list[str]) -> int:
        """Merge a WLED effect-name list (index = fx ID).  Returns count added."""
        added = 0
        for idx, name in enumerate(names):
            key = _normalize(name)
            if key:  # skip blank/reserved slots
                self._table[key] = idx
                added += 1
        return added

    def resolve(self, token) -> int | None:
        return resolve_effect(token, self._table)

    def names(self) -> list[str]:
        return sorted(self._table)


def effect_names() -> list[str]:
    """Sorted list of known (static) effect names."""
    return sorted(EFFECTS)
