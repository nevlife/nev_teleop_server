import asyncio
import json
import time
from unittest.mock import MagicMock, patch

from config.schema import TelemetryConfig
from state import SharedState
from robot_bridge import RobotProtocol


def make_proto(telemetry_cfg=None):
    loop = asyncio.new_event_loop()
    state = SharedState(telemetry_cfg)
    cfg = telemetry_cfg or TelemetryConfig()
    proto = RobotProtocol(state, loop, cfg)
    return proto, state, loop


class TestSeqCounter:
    def test_increments(self):
        proto, _, _ = make_proto()
        assert proto._next_seq() == 0
        assert proto._next_seq() == 1
        assert proto._next_seq() == 2

    def test_wraps_at_seq_max(self):
        cfg = TelemetryConfig(seq_max=4)
        proto, _, _ = make_proto(cfg)
        for _ in range(4):
            proto._next_seq()
        assert proto._next_seq() == 0


class TestBandwidthCalc:
    def test_calc_bandwidth(self):
        proto, state, loop = make_proto()
        proto._cam_bytes = 1_000_000
        proto._tele_bytes = 100_000
        proto._bw_ts = time.time() - 1.0

        proto._loop = MagicMock()
        proto._loop.call_soon_threadsafe = lambda fn, *a: fn(*a) if callable(fn) else None

        proto.calc_bandwidth()
        assert state.network.bw_video_rx > 0
        assert state.network.bw_telemetry > 0

    def test_no_calc_before_interval(self):
        proto, state, _ = make_proto()
        proto._cam_bytes = 1_000_000
        proto._bw_ts = time.time()
        proto.calc_bandwidth()
        assert state.network.bw_video_rx == 0.0


class TestSendMethods:
    def test_send_heartbeat(self):
        proto, _, _ = make_proto()
        mock_pub = MagicMock()
        proto._pubs['nev/gcs/heartbeat'] = mock_pub
        proto.send_heartbeat()
        mock_pub.put.assert_called_once()
        data = json.loads(mock_pub.put.call_args[0][0])
        assert 'ts' in data
        assert 'seq' in data

    def test_send_teleop(self):
        proto, _, _ = make_proto()
        mock_pub = MagicMock()
        proto._pubs['nev/gcs/teleop'] = mock_pub
        proto.send_teleop(1.5, 0.3)
        data = json.loads(mock_pub.put.call_args[0][0])
        assert data['linear_x'] == 1.5
        assert data['angular_z'] == 0.3

    def test_send_estop(self):
        proto, _, _ = make_proto()
        mock_pub = MagicMock()
        proto._pubs['nev/gcs/estop'] = mock_pub
        proto.send_estop(True)
        data = json.loads(mock_pub.put.call_args[0][0])
        assert data['active'] is True

    def test_send_cmd_mode(self):
        proto, _, _ = make_proto()
        mock_pub = MagicMock()
        proto._pubs['nev/gcs/cmd_mode'] = mock_pub
        proto.send_cmd_mode(2)
        data = json.loads(mock_pub.put.call_args[0][0])
        assert data['mode'] == 2

    def test_zput_exception_no_crash(self):
        proto, _, _ = make_proto()
        mock_pub = MagicMock()
        mock_pub.put.side_effect = RuntimeError("connection lost")
        proto._pubs['nev/gcs/heartbeat'] = mock_pub
        proto.send_heartbeat()
