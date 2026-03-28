from dataclasses import dataclass, field
from typing import List


@dataclass
class ZenohConfig:
    locator: str = 'tcp/127.0.0.1:7447'


@dataclass
class ServerConfig:
    heartbeat_rate: float = 5.0
    state_push_interval: float = 0.05
    station_timeout: float = 2.0


@dataclass
class RobotConfig:
    wheelbase: float = 0.650


@dataclass
class WebConfig:
    port: int = 8080
    ws_state_queue_size: int = 20
    ws_video_queue_size: int = 5
    rtc_enabled: bool = True
    rtc_stun_servers: List[str] = field(default_factory=lambda: ['stun:stun.l.google.com:19302'])
    video_transport: str = 'webrtc'


@dataclass
class TelemetryConfig:
    control_keys: List[str] = field(default_factory=lambda: ['mux', 'twist', 'network', 'hunter', 'estop'])
    disconnect_timeout: float = 3.0
    bw_calc_interval: float = 1.0
    seq_max: int = 65536
    camera_header_bytes: int = 10

    @property
    def control_keys_set(self) -> frozenset:
        return frozenset(self.control_keys)


@dataclass
class AppConfig:
    zenoh: ZenohConfig = field(default_factory=ZenohConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    robot: RobotConfig = field(default_factory=RobotConfig)
    web: WebConfig = field(default_factory=WebConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    def validate(self) -> None:
        if self.server.heartbeat_rate <= 0:
            raise ValueError(f"heartbeat_rate must be positive, got {self.server.heartbeat_rate}")

        if self.server.state_push_interval <= 0:
            raise ValueError(f"state_push_interval must be positive, got {self.server.state_push_interval}")

        if self.server.station_timeout <= 0:
            raise ValueError(f"station_timeout must be positive, got {self.server.station_timeout}")

        if self.robot.wheelbase <= 0:
            raise ValueError(f"wheelbase must be positive, got {self.robot.wheelbase}")

        if not (1 <= self.web.port <= 65535):
            raise ValueError(f"port must be 1-65535, got {self.web.port}")

        if self.web.ws_state_queue_size <= 0:
            raise ValueError(f"ws_state_queue_size must be positive, got {self.web.ws_state_queue_size}")

        if self.web.ws_video_queue_size <= 0:
            raise ValueError(f"ws_video_queue_size must be positive, got {self.web.ws_video_queue_size}")

        if self.web.video_transport not in ('webrtc', 'websocket'):
            raise ValueError(f"video_transport must be 'webrtc' or 'websocket', got {self.web.video_transport!r}")

        if self.telemetry.disconnect_timeout <= 0:
            raise ValueError(f"disconnect_timeout must be positive, got {self.telemetry.disconnect_timeout}")

        if self.telemetry.bw_calc_interval <= 0:
            raise ValueError(f"bw_calc_interval must be positive, got {self.telemetry.bw_calc_interval}")

        if self.telemetry.seq_max <= 0:
            raise ValueError(f"seq_max must be positive, got {self.telemetry.seq_max}")

        if self.telemetry.camera_header_bytes <= 0:
            raise ValueError(f"camera_header_bytes must be positive, got {self.telemetry.camera_header_bytes}")
