from dataclasses import dataclass, field
from typing import List


@dataclass
class ZenohConfig:
    locator: str = 'tcp/127.0.0.1:7447'


@dataclass
class ServerConfig:
    heartbeat_rate: float = 5.0
    state_push_interval: float = 0.5
    station_timeout: float = 2.0
    ping_rate: float = 1.0


@dataclass
class RobotConfig:
    wheelbase: float = 0.650


@dataclass
class TelemetryConfig:
    control_keys: List[str] = field(default_factory=lambda: ['mux', 'twist', 'network', 'hunter', 'estop'])
    disconnect_timeout: float = 3.0
    bw_calc_interval: float = 1.0
    seq_max: int = 65536
    camera_header_bytes: int = 12

    @property
    def control_keys_set(self) -> frozenset:
        return frozenset(self.control_keys)


@dataclass
class AppConfig:
    zenoh: ZenohConfig = field(default_factory=ZenohConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    robot: RobotConfig = field(default_factory=RobotConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    def validate(self) -> None:
        if self.server.heartbeat_rate <= 0:
            raise ValueError(f"heartbeat_rate must be positive, got {self.server.heartbeat_rate}")

        if self.server.state_push_interval <= 0:
            raise ValueError(f"state_push_interval must be positive, got {self.server.state_push_interval}")

        if self.server.station_timeout <= 0:
            raise ValueError(f"station_timeout must be positive, got {self.server.station_timeout}")

        if self.server.ping_rate <= 0:
            raise ValueError(f"ping_rate must be positive, got {self.server.ping_rate}")

        if self.robot.wheelbase <= 0:
            raise ValueError(f"wheelbase must be positive, got {self.robot.wheelbase}")

        if self.telemetry.disconnect_timeout <= 0:
            raise ValueError(f"disconnect_timeout must be positive, got {self.telemetry.disconnect_timeout}")

        if self.telemetry.bw_calc_interval <= 0:
            raise ValueError(f"bw_calc_interval must be positive, got {self.telemetry.bw_calc_interval}")

        if self.telemetry.seq_max <= 0:
            raise ValueError(f"seq_max must be positive, got {self.telemetry.seq_max}")

        if self.telemetry.camera_header_bytes <= 0:
            raise ValueError(f"camera_header_bytes must be positive, got {self.telemetry.camera_header_bytes}")
