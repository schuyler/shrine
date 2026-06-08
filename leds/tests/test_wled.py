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


class TestWledClientSend:
    def test_send_posts_to_correct_url(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(_make_segments())
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert url == "http://192.168.1.5:80/json/state"

    def test_send_returns_float_rtt_on_success(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert isinstance(result, float)
        assert result >= 0.0

    def test_send_rtt_uses_monotonic_time(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        call_times = [1000.0, 1000.025]  # 25 ms apart
        with patch("leds.wled.time.monotonic", side_effect=call_times):
            with patch("leds.wled.requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                result = client.send(_make_segments())
        assert result == pytest.approx(25.0)

    def test_send_request_body_has_seg(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        assert "seg" in body

    def test_send_request_body_col_field(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["col"] == [[10, 20, 30]]

    def test_send_request_body_bri_fx_sx_ix(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        segs = [_make_segment(col=[[10, 20, 30]], bri=100, fx=5, sx=64, ix=200)]
        with patch("leds.wled.requests.post") as mock_post:
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
        segs = [_make_segment(pal=3)]
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["pal"] == 3

    def test_send_request_body_on_field(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        segs = [_make_segment(on=False)]
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json") or mock_post.call_args[1].get("json")
        seg = body["seg"][0]
        assert seg["on"] is False

    def test_send_4_segments(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        segs = [_make_segment(col=[[i * 10, 0, 0]]) for i in range(4)]
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(segs)
        _, kwargs = mock_post.call_args
        body = kwargs.get("json")
        assert len(body["seg"]) == 4

    def test_send_uses_timeout(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=3)
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            client.send(_make_segments())
        _, kwargs = mock_post.call_args
        assert kwargs.get("timeout") == 3


class TestWledClientFailures:
    def test_timeout_returns_none(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post", side_effect=requests.Timeout()):
            result = client.send(_make_segments())
        assert result is None

    def test_connection_error_returns_none(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post", side_effect=requests.ConnectionError()):
            result = client.send(_make_segments())
        assert result is None

    def test_first_failure_logs_warning(self, caplog):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with caplog.at_level(logging.WARNING):
            with patch("leds.wled.requests.post", side_effect=requests.Timeout()):
                client.send(_make_segments())
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_repeated_failures_suppress_warning(self, caplog):
        """After the first failure warning, subsequent failures should not log more warnings."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post", side_effect=requests.Timeout()):
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
        mock_resp = MagicMock(status_code=500)
        mock_resp.raise_for_status.side_effect = requests.HTTPError()
        with patch("leds.wled.requests.post", return_value=mock_resp):
            result = client.send(_make_segments())
        assert result is None

    def test_recovery_after_failure_returns_float_rtt(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post", side_effect=requests.Timeout()):
            client.send(_make_segments())
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert isinstance(result, float)
        assert result >= 0.0

    def test_recovery_logs_message(self, caplog):
        """After a failure, a successful send should log a recovery message."""
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post", side_effect=requests.Timeout()):
            client.send(_make_segments())
        with caplog.at_level(logging.INFO):
            with patch("leds.wled.requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                client.send(_make_segments())
        assert any(r.levelno == logging.INFO for r in caplog.records)


class TestRttMeasurement:
    def test_rtt_calculation_with_mocked_time(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        # Simulate 10 ms round trip
        call_times = [5000.0, 5000.010]
        with patch("leds.wled.time.monotonic", side_effect=call_times):
            with patch("leds.wled.requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200)
                result = client.send(_make_segments())
        assert result == pytest.approx(10.0)

    def test_rtt_is_non_negative(self):
        client = WledClient(host="192.168.1.5", port=80, timeout=1)
        with patch("leds.wled.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = client.send(_make_segments())
        assert result >= 0.0
