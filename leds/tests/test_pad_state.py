import threading

import pytest

from leds.pad_state import EffectOverride, PadSnapshot, PadState


class TestEffectOverrides:
    def test_no_overrides_initially(self):
        state = PadState([0, 1, 2, 3])
        assert state.effect_overrides() == {}

    def test_set_effect_records_override(self):
        state = PadState([0, 1, 2, 3])
        ov = EffectOverride(fx=9)
        state.set_effect(1, ov)
        assert state.effect_overrides() == {1: ov}

    def test_set_effect_unknown_pad_ignored(self):
        state = PadState([0, 1, 2, 3])
        state.set_effect(99, EffectOverride(fx=9))
        assert state.effect_overrides() == {}

    def test_clear_effect_removes_one(self):
        state = PadState([0, 1, 2, 3])
        state.set_effect(0, EffectOverride(fx=1))
        state.set_effect(1, EffectOverride(fx=2))
        state.clear_effect(0)
        assert set(state.effect_overrides()) == {1}

    def test_clear_effect_missing_pad_is_noop(self):
        state = PadState([0, 1, 2, 3])
        state.clear_effect(2)  # never set; must not raise
        assert state.effect_overrides() == {}

    def test_clear_all_effects(self):
        state = PadState([0, 1, 2, 3])
        state.set_effect(0, EffectOverride(fx=1))
        state.set_effect(3, EffectOverride(fx=2))
        state.clear_all_effects()
        assert state.effect_overrides() == {}

    def test_effect_overrides_returns_copy(self):
        state = PadState([0, 1, 2, 3])
        state.set_effect(0, EffectOverride(fx=1))
        snapshot = state.effect_overrides()
        snapshot[0] = EffectOverride(fx=999)
        assert state.effect_overrides()[0].fx == 1

    def test_overrides_not_in_state_snapshot_tuple(self):
        # snapshot() must keep its 6-tuple shape for existing consumers.
        state = PadState([0, 1, 2, 3])
        state.set_effect(0, EffectOverride(fx=1))
        assert len(state.snapshot()) == 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestPadStateInit:
    def test_snapshot_returns_correct_number_of_pads(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        assert len(snapshots) == 4

    def test_snapshot_initial_cap_all_zero(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.cap == pytest.approx(0.0)

    def test_snapshot_initial_heartbeat_all_zero(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.heartbeat == pytest.approx(0.0)

    def test_snapshot_initial_flux_all_zero(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.flux == pytest.approx(0.0)

    def test_snapshot_initial_program_empty(self):
        state = PadState([0, 1, 2, 3])
        _, program, *_ = state.snapshot()
        assert program == ""

    def test_snapshot_initial_palette_empty(self):
        state = PadState([0, 1, 2, 3])
        _, program, palette, *_ = state.snapshot()
        assert palette == ""

    def test_snapshot_initial_bpm_zero(self):
        state = PadState([0, 1, 2, 3])
        _, program, palette, bpm, *_ = state.snapshot()
        assert bpm == pytest.approx(0.0)

    def test_snapshot_initial_sync_time_zero(self):
        state = PadState([0, 1, 2, 3])
        _, program, palette, bpm, sync_time, *_ = state.snapshot()
        assert sync_time == pytest.approx(0.0)

    def test_snapshot_initial_tempo_gen_zero(self):
        state = PadState([0, 1, 2, 3])
        *_, tempo_gen = state.snapshot()
        assert tempo_gen == 0

    def test_snapshot_returns_pad_snapshots(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert isinstance(snap, PadSnapshot)

    def test_subset_pads_returns_correct_count(self):
        state = PadState([1, 3])
        snapshots, *_ = state.snapshot()
        assert len(snapshots) == 2


class TestPadStateSetCap:
    def test_set_cap_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        state.set_cap(0, 0.75)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.75)

    def test_set_cap_updates_second_pad(self):
        state = PadState([0, 1, 2, 3])
        state.set_cap(1, 0.5)
        snapshots, *_ = state.snapshot()
        assert snapshots[1].cap == pytest.approx(0.5)

    def test_set_cap_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        state.set_cap(2, 0.9)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.0)
        assert snapshots[1].cap == pytest.approx(0.0)
        assert snapshots[3].cap == pytest.approx(0.0)

    def test_set_cap_unknown_pad_is_noop(self):
        state = PadState([0, 1, 2, 3])
        state.set_cap(99, 0.8)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.cap == pytest.approx(0.0)

    def test_set_cap_subset_ignores_unconfigured_pad(self):
        state = PadState([1, 3])
        state.set_cap(0, 0.5)
        state.set_cap(2, 0.5)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.cap == pytest.approx(0.0)

    def test_set_cap_subset_updates_configured_pad(self):
        state = PadState([1, 3])
        state.set_cap(1, 0.6)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.6)


class TestPadStateSetHeartbeat:
    def test_set_heartbeat_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        state.set_heartbeat(2, 1.2)
        snapshots, *_ = state.snapshot()
        assert snapshots[2].heartbeat == pytest.approx(1.2)

    def test_set_heartbeat_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        state.set_heartbeat(0, 0.8)
        snapshots, *_ = state.snapshot()
        assert snapshots[1].heartbeat == pytest.approx(0.0)
        assert snapshots[2].heartbeat == pytest.approx(0.0)
        assert snapshots[3].heartbeat == pytest.approx(0.0)

    def test_set_heartbeat_unknown_pad_is_noop(self):
        state = PadState([0, 1, 2, 3])
        state.set_heartbeat(5, 2.0)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.heartbeat == pytest.approx(0.0)

    def test_set_heartbeat_subset_ignores_unconfigured_pad(self):
        state = PadState([1, 3])
        state.set_heartbeat(0, 1.5)
        state.set_heartbeat(2, 1.5)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.heartbeat == pytest.approx(0.0)

    def test_set_heartbeat_subset_updates_configured_pad(self):
        state = PadState([1, 3])
        state.set_heartbeat(3, 1.8)
        snapshots, *_ = state.snapshot()
        # pad 3 is second in [1, 3] → snapshots[1]
        assert snapshots[1].heartbeat == pytest.approx(1.8)


class TestPadStateSetFlux:
    def test_set_flux_updates_correct_pad(self):
        state = PadState([0, 1, 2, 3])
        state.set_flux(3, 0.33)
        snapshots, *_ = state.snapshot()
        assert snapshots[3].flux == pytest.approx(0.33)

    def test_set_flux_does_not_affect_other_pads(self):
        state = PadState([0, 1, 2, 3])
        state.set_flux(1, 0.7)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].flux == pytest.approx(0.0)
        assert snapshots[2].flux == pytest.approx(0.0)
        assert snapshots[3].flux == pytest.approx(0.0)

    def test_set_flux_unknown_pad_is_noop(self):
        state = PadState([0, 1, 2, 3])
        state.set_flux(10, 0.5)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.flux == pytest.approx(0.0)

    def test_set_flux_subset_ignores_unconfigured_pad(self):
        state = PadState([1, 3])
        state.set_flux(0, 0.9)
        state.set_flux(2, 0.9)
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.flux == pytest.approx(0.0)

    def test_set_flux_subset_updates_configured_pad(self):
        state = PadState([1, 3])
        state.set_flux(1, 0.45)
        snapshots, *_ = state.snapshot()
        # pad 1 is first in [1, 3] → snapshots[0]
        assert snapshots[0].flux == pytest.approx(0.45)


class TestPadStateSetProgram:
    def test_set_program_updates_program_in_snapshot(self):
        state = PadState([0, 1, 2, 3])
        state.set_program("pulse")
        _, program, *_ = state.snapshot()
        assert program == "pulse"

    def test_set_program_overwrite(self):
        state = PadState([0, 1, 2, 3])
        state.set_program("pulse")
        state.set_program("wave")
        _, program, *_ = state.snapshot()
        assert program == "wave"


class TestPadStateSetPalette:
    def test_set_palette_updates_palette_in_snapshot(self):
        state = PadState([0, 1, 2, 3])
        state.set_palette("fire")
        _, program, palette, *_ = state.snapshot()
        assert palette == "fire"

    def test_set_palette_overwrite(self):
        state = PadState([0, 1, 2, 3])
        state.set_palette("fire")
        state.set_palette("ocean")
        _, program, palette, *_ = state.snapshot()
        assert palette == "ocean"


class TestPadStateSetTempo:
    def test_set_tempo_updates_bpm(self):
        state = PadState([0, 1, 2, 3])
        state.set_tempo(120.0, 1000.0)
        _, program, palette, bpm, *_ = state.snapshot()
        assert bpm == pytest.approx(120.0)

    def test_set_tempo_updates_sync_time(self):
        state = PadState([0, 1, 2, 3])
        state.set_tempo(120.0, 1234.5)
        _, program, palette, bpm, sync_time, *_ = state.snapshot()
        assert sync_time == pytest.approx(1234.5)

    def test_set_tempo_increments_tempo_gen(self):
        state = PadState([0, 1, 2, 3])
        state.set_tempo(120.0, 0.0)
        *_, tempo_gen = state.snapshot()
        assert tempo_gen == 1

    def test_set_tempo_multiple_calls_increment_tempo_gen(self):
        state = PadState([0, 1, 2, 3])
        state.set_tempo(120.0, 0.0)
        state.set_tempo(90.0, 1.0)
        state.set_tempo(60.0, 2.0)
        *_, tempo_gen = state.snapshot()
        assert tempo_gen == 3

    def test_set_tempo_duplicate_values_still_increments(self):
        state = PadState([0, 1, 2, 3])
        state.set_tempo(120.0, 0.0)
        state.set_tempo(120.0, 0.0)
        *_, tempo_gen = state.snapshot()
        assert tempo_gen == 2


class TestPadStateSnapshotOrder:
    def test_snapshot_order_matches_pads_list(self):
        state = PadState([0, 1, 2, 3])
        state.set_cap(0, 0.1)
        state.set_cap(1, 0.2)
        state.set_cap(2, 0.3)
        state.set_cap(3, 0.4)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.1)
        assert snapshots[1].cap == pytest.approx(0.2)
        assert snapshots[2].cap == pytest.approx(0.3)
        assert snapshots[3].cap == pytest.approx(0.4)

    def test_snapshot_order_matches_subset_pads_list(self):
        state = PadState([1, 3])
        state.set_cap(1, 0.6)
        state.set_cap(3, 0.8)
        snapshots, *_ = state.snapshot()
        assert snapshots[0].cap == pytest.approx(0.6)
        assert snapshots[1].cap == pytest.approx(0.8)


