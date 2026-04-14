import asyncio
import json
import logging
import struct
import time

import zenoh

from config.schema import TelemetryConfig
from telemetry.parser import extract_timestamp_delay
from state import SharedState, VehicleState

logger = logging.getLogger(__name__)

RELAY_HEADER_FMT = "dfdf"
RELAY_HEADER_SIZE = struct.calcsize(RELAY_HEADER_FMT)

_QOS_BE_LOW = dict(
    reliability=zenoh.Reliability.BEST_EFFORT,
    congestion_control=zenoh.CongestionControl.DROP,
    priority=zenoh.Priority.DATA_LOW,
)
_QOS_BE_HIGH = dict(
    reliability=zenoh.Reliability.BEST_EFFORT,
    congestion_control=zenoh.CongestionControl.DROP,
    priority=zenoh.Priority.INTERACTIVE_HIGH,
)
_QOS_REL_RT = dict(
    reliability=zenoh.Reliability.RELIABLE,
    congestion_control=zenoh.CongestionControl.BLOCK,
    priority=zenoh.Priority.REAL_TIME,
)
_QOS_REL_HIGH = dict(
    reliability=zenoh.Reliability.RELIABLE,
    congestion_control=zenoh.CongestionControl.BLOCK,
    priority=zenoh.Priority.INTERACTIVE_HIGH,
)

# suffix → QoS for GCS publishers
GCS_PUB_QOS = {
    "server_ping": _QOS_BE_LOW,
    "bot_ping": _QOS_BE_LOW,
    "bot_pong": _QOS_BE_LOW,
    "telemetry": _QOS_BE_LOW,
    "camera": _QOS_BE_HIGH,
    "teleop": _QOS_BE_HIGH,
    "estop": _QOS_REL_RT,
    "cmd_mode": _QOS_REL_HIGH,
    "station_pong": _QOS_BE_LOW,
}


