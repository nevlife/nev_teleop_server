import json
import time
import asyncio

from config.schema import TelemetryConfig
from state import SharedState, MuxStatus, Alert


class TestSharedStateUpdatePacket:
    def test_update_mux(self):
        s = SharedState()
        s.update_packet("mux", {"requested_mode": 2, "remote_enabled": True})
        assert s.mux.requested_mode == 2
        assert s.mux.remote_enabled is True

    def test_update_unknown_key_ignored(self):
        s = SharedState()
        s.update_packet("nonexistent", {"foo": 1})

    def test_unknown_field_ignored(self):
        s = SharedState()
        s.update_packet("mux", {"nonexistent_field": 99})
        assert not hasattr(s.mux, "nonexistent_field")

    def test_control_key_updates_last_control_recv(self):
        s = SharedState()
        assert s.last_control_recv == 0.0
        s.update_packet("mux", {"requested_mode": 0})
        assert s.last_control_recv > 0

    def test_non_control_key_does_not_update_control_recv(self):
        cfg = TelemetryConfig(control_keys=["mux"])
        s = SharedState(cfg)
        s.update_packet("resources", {"cpu_usage": 50.0})
        assert s.last_control_recv == 0.0

    def test_custom_control_keys(self):
        cfg = TelemetryConfig(control_keys=["twist"])
        s = SharedState(cfg)
        s.update_packet("mux", {"requested_mode": 0})
        assert s.last_control_recv == 0.0
        s.update_packet("twist", {"nav_lx": 1.0})
        assert s.last_control_recv > 0


class TestSharedStateListUpdates:
    def test_update_gpu(self):
        s = SharedState()
        s.update_gpu(0, {"gpu_usage": 80.0})
        assert s.gpu_list[0]["gpu_usage"] == 80.0

    def test_update_gpu_extends_list(self):
        s = SharedState()
        s.update_gpu(2, {"gpu_usage": 50.0})
        assert len(s.gpu_list) == 3
        assert s.gpu_list[2]["gpu_usage"] == 50.0

    def test_update_disk_partition(self):
        s = SharedState()
        s.update_disk_partition(0, {"mountpoint": "/", "percent": 45.0})
        assert s.disk_partitions[0]["percent"] == 45.0

    def test_update_net_interface(self):
        s = SharedState()
        s.update_net_interface(0, {"name": "eth0", "is_up": True})
        assert s.net_interfaces[0]["name"] == "eth0"


class TestSharedStateFlags:
    def test_update_remote_enabled(self):
        s = SharedState()
        s.update_remote_enabled(True)
        assert s.remote_enabled is True

    def test_update_station_connected(self):
        s = SharedState()
        s.update_station_connected(True)
        assert s.station_connected is True

    def test_update_joystick_connected(self):
        s = SharedState()
        s.update_joystick_connected(True)
        assert s.control.joystick_connected is True


class TestValidation:
    def test_estop_moving_alert(self):
        s = SharedState()
        s.estop.is_estop = True
        s.twist.final_lx = 1.0
        s._validate()
        assert any(a.level == "error" and "E-STOP" in a.message for a in s.alerts)

    def test_estop_pending_alert(self):
        s = SharedState()
        s.control.estop = True
        s.estop.is_estop = False
        s._validate()
        assert any(a.level == "warn" and "waiting" in a.message for a in s.alerts)

    def test_station_disconnected_alert(self):
        s = SharedState()
        s._validate()
        assert any(a.level == "warn" and "Station" in a.message for a in s.alerts)

    def test_no_robot_data_alert(self):
        s = SharedState()
        s.last_control_recv = time.monotonic() - 10.0
        s._validate()
        assert any(a.level == "error" and "No robot data" in a.message for a in s.alerts)

    def test_remote_mode_no_teleop_alert(self):
        s = SharedState()
        s.station_connected = True
        s.mux.requested_mode = 2
        s.mux.remote_enabled = True
        s.mux.teleop_active = False
        s._validate()
        assert any(a.level == "warn" and "teleop" in a.message.lower() for a in s.alerts)

    def test_clean_state_no_error_alerts(self):
        s = SharedState()
        s.station_connected = True
        s._validate()
        assert not any(a.level == "error" for a in s.alerts)


class TestSubscriberBroadcast:
    def test_broadcast_to_subscriber(self):
        s = SharedState()
        q = asyncio.Queue()
        s.add_subscriber(q)
        s._broadcast_sync()
        assert not q.empty()
        data = json.loads(q.get_nowait())
        assert "mux" in data
        assert "server_time" in data

    def test_remove_subscriber(self):
        s = SharedState()
        q = asyncio.Queue()
        s.add_subscriber(q)
        s.remove_subscriber(q)
        s._broadcast_sync()
        assert q.empty()


class TestToJson:
    def test_json_structure(self):
        s = SharedState()
        data = json.loads(s.to_json())
        expected_keys = [
            "mux",
            "twist",
            "network",
            "hunter",
            "estop",
            "resources",
            "gpu_list",
            "disk_partitions",
            "net_interfaces",
            "remote_enabled",
            "control",
            "station_connected",
            "alerts",
            "server_time",
            "robot_age",
        ]
        for key in expected_keys:
            assert key in data

    def test_robot_age_negative_when_no_recv(self):
        s = SharedState()
        data = json.loads(s.to_json())
        assert data["robot_age"] == -1