class TestPadStateThreadSafety:
    def test_snapshot_returns_consistent_data_under_concurrent_writes(self):
        state = PadState([0, 1, 2, 3])
        errors = []

        def writer():
            for i in range(100):
                state.set_cap(0, float(i) / 100)
                state.set_heartbeat(1, float(i) / 100)
                state.set_flux(2, float(i) / 100)
                state.set_program(f"prog{i}")
                state.set_palette(f"pal{i}")
                state.set_tempo(float(i), float(i))

        def reader():
            for _ in range(200):
                try:
                    result = state.snapshot()
                    snapshots, program, palette, bpm, sync_time, tempo_gen = result
                    assert len(snapshots) == 4
                    assert isinstance(program, str)
                    assert isinstance(palette, str)
                    assert isinstance(bpm, float)
                    assert isinstance(sync_time, float)
                    assert isinstance(tempo_gen, int)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ---------------------------------------------------------------------------
# PadSnapshot.signature_color
# ---------------------------------------------------------------------------

class TestPadSnapshotSignatureColor:

    def test_default_signature_color_is_none(self):
        snap = PadSnapshot(cap=0.0, heartbeat=0.0, flux=0.0)
        assert snap.signature_color is None

    def test_explicit_signature_color_stored(self):
        snap = PadSnapshot(cap=0.0, heartbeat=0.0, flux=0.0, signature_color=[255, 0, 0])
        assert snap.signature_color == [255, 0, 0]


