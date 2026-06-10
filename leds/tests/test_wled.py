import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from leds.programs import SegmentParams
from leds.wled import WledClient


def _make_segment(col=None, bri=200, fx=0, sx=128, ix=128, pal=0, on=True):
    if col is None:
        col = [[255, 0, 0]]
    return SegmentParams(col=col, bri=bri, fx=fx, sx=sx, ix=ix, pal=pal, on=on)


def _make_segments(n=4):
    return [_make_segment() for _ in range(n)]


def _make_effects_response(effects=None):
    """Build a mock GET /json response with an effects list."""
    if effects is None:
        effects = ["Solid", "Blink", "Breathe", "Chase"]
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"effects": effects}
    return mock_resp


def _seed_effects(client, effects=None):
    """Pre-seed _effects on a WledClient so send() skips the lazy GET /json call."""
    if effects is None:
        effects = {}
    client._effects = effects


class TestWledClientInit:
    def test_stores_host(self):
        client = WledClient(host="192.168.1.10", port=80, timeout=2)
        assert client.host == "192.168.1.10"

    def test_stores_port(self):
        client = WledClient(host="192.168.1.10", port=80, timeout=2)
        assert client.port == 80

    def test_stores_timeout(self):
        client = WledClient(host="192.168.1.10", port=80, timeout=2)
        assert client.timeout == 2

    def test_effects_initially_none(self):
        client = WledClient(host="192.168.1.10", port=80, timeout=2)
        assert client._effects is None

    def test_effect_names_preseeds_effects_dict(self):
        names = ["Solid", "Blink", "Comet"]
        client = WledClient(host="192.168.1.10", port=80, timeout=2, effect_names=names)
        assert client._effects == {"solid": 0, "blink": 1, "comet": 2}

    def test_effect_names_skips_lazy_fetch(self):
        """When effect_names is provided, _resolve_effects must not be called on send."""
        names = ["Solid", "Comet"]
        client = WledClient(host="192.168.1.10", port=80, timeout=1, effect_names=names)
        with patch.object(client, "_resolve_effects") as mock_resolve:
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        mock_resolve.assert_not_called()


