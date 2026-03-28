import asyncio
import json
import math
import time
from unittest.mock import MagicMock

from config.schema import RobotConfig
from state import SharedState
from station_bridge import StationBridge


def make_bridge(wheelbase=0.650):
    loop = asyncio.new_event_loop()
    state = SharedState()
    proto = MagicMock()
    robot_cfg = RobotConfig(wheelbase=wheelbase)
    bridge = StationBridge(state, loop, proto, robot_cfg)
    return bridge, state, proto, loop


class TestHeartbeat:
    def test_recv_heartbeat_sets_connected(self):
        bridge, state, _, _ = make_bridge()
        assert state.station_connected is False
        bridge._recv_heartbeat()
        assert state.station_connected is True
        assert state.station_last_recv > 0


class TestTeleop:
    def _make_sample(self, data):
        sample = MagicMock()
        sample.payload = json.dumps(data).encode()
        return sample

    def test_zero_steer(self):
        bridge, state, proto, _ = make_bridge()
        state.station_connected = True
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._on_teleop(self._make_sample({'linear_x': 1.0, 'steer_angle': 0.0}))
        proto.send_teleop.assert_called_once_with(1.0, 0.0)

    def test_ackermann_conversion(self):
        wb = 0.650
        bridge, state, proto, _ = make_bridge(wb)
        state.station_connected = True
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)

        lx = 1.0
        steer = 0.3
        expected_az = lx * math.tan(steer) / wb

        bridge._on_teleop(self._make_sample({'linear_x': lx, 'steer_angle': steer}))
        actual_az = proto.send_teleop.call_args[0][1]
        assert abs(actual_az - expected_az) < 1e-6

    def test_low_speed_steer_passthrough(self):
        bridge, state, proto, _ = make_bridge()
        state.station_connected = True
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._on_teleop(self._make_sample({'linear_x': 0.01, 'steer_angle': 0.5}))
        proto.send_teleop.assert_called_once_with(0.01, 0.5)

    def test_not_connected_no_send(self):
        bridge, state, proto, _ = make_bridge()
        state.station_connected = False
        bridge._on_teleop(self._make_sample({'linear_x': 1.0, 'steer_angle': 0.0}))
        proto.send_teleop.assert_not_called()


class TestEstop:
    def test_estop_forwarded(self):
        bridge, state, proto, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        sample = MagicMock()
        sample.payload = json.dumps({'active': True}).encode()
        bridge._on_estop(sample)
        proto.send_estop.assert_called_once_with(True)
        assert state.control.estop is True


class TestCmdMode:
    def test_cmd_mode_forwarded(self):
        bridge, state, proto, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        sample = MagicMock()
        sample.payload = json.dumps({'mode': 2}).encode()
        bridge._on_cmd_mode(sample)
        proto.send_cmd_mode.assert_called_once_with(2)
        assert state.control.mode == 2


class TestJoystick:
    def test_joystick_connected(self):
        bridge, state, _, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        sample = MagicMock()
        sample.payload = json.dumps({'connected': True}).encode()
        bridge._on_joystick_connected(sample)
        assert state.control.joystick_connected is True
