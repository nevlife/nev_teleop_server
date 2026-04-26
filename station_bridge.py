import json
import logging
import math
import time

import zenoh

logger = logging.getLogger(__name__)


class StationBridge:
    def __init__(self, state, loop, robot_proto):
        self._state = state
        self._loop = loop
        self._proto = robot_proto
        self._subs: list = []

    def start(self, session) -> None:
        # nev/station/{vehicle_id}/{topic}
        self._session = session
        self._subs = [
            session.declare_subscriber("nev/station/**", self._on_station),
        ]
        logger.info("StationBridge started (wildcard nev/station/**)")

    def stop(self) -> None:
        for sub in self._subs:
            sub.undeclare()

    def _call(self, fn, *args):
        self._loop.call_soon_threadsafe(fn, *args)

    def _on_station(self, sample):
        # nev/station/{vehicle_id}/{topic}
        parts = str(sample.key_expr).split("/")
        if len(parts) < 4:
            return
        vehicle_id = parts[2]
        topic = parts[3]
        raw = bytes(sample.payload)

        self._call(self._state.get_vehicle, vehicle_id)

        if topic == "teleop":
            self._handle_teleop(vehicle_id, raw)

        elif topic == "estop":
            self._handle_estop(vehicle_id, raw)

        elif topic == "cmd_mode":
            self._handle_cmd_mode(vehicle_id, raw)

        elif topic == "controller_heartbeat":
            self._handle_joystick(raw)

        elif topic == "station_ping":
            self._handle_station_ping(vehicle_id, raw)

        elif topic == "bot_ping":
            self._relay_bot_ping(vehicle_id, raw)

    def _handle_teleop(self, vehicle_id: str, raw: bytes):
        try:
            data = json.loads(raw)
            if not self._state.station_connected:
                return
            lx = float(data.get("linear_x", 0.0))
            steer = float(data.get("steer_angle", 0.0))
            self._proto.send_teleop(vehicle_id, lx, steer)
            steer_deg = math.degrees(steer)
            self._call(self._update_control, lx, steer_deg)
        except Exception as e:
            logger.warning(f"station teleop parse error: {e}")

    def _handle_estop(self, vehicle_id: str, raw: bytes):
        try:
            data = json.loads(raw)
            active = bool(data.get("active", False))
            self._proto.send_estop(vehicle_id, active)
            self._call(self._update_estop, active)
            logger.info(f"[{vehicle_id}] Station e-stop -> {active}")
        except Exception as e:
            logger.warning(f"station estop parse error: {e}")

    def _handle_cmd_mode(self, vehicle_id: str, raw: bytes):
        try:
            data = json.loads(raw)
            mode = int(data.get("mode", -1))
            self._proto.send_cmd_mode(vehicle_id, mode)
            self._call(self._update_mode, mode)
            logger.info(f"[{vehicle_id}] Station cmd_mode -> {mode}")
        except Exception as e:
            logger.warning(f"station cmd_mode parse error: {e}")

    def _handle_joystick(self, raw: bytes):
        try:
            data = json.loads(raw)
            val = bool(data.get("connected", False))
            self._state.station_last_recv = time.monotonic()
            if not self._state.station_connected:
                self._state.update_station_connected(True)
            self._call(self._state.update_joystick_connected, val)
        except Exception as e:
            logger.warning(f"station joystick_connected parse error: {e}")

    def _handle_station_ping(self, vehicle_id: str, raw: bytes):
        try:
            data = json.loads(raw)
            ts = data.get("ts")
            if ts is None:
                return
            pub = self._proto._get_pub(vehicle_id, "station_pong")
            pub.put(json.dumps({"ts": ts}))
        except Exception as e:
            logger.warning(f"station ping parse error: {e}")

    def _relay_bot_ping(self, vehicle_id: str, raw: bytes):
        try:
            pub = self._proto._get_pub(vehicle_id, "bot_ping")
            pub.put(raw)
        except Exception as e:
            logger.warning(f"bot_ping relay error: {e}")

    def _update_control(self, lx: float, steer_deg: float):
        self._state.control.linear_x = lx
        self._state.control.steer_angle_deg = steer_deg

    def _update_estop(self, active: bool):
        self._state.control.estop = active

    def _update_mode(self, mode: int):
        self._state.control.mode = mode