# ---------------------------------------------------------------------------
# PadSnapshot.group
# ---------------------------------------------------------------------------

class TestPadSnapshotGroup:

    def test_default_group_is_empty_frozenset(self):
        snap = PadSnapshot(cap=0.0, heartbeat=0.0, flux=0.0)
        assert snap.group == frozenset()

    def test_explicit_group_stored(self):
        group = frozenset({0, 1, 2})
        snap = PadSnapshot(cap=0.0, heartbeat=0.0, flux=0.0, group=group)
        assert snap.group == frozenset({0, 1, 2})

    def test_group_included_in_snapshot_after_set_group(self):
        state = PadState([0, 1, 2, 3])
        state.set_group(frozenset({1, 3}))
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.group == frozenset({1, 3})

    def test_snapshot_group_empty_by_default(self):
        state = PadState([0, 1, 2, 3])
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.group == frozenset()

    def test_snapshot_group_updates_after_set_group(self):
        state = PadState([0, 1, 2, 3])
        state.set_group(frozenset({0, 2}))
        snapshots, *_ = state.snapshot()
        assert snapshots[0].group == frozenset({0, 2})
        assert snapshots[2].group == frozenset({0, 2})


# ---------------------------------------------------------------------------
# PadState.set_signature_colors
# ---------------------------------------------------------------------------

class TestPadStateSetSignatureColors:

    def test_set_signature_colors_populates_snapshots(self):
        state = PadState([0, 1, 2, 3])
        state.set_signature_colors({0: [255, 0, 0], 2: [0, 255, 0]})
        snapshots, *_ = state.snapshot()
        assert snapshots[0].signature_color == [255, 0, 0]
        assert snapshots[2].signature_color == [0, 255, 0]

    def test_pads_without_configured_color_get_none(self):
        state = PadState([0, 1, 2, 3])
        state.set_signature_colors({0: [255, 0, 0]})
        snapshots, *_ = state.snapshot()
        assert snapshots[1].signature_color is None
        assert snapshots[2].signature_color is None
        assert snapshots[3].signature_color is None

    def test_unknown_pad_numbers_are_silently_ignored(self):
        state = PadState([0, 1, 2, 3])
        # pad 99 not in configured pads — must not raise
        state.set_signature_colors({0: [255, 0, 0], 99: [0, 0, 255]})
        snapshots, *_ = state.snapshot()
        assert snapshots[0].signature_color == [255, 0, 0]

    def test_set_signature_colors_empty_mapping_leaves_all_none(self):
        state = PadState([0, 1, 2, 3])
        state.set_signature_colors({})
        snapshots, *_ = state.snapshot()
        for snap in snapshots:
            assert snap.signature_color is None

    def test_set_signature_colors_overwrite(self):
        state = PadState([0, 1, 2, 3])
        state.set_signature_colors({0: [255, 0, 0]})
        state.set_signature_colors({0: [0, 0, 255]})
        snapshots, *_ = state.snapshot()
        assert snapshots[0].signature_color == [0, 0, 255]
