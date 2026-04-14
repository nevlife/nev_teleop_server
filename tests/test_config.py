import os
import tempfile
import pytest
import yaml

from config.schema import (
    AppConfig,
    ZenohConfig,
    ServerConfig,
    TelemetryConfig,
)
from config.loader import load_config


class TestSchemaDefaults:
    def test_zenoh_default(self):
        c = ZenohConfig()
        assert c.locator == "tcp/127.0.0.1:7447"

    def test_server_defaults(self):
        c = ServerConfig()
        assert c.telemetry_rate == 2.0
        assert c.station_timeout == 2.0

    def test_telemetry_defaults(self):
        c = TelemetryConfig()
        assert c.disconnect_timeout == 3.0
        assert c.bw_calc_interval == 1.0
        assert c.seq_max == 65536
        assert c.camera_header_bytes == 12
        assert set(c.control_keys) == {"mux", "twist", "network", "hunter", "estop"}

    def test_telemetry_control_keys_set(self):
        c = TelemetryConfig(control_keys=["mux", "twist"])
        assert c.control_keys_set == frozenset({"mux", "twist"})


class TestAppConfigValidation:
    def test_valid_config_passes(self):
        cfg = AppConfig()
        cfg.validate()

    def test_zero_telemetry_rate(self):
        cfg = AppConfig(server=ServerConfig(telemetry_rate=0))
        with pytest.raises(ValueError, match="telemetry_rate"):
            cfg.validate()

    def test_negative_station_timeout(self):
        cfg = AppConfig(server=ServerConfig(station_timeout=-1))
        with pytest.raises(ValueError, match="station_timeout"):
            cfg.validate()

    def test_negative_disconnect_timeout(self):
        cfg = AppConfig(telemetry=TelemetryConfig(disconnect_timeout=-1))
        with pytest.raises(ValueError, match="disconnect_timeout"):
            cfg.validate()

    def test_zero_bw_calc_interval(self):
        cfg = AppConfig(telemetry=TelemetryConfig(bw_calc_interval=0))
        with pytest.raises(ValueError, match="bw_calc_interval"):
            cfg.validate()

    def test_negative_seq_max(self):
        cfg = AppConfig(telemetry=TelemetryConfig(seq_max=-1))
        with pytest.raises(ValueError, match="seq_max"):
            cfg.validate()

    def test_zero_camera_header_bytes(self):
        cfg = AppConfig(telemetry=TelemetryConfig(camera_header_bytes=0))
        with pytest.raises(ValueError, match="camera_header_bytes"):
            cfg.validate()


class TestLoader:
    def test_load_from_yaml(self):
        data = {
            "zenoh_locator": "tcp/10.0.0.1:7447",
            "disconnect_timeout": 5.0,
            "control_keys": ["mux", "estop"],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            cfg = load_config(f.name)
        os.unlink(f.name)

        assert cfg.zenoh.locator == "tcp/10.0.0.1:7447"
        assert cfg.telemetry.disconnect_timeout == 5.0
        assert cfg.telemetry.control_keys == ["mux", "estop"]

    def test_load_nonexistent_file_uses_defaults(self):
        cfg = load_config("/tmp/does_not_exist_12345.yaml")
        assert cfg.zenoh.locator == "tcp/127.0.0.1:7447"
