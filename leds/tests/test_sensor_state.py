import threading

import pytest

from leds.sensor_state import GSR_PAIRS, NODE_GSR_MAPPING, SensorState


class TestSensorStateInitial:
    def test_cap_initial_length(self):
        state = SensorState()
        cap, _ = state.snapshot()
        assert len(cap) == 4

    def test_cap_initial_zeros(self):
        state = SensorState()
        cap, _ = state.snapshot()
        assert cap == [0, 0, 0, 0]

    def test_gsr_mag_initial_length(self):
        state = SensorState()
        _, gsr_mag = state.snapshot()
        assert len(gsr_mag) == 6

    def test_gsr_mag_initial_zeros(self):
        state = SensorState()
        _, gsr_mag = state.snapshot()
        assert gsr_mag == [0, 0, 0, 0, 0, 0]


class TestSetCap:
    @pytest.mark.parametrize("pad_index", [0, 1, 2, 3])
    def test_set_cap_updates_correct_slot(self, pad_index):
        state = SensorState()
        state.set_cap(pad_index, 0.75)
        cap, _ = state.snapshot()
        assert cap[pad_index] == pytest.approx(0.75)

    @pytest.mark.parametrize("pad_index", [0, 1, 2, 3])
    def test_set_cap_does_not_affect_other_slots(self, pad_index):
        state = SensorState()
        state.set_cap(pad_index, 0.5)
        cap, _ = state.snapshot()
        other = [cap[i] for i in range(4) if i != pad_index]
        assert all(v == 0 for v in other)

    def test_set_cap_overwrites_previous_value(self):
        state = SensorState()
        state.set_cap(2, 0.3)
        state.set_cap(2, 0.9)
        cap, _ = state.snapshot()
        assert cap[2] == pytest.approx(0.9)


class TestSetGsrMag:
    @pytest.mark.parametrize("global_pair_index", range(6))
    def test_set_gsr_mag_updates_correct_slot(self, global_pair_index):
        state = SensorState()
        state.set_gsr_mag(global_pair_index, mag=0.6)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[global_pair_index] == pytest.approx(0.6)

    @pytest.mark.parametrize("global_pair_index", range(6))
    def test_set_gsr_mag_does_not_affect_other_slots(self, global_pair_index):
        state = SensorState()
        state.set_gsr_mag(global_pair_index, mag=0.5)
        _, gsr_mag = state.snapshot()
        other = [gsr_mag[i] for i in range(6) if i != global_pair_index]
        assert all(v == 0 for v in other)

    def test_set_gsr_mag_overwrites_previous_value(self):
        state = SensorState()
        state.set_gsr_mag(3, mag=0.1)
        state.set_gsr_mag(3, mag=0.8)
        _, gsr_mag = state.snapshot()
        assert gsr_mag[3] == pytest.approx(0.8)


class TestSnapshot:
    def test_snapshot_returns_two_values(self):
        state = SensorState()
        result = state.snapshot()
        assert len(result) == 2

    def test_snapshot_cap_is_copy(self):
        state = SensorState()
        state.set_cap(0, 0.5)
        cap, _ = state.snapshot()
        cap[0] = 999
        cap2, _ = state.snapshot()
        assert cap2[0] == pytest.approx(0.5)

    def test_snapshot_gsr_mag_is_copy(self):
        state = SensorState()
        state.set_gsr_mag(0, mag=0.4)
        _, gsr_mag = state.snapshot()
        gsr_mag[0] = 999
        _, gsr_mag2 = state.snapshot()
        assert gsr_mag2[0] == pytest.approx(0.4)


class TestThreadSafety:
    def test_concurrent_writes_and_reads_do_not_crash(self):
        state = SensorState()
        errors = []

        def write_caps():
            try:
                for _ in range(200):
                    for i in range(4):
                        state.set_cap(i, float(i) * 0.1)
            except Exception as e:
                errors.append(e)

        def write_gsr():
            try:
                for _ in range(200):
                    for i in range(6):
                        state.set_gsr_mag(i, mag=float(i) * 0.05)
            except Exception as e:
                errors.append(e)

        def read_state():
            try:
                for _ in range(200):
                    state.snapshot()
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=write_caps) for _ in range(3)]
            + [threading.Thread(target=write_gsr) for _ in range(3)]
            + [threading.Thread(target=read_state) for _ in range(3)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


class TestConstants:
    def test_gsr_pairs_value(self):
        assert GSR_PAIRS == [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]

    def test_gsr_pairs_length(self):
        assert len(GSR_PAIRS) == 6

    def test_node_gsr_mapping_value(self):
        assert NODE_GSR_MAPPING == [[0, 1, 2], [3, 4, 0], [5, 1, 3], [2, 4, 5]]

    def test_node_gsr_mapping_length(self):
        assert len(NODE_GSR_MAPPING) == 4

    def test_node_gsr_mapping_node0(self):
        assert NODE_GSR_MAPPING[0] == [0, 1, 2]

    def test_node_gsr_mapping_node1(self):
        assert NODE_GSR_MAPPING[1] == [3, 4, 0]

    def test_node_gsr_mapping_node2(self):
        assert NODE_GSR_MAPPING[2] == [5, 1, 3]

    def test_node_gsr_mapping_node3(self):
        assert NODE_GSR_MAPPING[3] == [2, 4, 5]
