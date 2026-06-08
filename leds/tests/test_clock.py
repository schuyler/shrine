import pytest

from leds.clock import Clock, ClockPhase


class TestClockInit:
    def test_default_latency_offset_is_zero(self):
        clock = Clock()
        assert clock.latency_offset_ms == pytest.approx(0.0)

    def test_latency_offset_stored_from_constructor(self):
        clock = Clock(latency_offset_ms=100.0)
        assert clock.latency_offset_ms == pytest.approx(100.0)

    def test_latency_offset_property_set(self):
        clock = Clock()
        clock.latency_offset_ms = 50.0
        assert clock.latency_offset_ms == pytest.approx(50.0)

    def test_phase_before_sync_returns_zero_beat(self):
        clock = Clock()
        phase = clock.phase(0.0)
        assert phase.beat == pytest.approx(0.0)

    def test_phase_before_sync_returns_zero_bar(self):
        clock = Clock()
        phase = clock.phase(0.0)
        assert phase.bar == pytest.approx(0.0)

    def test_phase_before_sync_returns_zero_bpm(self):
        clock = Clock()
        phase = clock.phase(0.0)
        assert phase.bpm == pytest.approx(0.0)

    def test_phase_returns_clock_phase_instance(self):
        clock = Clock()
        phase = clock.phase(0.0)
        assert isinstance(phase, ClockPhase)


class TestClockSync:
    def test_sync_at_t0_beat_is_zero(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.beat == pytest.approx(0.0)

    def test_sync_at_t0_bar_is_zero(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.bar == pytest.approx(0.0)

    def test_sync_bpm_reflected_in_phase(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.bpm == pytest.approx(120.0)

    def test_120bpm_beat_at_quarter_period(self):
        # 120 BPM: beat period = 0.5s. At t=0.25, beat should be 0.5
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.25)
        assert phase.beat == pytest.approx(0.5)

    def test_120bpm_beat_wraps_at_one_period(self):
        # At t=0.5, one full beat has elapsed; beat wraps to 0.0
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.5)
        assert phase.beat == pytest.approx(0.0)

    def test_120bpm_bar_at_one_beat(self):
        # At t=0.5 (1 beat at 120 BPM), bar = 1/4 = 0.25
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.5)
        assert phase.bar == pytest.approx(0.25)

    def test_120bpm_bar_wraps_at_four_beats(self):
        # At t=2.0 (4 beats at 120 BPM = 1 bar), bar wraps to 0.0
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(2.0)
        assert phase.bar == pytest.approx(0.0)

    def test_resync_resets_phase(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        # Advance well into first sync
        clock.sync(bpm=120.0, sync_time=1.0)
        # At exactly the new sync_time, beat should be 0
        phase = clock.phase(1.0)
        assert phase.beat == pytest.approx(0.0)

    def test_resync_new_bpm_takes_effect(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        clock.sync(bpm=60.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.bpm == pytest.approx(60.0)

    def test_resync_new_bpm_and_sync_time(self):
        # First sync: 120 BPM from t=0. At t=1.0, beat = (1.0/0.5) % 1 = 0.0
        # Second sync: 60 BPM from t=0.5. At t=1.0, elapsed=0.5, beat = 0.5/1.0 = 0.5
        # This distinguishes using the second sync_time from the first.
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        clock.sync(bpm=60.0, sync_time=0.5)
        phase = clock.phase(1.0)
        assert phase.beat == pytest.approx(0.5)


class TestClockBpmVariants:
    def test_60bpm_beat_period_is_one_second(self):
        # 60 BPM: beat period = 1.0s. At t=0.5, beat = 0.5
        clock = Clock()
        clock.sync(bpm=60.0, sync_time=0.0)
        phase = clock.phase(0.5)
        assert phase.beat == pytest.approx(0.5)

    def test_60bpm_beat_wraps_at_one_second(self):
        clock = Clock()
        clock.sync(bpm=60.0, sync_time=0.0)
        phase = clock.phase(1.0)
        assert phase.beat == pytest.approx(0.0)

    def test_180bpm_beat_period_is_one_third_second(self):
        # 180 BPM: beat period = 1/3s. At t=1/6, beat = 0.5
        clock = Clock()
        clock.sync(bpm=180.0, sync_time=0.0)
        phase = clock.phase(1.0 / 6.0)
        assert phase.beat == pytest.approx(0.5)

    def test_180bpm_beat_wraps_correctly(self):
        clock = Clock()
        clock.sync(bpm=180.0, sync_time=0.0)
        phase = clock.phase(1.0 / 3.0)
        assert phase.beat == pytest.approx(0.0)


class TestClockLatencyOffset:
    def test_latency_offset_shifts_clock_forward(self):
        # 100ms offset at t=0 is equivalent to querying at t=0.1
        # 120 BPM, beat period=0.5s. At effective t=0.1, beat = 0.1/0.5 = 0.2
        clock = Clock(latency_offset_ms=100.0)
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.beat == pytest.approx(0.2)

    def test_zero_latency_offset_no_shift(self):
        clock = Clock(latency_offset_ms=0.0)
        clock.sync(bpm=120.0, sync_time=0.0)
        phase = clock.phase(0.0)
        assert phase.beat == pytest.approx(0.0)


class TestClockPhaseRange:
    def test_beat_always_in_zero_to_one(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        for i in range(20):
            t = i * 0.13
            phase = clock.phase(t)
            assert 0.0 <= phase.beat < 1.0

    def test_bar_always_in_zero_to_one(self):
        clock = Clock()
        clock.sync(bpm=120.0, sync_time=0.0)
        for i in range(20):
            t = i * 0.13
            phase = clock.phase(t)
            assert 0.0 <= phase.bar < 1.0