class TestWledClientSend:
    def test_send_posts_to_correct_url(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(_make_segments())
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert url == "http://192.168.1.5:80/json/state"

    def test_send_returns_float_rtt_on_success(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert isinstance(result, float)
        assert result >= 0.0

    def test_send_rtt_uses_monotonic_time(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        call_times = [1000.0, 1000.025]  # 25 ms apart
        with patch("leds.wled.time.monotonic", side_effect=call_times):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                result = client.send(_make_segments())
        assert result == pytest.approx(25.0)

    def test_send_request_body_has_seg(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "seg" in body

    def test_send_request_body_col_field(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["col"] == [[10, 20, 30]]

    def test_send_request_body_bri_fx_sx_ix(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["bri"] == 100
        assert seg["fx"] == 5
        assert seg["sx"] == 64
        assert seg["ix"] == 200

    def test_send_request_body_pal_field(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(pal=3)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["pal"] == 3

    def test_send_request_body_on_field(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(on=False)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["on"] is False

    def test_send_4_segments(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        segs = [_make_segment(col=[[i * 10, 0, 0]]) for i in range(4)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json")
        assert len(body["seg"]) == 4

    def test_send_uses_timeout(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=3)
        _seed_effects(client)
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(_make_segments())
        _, kwargs = mock_post.call_args
        assert kwargs.get("timeout") == 3


class TestWledClientFailures:
    def test_timeout_returns_none(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post", side_effect=requests.Timeout()):
            result = client.send(_make_segments())
        assert result is None

    def test_connection_error_returns_none(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post", side_effect=requests.ConnectionError()):
            result = client.send(_make_segments())
        assert result is None

    def test_first_failure_logs_warning(self, caplog):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with caplog.at_level(logging.WARNING):
            with patch.object(client._session, "post", side_effect=requests.Timeout()):
                client.send(_make_segments())
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_repeated_failures_suppress_warning(self, caplog):
        """After the first failure warning, subsequent failures should not log more warnings."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post", side_effect=requests.Timeout()):
            with caplog.at_level(logging.WARNING):
                client.send(_make_segments())  # first failure — may log
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                client.send(_make_segments())  # second failure — should not log
                client.send(_make_segments())  # third failure — should not log
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_http_error_returns_none(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        mock_resp = MagicMock(status_code=500)
        mock_resp.raise_for_status.side_effect = requests.HTTPError()
        with patch.object(client._session, "post", return_value=mock_resp):
            result = client.send(_make_segments())
        assert result is None

    def test_recovery_after_failure_returns_float_rtt(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post", side_effect=requests.Timeout()):
            client.send(_make_segments())
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert isinstance(result, float)
        assert result >= 0.0

    def test_recovery_logs_message(self, caplog):
        """After a failure, a successful send should log a recovery message."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post", side_effect=requests.Timeout()):
            client.send(_make_segments())
        with caplog.at_level(logging.INFO):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        assert any(r.levelno == logging.INFO for r in caplog.records)


class TestRttMeasurement:
    def test_rtt_calculation_with_mocked_time(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        # Simulate 10 ms round trip
        call_times = [5000.0, 5000.010]
        with patch("leds.wled.time.monotonic", side_effect=call_times):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                result = client.send(_make_segments())
        assert result == pytest.approx(10.0)

    def test_rtt_is_non_negative(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client)
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert result >= 0.0


class TestEffectResolution:
    def test_resolve_effects_called_lazily_on_first_send(self):
        """_resolve_effects must be called on the first send when _effects is None."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        assert client._effects is None
        with patch.object(client, "_resolve_effects", wraps=client._resolve_effects) as mock_resolve:
            with patch.object(client._session, "get", return_value=_make_effects_response()):
                with patch.object(client._session, "post") as mock_post:
                    mock_post.return_value = MagicMock(status_code=200)
                    client.send(_make_segments())
        mock_resolve.assert_called_once()

    def test_resolve_effects_not_called_again_on_second_send(self):
        """After the first send, _resolve_effects must not be called again."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch.object(client._session, "get", return_value=_make_effects_response()):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        with patch.object(client, "_resolve_effects") as mock_resolve:
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        mock_resolve.assert_not_called()

    def test_resolve_effects_builds_lowercase_name_to_id_map(self):
        """Effect names from /json response are mapped lowercase name → index."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        effects = ["Solid", "Blink", "Chase", "Breathe"]
        with patch.object(client._session, "get", return_value=_make_effects_response(effects)):
            client._resolve_effects()
        assert client._effects == {"solid": 0, "blink": 1, "chase": 2, "breathe": 3}

    def test_string_fx_resolved_to_int_id_in_post_body(self):
        """A string fx value must be resolved to its int ID in the POST body."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        effects = ["Solid", "Blink", "Chase"]
        _seed_effects(client, {name.lower(): idx for idx, name in enumerate(effects)})
        segs = [_make_segment(fx="Chase")]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["seg"][0]["fx"] == 2

    def test_string_fx_resolution_is_case_insensitive(self):
        """Effect name lookup must be case-insensitive."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client, {"chase": 2, "solid": 0})
        segs = [_make_segment(fx="CHASE")]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["seg"][0]["fx"] == 2

    def test_unknown_string_fx_falls_back_to_zero(self):
        """An unrecognized effect name must produce fx=0 (Solid) in the POST body."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client, {"solid": 0, "chase": 2})
        segs = [_make_segment(fx="NonExistentEffect")]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["seg"][0]["fx"] == 0

    def test_unknown_string_fx_logs_warning(self, caplog):
        """An unrecognized effect name must log a warning."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client, {"solid": 0})
        segs = [_make_segment(fx="NonExistentEffect")]
        with caplog.at_level(logging.WARNING):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(segs)
        assert any("NonExistentEffect" in r.message for r in caplog.records)

    def test_unknown_string_fx_warning_logged_only_once(self, caplog):
        """Warning for an unrecognized effect name must only be logged once across multiple sends."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client, {"solid": 0})
        segs = [_make_segment(fx="Ghost")]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            with caplog.at_level(logging.WARNING):
                client.send(segs)
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                client.send(segs)
                client.send(segs)
        warning_records = [r for r in caplog.records if "Ghost" in r.message]
        assert len(warning_records) == 0

    def test_integer_fx_passes_through_unchanged(self):
        """An integer fx value must be used as-is without any lookup."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        _seed_effects(client, {"solid": 0, "chase": 2})
        segs = [_make_segment(fx=17)]
        with patch.object(client._session, "post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["seg"][0]["fx"] == 17

    def test_resolve_effects_failure_sets_empty_dict(self):
        """A connection error during effect resolution must set _effects to {} (not None)."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch.object(client._session, "get", side_effect=requests.ConnectionError()):
            client._resolve_effects()
        assert client._effects == {}

    def test_resolve_effects_failure_logs_warning(self, caplog):
        """A connection error during effect resolution must log a warning."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with caplog.at_level(logging.WARNING):
            with patch.object(client._session, "get", side_effect=requests.ConnectionError()):
                client._resolve_effects()
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_resolve_effects_failure_causes_fx_zero_fallback(self):
        """When effect resolution fails, string fx values must fall back to fx=0."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch.object(client._session, "get", side_effect=requests.ConnectionError()):
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                segs = [_make_segment(fx="Chase")]
                client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs["json"]
        assert body["seg"][0]["fx"] == 0

    def test_resolve_effects_not_retried_after_failure(self):
        """After a failed resolution, _resolve_effects must not be called again on subsequent sends."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch.object(client._session, "get", side_effect=requests.ConnectionError()):
            client._resolve_effects()
        assert client._effects == {}
        # _effects is now {} (not None), so lazy init should not trigger again
        with patch.object(client, "_resolve_effects") as mock_resolve:
            with patch.object(client._session, "post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        mock_resolve.assert_not_called()