class RobotProtocol:

    def __init__(
        self,
        state: SharedState,
        loop: asyncio.AbstractEventLoop,
        telemetry_cfg: TelemetryConfig = None,
    ):
        self.state = state
        self._loop = loop
        self._session: zenoh.Session | None = None
        self._cfg = telemetry_cfg or TelemetryConfig()
        self._subs: list = []
        self._seq = 0

        self._veh_pubs: dict[str, dict[str, zenoh.Publisher]] = {}
        self._veh_cam_bytes: dict[str, int] = {}
        self._veh_tele_bytes: dict[str, int] = {}
        self._bw_ts = time.time()
        self._veh_last_pong: dict[str, float] = {}

    def start(self, session: zenoh.Session) -> None:
        self._session = session
        self._subs = [
            session.declare_subscriber("nev/robot/**", self._on_robot),
        ]
        logger.info("RobotProtocol started (wildcard nev/robot/**)")

    def stop(self) -> None:
        for sub in self._subs:
            sub.undeclare()
        for pubs in self._veh_pubs.values():
            for pub in pubs.values():
                pub.undeclare()
        self._veh_pubs.clear()

    def _call(self, fn, *args):
        self._loop.call_soon_threadsafe(fn, *args)

    def _get_pub(self, vehicle_id: str, suffix: str) -> zenoh.Publisher:
        if vehicle_id not in self._veh_pubs:
            self._veh_pubs[vehicle_id] = {}
        pubs = self._veh_pubs[vehicle_id]
        if suffix not in pubs:
            key = f"nev/gcs/{vehicle_id}/{suffix}"
            qos = GCS_PUB_QOS.get(suffix, _QOS_BE_LOW)
            pubs[suffix] = self._session.declare_publisher(key, **qos)
            logger.info(f"Declared GCS publisher: {key}")
        return pubs[suffix]

    def _add_tele_bytes(self, vehicle_id: str, n: int):
        self._veh_tele_bytes[vehicle_id] = self._veh_tele_bytes.get(vehicle_id, 0) + n

    def _add_cam_bytes(self, vehicle_id: str, n: int):
        self._veh_cam_bytes[vehicle_id] = self._veh_cam_bytes.get(vehicle_id, 0) + n

    def _on_robot(self, sample):
        # nev/robot/{vehicle_id}/{topic...}
        parts = str(sample.key_expr).split("/")
        # parts: ['nev', 'robot', '{vehicle_id}', '{topic}', ...]
        if len(parts) < 4:
            return
        vehicle_id = parts[2]
        topic = "/".join(parts[3:])
        raw = bytes(sample.payload)

        if topic == "camera":
            self._handle_camera(vehicle_id, raw)
        elif topic == "server_pong":
            self._handle_server_pong(vehicle_id, raw)
        elif topic == "bot_pong":
            self._relay_bot_pong(vehicle_id, raw)
        elif topic == "video_stats":
            self._handle_video_stats(vehicle_id, raw)
        else:
            self._handle_telemetry(vehicle_id, topic, raw)

    def _handle_telemetry(self, vehicle_id: str, topic: str, raw: bytes):
        self._add_tele_bytes(vehicle_id, len(raw))
        try:
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"JSON parse error [{topic}]: {e}")
            return

        ts, tele_delay_ms = extract_timestamp_delay(data)

        if topic == "mux":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                veh.update_packet("mux", data)
                veh.update_remote_enabled(data.get("remote_enabled", False))
                if tele_delay_ms is not None:
                    veh.network.tele_delay_ms = tele_delay_ms

            self._call(_update)

        elif topic == "twist":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                veh.update_packet("twist", data)
                if tele_delay_ms is not None:
                    veh.network.tele_delay_ms = tele_delay_ms

            self._call(_update)

        elif topic == "estop":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                veh.update_packet("estop", data)
                if tele_delay_ms is not None:
                    veh.network.tele_delay_ms = tele_delay_ms

            self._call(_update)

        elif topic == "cpu" or topic == "mem":
            self._call(lambda: self.state.get_vehicle(vehicle_id).update_packet("resources", data))

        elif topic == "gpu":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                for g in data if isinstance(data, list) else []:
                    try:
                        veh.update_gpu(
                            g["idx"],
                            {
                                "gpu_usage": g["gpu_usage"],
                                "gpu_mem_used": g["gpu_mem_used"],
                                "gpu_mem_total": g["gpu_mem_total"],
                                "gpu_temp": g["gpu_temp"],
                                "gpu_power": g["gpu_power"],
                            },
                        )
                    except (KeyError, TypeError):
                        pass

            self._call(_update)

        elif topic == "disk":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                for p in data.get("partitions", []):
                    try:
                        veh.update_disk_partition(
                            p["idx"],
                            {
                                "mountpoint": p["mountpoint"],
                                "total_bytes": p["total_bytes"],
                                "used_bytes": p["used_bytes"],
                                "percent": p["percent"],
                                "accessible": p["accessible"],
                            },
                        )
                    except (KeyError, TypeError):
                        pass

            self._call(_update)

        elif topic == "net":

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                try:
                    veh.update_packet(
                        "resources",
                        {
                            "net_total_ifaces": data["net_total_ifaces"],
                            "net_active_ifaces": data["net_active_ifaces"],
                            "net_down_ifaces": data["net_down_ifaces"],
                        },
                    )
                except (KeyError, TypeError):
                    pass
                for iface in data.get("interfaces", []):
                    try:
                        veh.update_net_interface(
                            iface["idx"],
                            {
                                "name": iface["name"],
                                "is_up": iface["is_up"],
                                "speed_mbps": iface["speed_mbps"],
                                "in_bps": iface["in_bps"],
                                "out_bps": iface["out_bps"],
                            },
                        )
                    except (KeyError, TypeError):
                        pass

            self._call(_update)

        else:
            logger.debug(f"Unknown robot topic: nev/robot/{vehicle_id}/{topic}")

    def _handle_camera(self, vehicle_id: str, raw: bytes):
        try:
            t0 = time.perf_counter()
            if len(raw) <= self._cfg.camera_header_bytes:
                return
            server_rx_ts = time.time()
            ts, encode_ms = struct.unpack_from("df", raw, 0)
            hdr_size = self._cfg.camera_header_bytes
            nal_size = len(raw) - hdr_size
            self._add_cam_bytes(vehicle_id, len(raw))
            veh_to_srv_ms = max(0.0, (server_rx_ts - ts) * 1000.0)
            logger.debug(
                f"[{vehicle_id}] camera rx: {nal_size}B  enc={encode_ms}ms  delay={veh_to_srv_ms:.1f}ms"
            )

            out = bytearray(RELAY_HEADER_SIZE + nal_size)
            struct.pack_into(RELAY_HEADER_FMT, out, 0, ts, encode_ms, server_rx_ts, veh_to_srv_ms)
            out[RELAY_HEADER_SIZE:] = memoryview(raw)[hdr_size:]

            pub = self._get_pub(vehicle_id, "camera")
            pub.put(bytes(out))

            relay_ms = (time.perf_counter() - t0) * 1000.0

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                veh.network.video_net_delay = veh_to_srv_ms
                if relay_ms > veh.network.relay_max_ms:
                    veh.network.relay_max_ms = relay_ms

            self._call(_update)
        except Exception as e:
            logger.warning(f"camera frame parse error: {e}")

    def _handle_video_stats(self, vehicle_id: str, raw: bytes):
        data = json.loads(raw)

        def _update():
            veh = self.state.get_vehicle(vehicle_id)
            veh.network.bw_video_tx = data.get("bw_mbps", 0.0)
            veh.network.encode_delay = data.get("enc_avg_ms", 0.0)
            veh.video_stats = data

        self._call(_update)

    def _handle_server_pong(self, vehicle_id: str, raw: bytes):
        try:
            data = json.loads(raw)
            ts = data.get("ts")
            if ts is None:
                return
            rtt_ms = (time.time() - ts) * 1000.0
            if rtt_ms < 0:
                return
            logger.debug(f"[{vehicle_id}] server pong: rtt={rtt_ms:.1f}ms")

            def _update():
                veh = self.state.get_vehicle(vehicle_id)
                veh.network.rtt_server_bot_ms = round(rtt_ms, 1)
                self._veh_last_pong[vehicle_id] = time.monotonic()

            self._call(_update)
        except Exception as e:
            logger.warning(f"server pong parse error: {e}")

    def _relay_bot_pong(self, vehicle_id: str, raw: bytes):
        try:
            pub = self._get_pub(vehicle_id, "bot_pong")
            pub.put(raw)
        except Exception as e:
            logger.warning(f"bot_pong relay error: {e}")

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) % self._cfg.seq_max
        return s

    def _zput(self, vehicle_id: str, suffix: str, data: dict) -> None:
        try:
            pub = self._get_pub(vehicle_id, suffix)
            pub.put(json.dumps(data))
        except Exception as e:
            logger.warning(f"zenoh put [nev/gcs/{vehicle_id}/{suffix}]: {e}")

    def send_server_ping(self, vehicle_id: str):
        self._zput(vehicle_id, "server_ping", {"ts": time.time()})

    def send_teleop(self, vehicle_id: str, linear_x: float, steer_angle: float):
        self._zput(
            vehicle_id,
            "teleop",
            {
                "linear_x": round(linear_x, 3),
                "steer_angle": round(steer_angle, 4),
                "seq": self._next_seq(),
            },
        )

    def send_estop(self, vehicle_id: str, activate: bool):
        self._zput(vehicle_id, "estop", {"active": activate, "seq": self._next_seq()})

    def send_cmd_mode(self, vehicle_id: str, mode: int):
        self._zput(vehicle_id, "cmd_mode", {"mode": mode, "seq": self._next_seq()})

    def send_telemetry(self, state_json: str):
        """Broadcast aggregated telemetry to all connected vehicles' GCS topics."""
        for vehicle_id in list(self.state.vehicles.keys()):
            try:
                pub = self._get_pub(vehicle_id, "telemetry")
                pub.put(state_json)
            except Exception as e:
                logger.warning(f"zenoh put [nev/gcs/{vehicle_id}/telemetry]: {e}")

    def calc_bandwidth(self):
        now = time.time()
        dt = now - self._bw_ts
        if dt < self._cfg.bw_calc_interval:
            return
        self._bw_ts = now

        for vehicle_id in list(self.state.vehicles.keys()):
            cam_bytes = self._veh_cam_bytes.pop(vehicle_id, 0)
            tele_bytes = self._veh_tele_bytes.pop(vehicle_id, 0)
            cam_mbps = round(cam_bytes * 8 / (dt * 1e6), 3)
            tele_mbps = round(tele_bytes * 8 / (dt * 1e6), 3)

            def _update(vid=vehicle_id, cm=cam_mbps, tm=tele_mbps):
                veh = self.state.get_vehicle(vid)
                veh.network.bw_video_rx = cm
                veh.network.bw_telemetry = tm

            self._call(_update)

    def check_rtt_stale(self):
        now = time.monotonic()
        for vehicle_id in list(self.state.vehicles.keys()):
            last = self._veh_last_pong.get(vehicle_id, 0)
            if last > 0 and (now - last) > 3.0:

                def _update(vid=vehicle_id):
                    self.state.get_vehicle(vid).network.rtt_server_bot_ms = 0.0

                self._call(_update)
