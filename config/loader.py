from pathlib import Path
from typing import Dict, Any
import yaml

from .schema import AppConfig, ZenohConfig, ServerConfig, RobotConfig, TelemetryConfig


def _cast(value, expected_type, field_name: str):
    if not isinstance(value, expected_type):
        try:
            return expected_type(value)
        except (ValueError, TypeError):
            raise ValueError(f"config field '{field_name}' expected {expected_type.__name__}, got {type(value).__name__}: {value!r}")
    return value


def load_config(path: str, overrides: Dict[str, Any] = None) -> AppConfig:
    cfg_dict = {}
    p = Path(path)

    if p.exists():
        with open(p, 'r') as f:
            cfg_dict = yaml.safe_load(f) or {}

    if overrides:
        cfg_dict.update({k: v for k, v in overrides.items() if v is not None})

    zenoh_cfg = ZenohConfig(
        locator=str(cfg_dict.get('zenoh_locator', 'tcp/127.0.0.1:7447'))
    )

    server_cfg = ServerConfig(
        heartbeat_rate=_cast(cfg_dict.get('heartbeat_rate', 5.0), float, 'heartbeat_rate'),
        state_push_interval=_cast(cfg_dict.get('state_push_interval', 0.5), float, 'state_push_interval'),
        station_timeout=_cast(cfg_dict.get('station_timeout', 2.0), float, 'station_timeout'),
    )

    robot_cfg = RobotConfig(
        wheelbase=_cast(cfg_dict.get('wheelbase', 0.650), float, 'wheelbase')
    )

    raw_keys = cfg_dict.get('control_keys', ['mux', 'twist', 'network', 'hunter', 'estop'])
    if not isinstance(raw_keys, list) or not all(isinstance(k, str) for k in raw_keys):
        raise ValueError(f"config field 'control_keys' must be a list of strings, got {raw_keys!r}")

    telemetry_cfg = TelemetryConfig(
        control_keys=raw_keys,
        disconnect_timeout=_cast(cfg_dict.get('disconnect_timeout', 3.0), float, 'disconnect_timeout'),
        bw_calc_interval=_cast(cfg_dict.get('bw_calc_interval', 1.0), float, 'bw_calc_interval'),
        seq_max=_cast(cfg_dict.get('seq_max', 65536), int, 'seq_max'),
        camera_header_bytes=_cast(cfg_dict.get('camera_header_bytes', 10), int, 'camera_header_bytes'),
    )

    config = AppConfig(
        zenoh=zenoh_cfg,
        server=server_cfg,
        robot=robot_cfg,
        telemetry=telemetry_cfg,
    )

    config.validate()

    return config
