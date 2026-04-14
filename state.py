import json
import time
import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List

from config.schema import TelemetryConfig


@dataclass
class MuxStatus:
    requested_mode: int = -1
    active_source: int = -1
    remote_enabled: bool = False
    nav_active: bool = False
    teleop_active: bool = False
    final_active: bool = False


@dataclass
class TwistValues:
    nav_lx: float = 0.0
    nav_az: float = 0.0
    teleop_lx: float = 0.0
    teleop_az: float = 0.0
    final_lx: float = 0.0
    final_az: float = 0.0


@dataclass
class NetworkStatus:
    bw_video_rx: float = 0.0
    bw_telemetry: float = 0.0
    bw_video_tx: float = 0.0
    encode_delay: float = 0.0
    video_net_delay: float = 0.0
    tele_delay_ms: float = 0.0
    rtt_server_bot_ms: float = 0.0
    relay_max_ms: float = 0.0


@dataclass
class EStopStatus:
    is_estop: bool = False
    bridge_flag: int = 0
    mux_flag: int = 0


@dataclass
class SystemResources:
    cpu_usage: float = 0.0
    cpu_temp: float = 0.0
    cpu_load: float = 0.0
    ram_total: int = 0
    ram_used: int = 0
    net_total_ifaces: int = 0
    net_active_ifaces: int = 0
    net_down_ifaces: int = 0


@dataclass
class ControlState:
    mode: int = -1
    estop: bool = False
    linear_x: float = 0.0
    steer_angle_deg: float = 0.0
    joystick_connected: bool = False


@dataclass
class Alert:
    level: str = "ok"
    message: str = ""


class VehicleState:
    """Single vehicle state."""

    def __init__(self, vehicle_id: str, control_keys: frozenset):
        self.vehicle_id = vehicle_id
        self._control_keys = control_keys

        self.mux = MuxStatus()
        self.twist = TwistValues()
        self.network = NetworkStatus()
        self.estop = EStopStatus()
        self.resources = SystemResources()
        self.vehicle: dict[str, dict] = {}
        self.remote_enabled: bool = False
        self.video_stats: dict = {}

        self.last_robot_recv: float = 0.0
        self.last_control_recv: float = 0.0

        self.gpu_list: list = []
        self.disk_partitions: list = []
        self.net_interfaces: list = []

    def update_packet(self, key: str, data: dict):
        obj = getattr(self, key, None)
        if obj is None:
            return
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        now = time.monotonic()
        self.last_robot_recv = now
        if key in self._control_keys:
            self.last_control_recv = now

    def _upsert_list(self, lst: list, idx: int, data: dict):
        if idx > 64:
            return
        if idx >= len(lst):
            lst.extend({} for _ in range(idx - len(lst) + 1))
        lst[idx].update(data)

    def update_gpu(self, idx: int, data: dict):
        self._upsert_list(self.gpu_list, idx, data)
        self.last_robot_recv = time.monotonic()

    def update_disk_partition(self, idx: int, data: dict):
        self._upsert_list(self.disk_partitions, idx, data)
        self.last_robot_recv = time.monotonic()

    def update_net_interface(self, idx: int, data: dict):
        self._upsert_list(self.net_interfaces, idx, data)
        self.last_robot_recv = time.monotonic()

    def vehicle_update(self, subtopic: str, data: dict):
        self.vehicle[subtopic] = data
        now = time.monotonic()
        self.last_robot_recv = now
        self.last_control_recv = now

    def update_remote_enabled(self, val: bool):
        self.remote_enabled = val

    def to_dict(self) -> dict:
        def _d(obj):
            return dataclasses.asdict(obj)

        return {
            "vehicle_id": self.vehicle_id,
            "mux": _d(self.mux),
            "twist": _d(self.twist),
            "network": _d(self.network),
            "estop": _d(self.estop),
            "resources": _d(self.resources),
            "vehicle": self.vehicle,
            "gpu_list": self.gpu_list,
            "disk_partitions": self.disk_partitions,
            "net_interfaces": self.net_interfaces,
            "remote_enabled": self.remote_enabled,
            "video_stats": self.video_stats,
            "robot_age": (
                (time.monotonic() - self.last_control_recv) if self.last_control_recv > 0 else -1
            ),
        }


class SharedState:
    """Server-wide state managing multiple vehicles."""

    def __init__(self, telemetry_cfg: TelemetryConfig = None):
        self._control_keys = (telemetry_cfg or TelemetryConfig()).control_keys_set

        self.vehicles: dict[str, VehicleState] = {}

        self.station_connected: bool = False
        self.station_last_recv: float = 0.0
        self.control = ControlState()
        self.alerts: List[Alert] = []

    def get_vehicle(self, vehicle_id: str) -> VehicleState:
        if vehicle_id not in self.vehicles:
            self.vehicles[vehicle_id] = VehicleState(vehicle_id, self._control_keys)
        return self.vehicles[vehicle_id]

    def update_station_connected(self, val: bool):
        if self.station_connected != val:
            self.station_connected = val

    def update_joystick_connected(self, val: bool):
        if self.control.joystick_connected != val:
            self.control.joystick_connected = val

    def validate(self):
        alerts: List[Alert] = []

        for vid, veh in self.vehicles.items():
            if veh.estop.is_estop and (
                abs(veh.twist.final_lx) > 0.05 or abs(veh.twist.final_az) > 0.05
            ):
                alerts.append(Alert("error", f"[{vid}] E-STOP active but robot is moving!"))

            if self.control.estop and not veh.estop.is_estop:
                alerts.append(
                    Alert("warn", f"[{vid}] E-stop sent — waiting for robot confirmation")
                )

            if (
                veh.mux.requested_mode == 2
                and veh.mux.remote_enabled
                and not veh.mux.teleop_active
            ):
                alerts.append(
                    Alert("warn", f"[{vid}] Remote mode active but no teleop commands received")
                )

            if veh.last_control_recv > 0:
                age = time.monotonic() - veh.last_control_recv
                if age > 3.0:
                    alerts.append(Alert("error", f"[{vid}] No robot data for {age:.1f}s"))

        if not self.station_connected:
            alerts.append(Alert("warn", "Station not connected — control unavailable"))

        self.alerts = alerts

    def to_json(self) -> str:
        def _d(obj):
            return dataclasses.asdict(obj)

        vehicles_dict = {vid: veh.to_dict() for vid, veh in self.vehicles.items()}

        return json.dumps(
            {
                "vehicles": vehicles_dict,
                "station_connected": self.station_connected,
                "control": _d(self.control),
                "alerts": [_d(a) for a in self.alerts],
                "server_time": time.time(),
            }
        )
