import asyncio
import json
import math
import time
from unittest.mock import MagicMock

from state import SharedState
from station_bridge import StationBridge


def make_bridge():
    loop = asyncio.new_event_loop()
    state = SharedState()
    proto = MagicMock()
    bridge = StationBridge(state, loop, proto)
    return bridge, state, proto, loop


class TestTeleop:
    def _make_sample(self, data):
        sample = MagicMock()
        sample.payload = json.dumps(data).encode()
        return sample

    def test_passthrough(self):
        bridge, state, proto, _ = make_bridge()
        state.station_connected = True
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._handle_teleop(
            "0", self._make_sample({"linear_x": 1.0, "steer_angle": 0.3}).payload
        )
        proto.send_teleop.assert_called_once_with("0", 1.0, 0.3)

    def test_not_connected_no_send(self):
        bridge, state, proto, _ = make_bridge()
        state.station_connected = False
        bridge._handle_teleop(
            "0", self._make_sample({"linear_x": 1.0, "steer_angle": 0.0}).payload
        )
        proto.send_teleop.assert_not_called()


class TestEstop:
    def test_estop_forwarded(self):
        bridge, state, proto, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._handle_estop("0", json.dumps({"active": True}).encode())
        proto.send_estop.assert_called_once_with("0", True)
        assert state.control.estop is True


class TestCmdMode:
    def test_cmd_mode_forwarded(self):
        bridge, state, proto, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._handle_cmd_mode("0", json.dumps({"mode": 2}).encode())
        proto.send_cmd_mode.assert_called_once_with("0", 2)
        assert state.control.mode == 2


class TestJoystick:
    def test_joystick_connected(self):
        bridge, state, _, _ = make_bridge()
        bridge._loop = MagicMock()
        bridge._loop.call_soon_threadsafe = lambda fn, *a: fn(*a)
        bridge._handle_joystick(json.dumps({"connected": True}).encode())
        assert state.control.joystick_connected is True
