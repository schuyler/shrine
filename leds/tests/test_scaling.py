"""Tests for the conductor scaling function.

Tests cover: normal scaling, passthrough when no config, clamp to [0,1],
and edge cases (zero range outputs 0).
"""

import pytest

from leds.conductor import _apply_scaling


class TestApplyScalingPassthrough:
    """When no scaling config is loaded, values pass through unchanged."""

    def test_no_config_returns_original_values(self):
        result = _apply_scaling({}, 0, 0.5, 0.0, 0.3, 0.4, 0.5)
        assert result == (0.5, 0.0, 0.3, 0.4, 0.5)

    def test_no_config_all_zeros(self):
        result = _apply_scaling({}, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert result == (0.0, 0.0, 0.0, 0.0, 0.0)

    def test_no_config_node_not_in_config(self):
        # Config has entries but not for this node
        cfg = {
            "node_1": {
                "stdev": {"floor": 0, "ceiling": 200},
                "gsr": {"floor": 0, "ceiling": 50},
            }
        }
        result = _apply_scaling(cfg, 0, 100.0, 0.0, 25.0, 25.0, 25.0)
        assert result == (100.0, 0.0, 25.0, 25.0, 25.0)


class TestApplyScalingNormal:
    """Normal scaling: clamp((raw - floor) / (ceiling - floor), 0, 1)."""

    def _cfg(self, stdev_floor=0, stdev_ceil=200, gsr_floor=0, gsr_ceil=50):
        return {
            f"node_{i}": {
                "stdev": {"floor": stdev_floor, "ceiling": stdev_ceil},
                "gsr": {"floor": gsr_floor, "ceiling": gsr_ceil},
            }
            for i in range(4)
        }

    def test_midpoint_values(self):
        cfg = self._cfg()
        result = _apply_scaling(cfg, 0, 100.0, 0.0, 25.0, 25.0, 25.0)
        assert result == pytest.approx((0.5, 0.0, 0.5, 0.5, 0.5))

    def test_floor_maps_to_zero(self):
        cfg = self._cfg(stdev_floor=10, stdev_ceil=110, gsr_floor=5, gsr_ceil=55)
        result = _apply_scaling(cfg, 0, 10.0, 0.0, 5.0, 5.0, 5.0)
        assert result == pytest.approx((0.0, 0.0, 0.0, 0.0, 0.0))

    def test_ceiling_maps_to_one(self):
        cfg = self._cfg()
        result = _apply_scaling(cfg, 0, 200.0, 0.0, 50.0, 50.0, 50.0)
        assert result == pytest.approx((1.0, 0.0, 1.0, 1.0, 1.0))

    def test_carrier_mag_always_passes_through(self):
        """carrier_mag (second float) is dead weight — always passed through."""
        cfg = self._cfg()
        result = _apply_scaling(cfg, 0, 100.0, 42.0, 25.0, 25.0, 25.0)
        assert result[1] == 42.0


class TestApplyScalingClamp:
    """Values outside [floor, ceiling] are clamped to [0, 1]."""

    def _cfg(self):
        return {
            f"node_{i}": {
                "stdev": {"floor": 0, "ceiling": 200},
                "gsr": {"floor": 0, "ceiling": 50},
            }
            for i in range(4)
        }

    def test_below_floor_clamps_to_zero(self):
        cfg = self._cfg()
        result = _apply_scaling(cfg, 0, -50.0, 0.0, -10.0, -5.0, -1.0)
        assert result[0] == 0.0
        assert result[2] == 0.0
        assert result[3] == 0.0
        assert result[4] == 0.0

    def test_above_ceiling_clamps_to_one(self):
        cfg = self._cfg()
        result = _apply_scaling(cfg, 0, 300.0, 0.0, 100.0, 80.0, 60.0)
        assert result[0] == 1.0
        assert result[2] == 1.0
        assert result[3] == 1.0
        assert result[4] == 1.0


class TestApplyScalingEdgeCases:
    """Edge cases: zero range, degenerate config."""

    def test_zero_range_outputs_zero(self):
        """ceiling == floor should output 0.0, not raise ZeroDivisionError.

        Matches firmware behavior: unconfigured channels output 0.
        """
        cfg = {
            f"node_{i}": {
                "stdev": {"floor": 100, "ceiling": 100},
                "gsr": {"floor": 0, "ceiling": 50},
            }
            for i in range(4)
        }
        result = _apply_scaling(cfg, 0, 100.0, 0.0, 25.0, 25.0, 25.0)
        assert result[0] == pytest.approx(0.0)


class TestApplyScalingPerNode:
    """Different nodes can have different scaling parameters."""

    def test_per_node_scaling(self):
        cfg = {
            "node_0": {
                "stdev": {"floor": 0, "ceiling": 100},
                "gsr": {"floor": 0, "ceiling": 100},
            },
            "node_1": {
                "stdev": {"floor": 0, "ceiling": 200},
                "gsr": {"floor": 0, "ceiling": 200},
            },
        }
        # Same raw value, different scaling
        r0 = _apply_scaling(cfg, 0, 50.0, 0.0, 50.0, 50.0, 50.0)
        r1 = _apply_scaling(cfg, 1, 50.0, 0.0, 50.0, 50.0, 50.0)
        assert r0[0] == pytest.approx(0.5)   # 50/100
        assert r1[0] == pytest.approx(0.25)  # 50/200
        # GSR also scales per-node
        assert r0[2] == pytest.approx(0.5)   # 50/100
        assert r1[2] == pytest.approx(0.25)  # 50/200
