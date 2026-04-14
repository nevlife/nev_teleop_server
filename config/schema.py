from dataclasses import dataclass, field
from typing import List


@dataclass
class ZenohConfig:
    port: int = 7447


@dataclass
class ServerConfig:
    telemetry_rate: float = 2.0
    station_timeout: float = 2.0
    ping_rate: float = 1.0


@dataclass
class TelemetryConfig:
    control_keys: List[str] = field(default_factory=lambda: ["mux", "twist", "network", "estop"])
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
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)

    def validate(self) -> None:
        if self.server.telemetry_rate <= 0:
            raise ValueError(f"telemetry_rate must be positive, got {self.server.telemetry_rate}")

        if self.server.station_timeout <= 0:
            raise ValueError(
                f"station_timeout must be positive, got {self.server.station_timeout}"
            )

        if self.server.ping_rate <= 0:
            raise ValueError(f"ping_rate must be positive, got {self.server.ping_rate}")

        if self.telemetry.disconnect_timeout <= 0:
            raise ValueError(
                f"disconnect_timeout must be positive, got {self.telemetry.disconnect_timeout}"
            )

        if self.telemetry.bw_calc_interval <= 0:
            raise ValueError(
                f"bw_calc_interval must be positive, got {self.telemetry.bw_calc_interval}"
            )

        if self.telemetry.seq_max <= 0:
            raise ValueError(f"seq_max must be positive, got {self.telemetry.seq_max}")

        if self.telemetry.camera_header_bytes <= 0:
            raise ValueError(
                f"camera_header_bytes must be positive, got {self.telemetry.camera_header_bytes}"
            )
