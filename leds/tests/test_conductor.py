import random

from leds.conductor import _PENTATONIC_ROOTS, _ROOT_BASE, _pick_pentatonic_root


def test_pentatonic_roots_are_major_pentatonic():
    assert _PENTATONIC_ROOTS == tuple(_ROOT_BASE + i for i in (0, 2, 4, 7, 9))


def test_pick_is_always_in_scale():
    rng = random.Random(1234)
    for _ in range(200):
        assert _pick_pentatonic_root(rng=rng) in _PENTATONIC_ROOTS


def test_pick_avoids_immediate_repeat():
    rng = random.Random(0)
    prev = _PENTATONIC_ROOTS[0]
    for _ in range(200):
        nxt = _pick_pentatonic_root(exclude=prev, rng=rng)
        assert nxt != prev
        prev = nxt


def test_exclude_unknown_value_still_picks():
    # Excluding a note not in the scale must not empty the choices.
    rng = random.Random(7)
    assert _pick_pentatonic_root(exclude=999, rng=rng) in _PENTATONIC_ROOTS
