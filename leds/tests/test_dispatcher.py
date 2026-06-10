"""Tests for WledDispatcher (multi-box WLED architecture)."""

import pytest

from leds.wled import WledDispatcher
from leds.programs import SegmentParams


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segment(col=None, bri=200, fx=0, sx=128, ix=128, pal=0, on=True):
    if col is None:
        col = [[255, 0, 0]]
    return SegmentParams(col=col, bri=bri, fx=fx, sx=sx, ix=ix, pal=pal, on=on)


def _minimal_targets():
    """Two targets, each owning one pad."""
    return [
        {"host": "192.168.1.10", "port": 80, "pad": 0},
        {"host": "192.168.1.11", "port": 80, "pad": 1},
    ]


# ---------------------------------------------------------------------------
# Init tests
# ---------------------------------------------------------------------------

class TestWledDispatcherInit:
    def test_creates_one_client_per_target(self):
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        assert len(dispatcher.clients) == 2

    def test_uses_top_level_port_default_when_target_omits_port(self):
        targets = [{"host": "192.168.1.10", "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=9999, timeout=0.1)
        client = dispatcher.clients[0]
        assert client.port == 9999

    def test_per_target_port_override_takes_precedence(self):
        targets = [{"host": "192.168.1.10", "port": 1234, "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        client = dispatcher.clients[0]
        assert client.port == 1234

    def test_empty_targets_raises_value_error(self):
        with pytest.raises(ValueError):
            WledDispatcher(targets=[], port=80, timeout=0.1)

    def test_effect_names_seeded_into_clients(self):
        """effect_names passed to WledDispatcher must be pre-loaded into each client."""
        names = ["Solid", "Blink", "Comet"]
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1,
                                    effect_names=names)
        for client in dispatcher.clients.values():
            assert client._effects == {"solid": 0, "blink": 1, "comet": 2}


# ---------------------------------------------------------------------------
# Send tests
# ---------------------------------------------------------------------------

class TestWledDispatcherSend:
    def test_send_routes_segment_to_correct_client_by_pad(self):
        """Segment for pad 0 goes to the client whose target has pad=0."""
        from unittest.mock import patch, MagicMock
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        seg = _make_segment()
        with patch.object(dispatcher.clients[0], "send", return_value=5.0) as mock_send_0, \
             patch.object(dispatcher.clients[1], "send", return_value=None):
            dispatcher.send({0: seg})
        mock_send_0.assert_called_once()

    def test_send_does_not_route_segment_to_wrong_client(self):
        """Segment for pad 0 must not reach the client for pad 1."""
        from unittest.mock import patch
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        seg = _make_segment()
        with patch.object(dispatcher.clients[0], "send", return_value=5.0), \
             patch.object(dispatcher.clients[1], "send", return_value=None) as mock_send_1:
            dispatcher.send({0: seg})
        mock_send_1.assert_not_called()

    def test_send_passes_single_segment_to_client(self):
        """Each client receives a single-element list containing its segment."""
        from unittest.mock import patch
        targets = [{"host": "192.168.1.10", "port": 80, "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        seg = _make_segment()
        with patch.object(dispatcher.clients[0], "send", return_value=5.0) as mock_send:
            dispatcher.send({0: seg})
        args = mock_send.call_args[0][0]
        assert len(args) == 1
        assert args[0] == seg

    def test_send_returns_max_rtt_among_successful_sends(self):
        from unittest.mock import patch
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        seg = _make_segment()
        with patch.object(dispatcher.clients[0], "send", return_value=10.0), \
             patch.object(dispatcher.clients[1], "send", return_value=25.0):
            result = dispatcher.send({0: _make_segment(), 1: _make_segment()})
        assert result == pytest.approx(25.0)

    def test_send_returns_none_when_all_sends_fail(self):
        from unittest.mock import patch
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        with patch.object(dispatcher.clients[0], "send", return_value=None), \
             patch.object(dispatcher.clients[1], "send", return_value=None):
            result = dispatcher.send({0: _make_segment(), 1: _make_segment()})
        assert result is None

    def test_one_dead_target_does_not_block_others(self):
        """A None return from one client must not prevent the other from being called."""
        from unittest.mock import patch
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        with patch.object(dispatcher.clients[0], "send", return_value=None), \
             patch.object(dispatcher.clients[1], "send", return_value=15.0) as mock_send_1:
            result = dispatcher.send({0: _make_segment(), 1: _make_segment()})
        mock_send_1.assert_called_once()
        assert result == pytest.approx(15.0)

    def test_segment_for_unconfigured_pad_is_silently_dropped(self):
        """A segment keyed to pad 99 (not in any target) produces no calls."""
        from unittest.mock import patch
        targets = [{"host": "192.168.1.10", "port": 80, "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        with patch.object(dispatcher.clients[0], "send", return_value=5.0) as mock_send:
            dispatcher.send({99: _make_segment()})
        mock_send.assert_not_called()

    def test_exception_in_one_send_does_not_kill_other_sends(self):
        """An exception raised by one client's future must not suppress the other."""
        from unittest.mock import patch
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        with patch.object(dispatcher.clients[0], "send", side_effect=RuntimeError("boom")), \
             patch.object(dispatcher.clients[1], "send", return_value=8.0) as mock_send_1:
            result = dispatcher.send({0: _make_segment(), 1: _make_segment()})
        mock_send_1.assert_called_once()
        assert result == pytest.approx(8.0)

    def test_sends_are_concurrent_via_thread_pool(self):
        """Dispatcher must use a ThreadPoolExecutor (submit, not sequential calls)."""
        from unittest.mock import patch, MagicMock
        import concurrent.futures
        targets = _minimal_targets()
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        submit_calls = []
        original_submit = dispatcher._executor.submit

        def tracking_submit(fn, *args, **kwargs):
            submit_calls.append(fn)
            return original_submit(fn, *args, **kwargs)

        with patch.object(dispatcher._executor, "submit", side_effect=tracking_submit):
            with patch.object(dispatcher.clients[0], "send", return_value=5.0), \
                 patch.object(dispatcher.clients[1], "send", return_value=5.0):
                dispatcher.send({0: _make_segment(), 1: _make_segment()})

        assert len(submit_calls) == 2


# ---------------------------------------------------------------------------
# Close test
# ---------------------------------------------------------------------------

class TestWledDispatcherClose:
    def test_close_shuts_down_executor_without_error(self):
        targets = [{"host": "192.168.1.10", "port": 80, "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        # Must not raise
        dispatcher.close()

    def test_close_is_idempotent(self):
        """Calling close twice must not raise."""
        targets = [{"host": "192.168.1.10", "port": 80, "pad": 0}]
        dispatcher = WledDispatcher(targets=targets, port=80, timeout=0.1)
        dispatcher.close()
        dispatcher.close()
