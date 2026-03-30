import asyncio
import json
import logging
import struct
import time

import zenoh

from zenoh_utils.protocol import GCS_QOS
from config.schema import TelemetryConfig
from telemetry.parser import extract_timestamp_delay
from state import SharedState

logger = logging.getLogger(__name__)


class RobotProtocol:

    def __init__(self, state: SharedState, loop: asyncio.AbstractEventLoop,
                 telemetry_cfg: TelemetryConfig = None):
        self.state   = state
        self._loop   = loop
        self._cfg    = telemetry_cfg or TelemetryConfig()
        self._pubs:  dict = {}
        self._subs:  list = []
        self._seq    = 0
        self._cam_bytes  = 0
        self._tele_bytes = 0
        self._bw_ts      = time.time()

    def start(self, session: zenoh.Session) -> None:
        for key in ('nev/gcs/heartbeat', 'nev/gcs/teleop',
                    'nev/gcs/estop', 'nev/gcs/cmd_mode'):
            self._pubs[key] = session.declare_publisher(key, **GCS_QOS[key])

        # Telemetry publisher (state broadcast to client)
        self._pubs['nev/gcs/telemetry'] = session.declare_publisher(
            'nev/gcs/telemetry',
            reliability=zenoh.Reliability.BEST_EFFORT,
            congestion_control=zenoh.CongestionControl.DROP,
            priority=zenoh.Priority.DATA_LOW,
        )

        # Camera passthrough publisher (H.265 NAL relay to client)
        self._pubs['nev/gcs/camera'] = session.declare_publisher(
            'nev/gcs/camera',
            reliability=zenoh.Reliability.BEST_EFFORT,
            congestion_control=zenoh.CongestionControl.DROP,
            priority=zenoh.Priority.INTERACTIVE_HIGH,
        )

        self._subs = [
            session.declare_subscriber('nev/robot/mux',         self._on_mux),
            session.declare_subscriber('nev/robot/twist',       self._on_twist),
            session.declare_subscriber('nev/robot/network',     self._on_network),
            session.declare_subscriber('nev/robot/hunter',      self._on_hunter),
            session.declare_subscriber('nev/robot/estop',       self._on_estop),
            session.declare_subscriber('nev/robot/cpu',         self._on_cpu),
            session.declare_subscriber('nev/robot/mem',         self._on_mem),
            session.declare_subscriber('nev/robot/gpu',         self._on_gpu),
            session.declare_subscriber('nev/robot/disk',        self._on_disk),
            session.declare_subscriber('nev/robot/net',         self._on_net),
            session.declare_subscriber('nev/robot/camera',      self._on_camera),
            session.declare_subscriber('nev/robot/hb_ack',      self._on_hb_ack),
            session.declare_subscriber('nev/robot/video_stats', self._on_video_stats),
        ]
        logger.info('RobotProtocol started')

    def stop(self) -> None:
        for sub in self._subs:
            sub.undeclare()
        for pub in self._pubs.values():
            pub.undeclare()

    def _call(self, fn, *args):
        self._loop.call_soon_threadsafe(fn, *args)

    def _on_mux(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        ts, tele_delay_ms = extract_timestamp_delay(data)
        def _update():
            self.state.update_packet('mux', data)
            self.state.update_remote_enabled(data.get('remote_enabled', False))
            if tele_delay_ms is not None:
                self.state.network.tele_delay_ms = tele_delay_ms
        self._call(_update)

    def _on_twist(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        ts, tele_delay_ms = extract_timestamp_delay(data)
        def _update():
            self.state.update_packet('twist', data)
            if tele_delay_ms is not None:
                self.state.network.tele_delay_ms = tele_delay_ms
        self._call(_update)

    def _on_network(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        self._call(self.state.update_packet, 'network', data)

    def _on_hunter(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        ts, tele_delay_ms = extract_timestamp_delay(data)
        def _update():
            self.state.update_packet('hunter', data)
            if tele_delay_ms is not None:
                self.state.network.tele_delay_ms = tele_delay_ms
        self._call(_update)

    def _on_estop(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        ts, tele_delay_ms = extract_timestamp_delay(data)
        def _update():
            self.state.update_packet('estop', data)
            if tele_delay_ms is not None:
                self.state.network.tele_delay_ms = tele_delay_ms
        self._call(_update)

    def _on_cpu(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        self._call(self.state.update_packet, 'resources', json.loads(raw))

    def _on_mem(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        self._call(self.state.update_packet, 'resources', json.loads(raw))

    def _on_gpu(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        gpus = json.loads(raw)
        def _update():
            for g in gpus:
                try:
                    self.state.update_gpu(g['idx'], {
                        'gpu_usage':     g['gpu_usage'],
                        'gpu_mem_used':  g['gpu_mem_used'],
                        'gpu_mem_total': g['gpu_mem_total'],
                        'gpu_temp':      g['gpu_temp'],
                        'gpu_power':     g['gpu_power'],
                    })
                except (KeyError, TypeError):
                    pass
        self._call(_update)

    def _on_disk(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        def _update():
            for p in data.get('partitions', []):
                try:
                    self.state.update_disk_partition(p['idx'], {
                        'mountpoint':  p['mountpoint'],
                        'total_bytes': p['total_bytes'],
                        'used_bytes':  p['used_bytes'],
                        'percent':     p['percent'],
                        'accessible':  p['accessible'],
                    })
                except (KeyError, TypeError):
                    pass
        self._call(_update)

    def _on_camera(self, sample):
        try:
            raw = bytes(sample.payload)
            if len(raw) <= self._cfg.camera_header_bytes:
                return
            ts, encode_ms = struct.unpack_from('dH', raw, 0)
            self._cam_bytes += len(raw) - self._cfg.camera_header_bytes
            video_delay_ms = (time.time() - ts) * 1000.0
            def _update_delay():
                self.state.network.video_net_delay = video_delay_ms
            self._call(_update_delay)
            # Passthrough: relay entire frame (header + NAL) to client
            self._pubs['nev/gcs/camera'].put(raw)
        except Exception as e:
            logger.warning(f'camera frame parse error: {e}')

    def _on_video_stats(self, sample):
        raw = bytes(sample.payload)
        data = json.loads(raw)
        def _update():
            self.state.network.bw_video_tx  = data.get('bw_mbps', 0.0)
            self.state.network.encode_delay = data.get('encode_ms', 0.0)
        self._call(_update)

    def _on_hb_ack(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        ts = data.get('ts', 0.0)
        if ts > 0:
            rtt_ms = max(0.0, (time.time() - ts) * 1000.0)
            def _update():
                self.state.network.ht_rtt = rtt_ms
            self._call(_update)

    def _on_net(self, sample):
        raw = bytes(sample.payload)
        self._tele_bytes += len(raw)
        data = json.loads(raw)
        def _update():
            try:
                self.state.update_packet('resources', {
                    'net_total_ifaces':  data['net_total_ifaces'],
                    'net_active_ifaces': data['net_active_ifaces'],
                    'net_down_ifaces':   data['net_down_ifaces'],
                })
            except (KeyError, TypeError):
                pass
            for iface in data.get('interfaces', []):
                try:
                    self.state.update_net_interface(iface['idx'], {
                        'name':       iface['name'],
                        'is_up':      iface['is_up'],
                        'speed_mbps': iface['speed_mbps'],
                        'in_bps':     iface['in_bps'],
                        'out_bps':    iface['out_bps'],
                    })
                except (KeyError, TypeError):
                    pass
        self._call(_update)

    def calc_bandwidth(self):
        now = time.time()
        dt  = now - self._bw_ts
        if dt >= self._cfg.bw_calc_interval:
            cam_mbps  = round(self._cam_bytes  * 8 / (dt * 1e6), 3)
            tele_mbps = round(self._tele_bytes * 8 / (dt * 1e6), 3)
            self._cam_bytes  = 0
            self._tele_bytes = 0
            self._bw_ts      = now
            def _update():
                self.state.network.bw_video_rx  = cam_mbps
                self.state.network.bw_telemetry = tele_mbps
            self._call(_update)

    def _next_seq(self) -> int:
        s = self._seq
        self._seq = (self._seq + 1) % self._cfg.seq_max
        return s

    def _zput(self, key: str, data: dict) -> None:
        try:
            self._pubs[key].put(json.dumps(data))
        except Exception as e:
            logger.warning(f'zenoh put [{key}]: {e}')

    def send_heartbeat(self):
        self._zput('nev/gcs/heartbeat', {'ts': time.time(), 'seq': self._next_seq()})

    def send_teleop(self, linear_x: float, angular_z: float):
        self._zput('nev/gcs/teleop', {
            'linear_x':  round(linear_x, 3),
            'angular_z': round(angular_z, 3),
            'seq':       self._next_seq(),
        })

    def send_estop(self, activate: bool):
        self._zput('nev/gcs/estop', {'active': activate, 'seq': self._next_seq()})

    def send_cmd_mode(self, mode: int):
        self._zput('nev/gcs/cmd_mode', {'mode': mode, 'seq': self._next_seq()})

    def send_telemetry(self, state_json: str):
        try:
            self._pubs['nev/gcs/telemetry'].put(state_json)
        except Exception as e:
            logger.warning(f'zenoh put [nev/gcs/telemetry]: {e}')
