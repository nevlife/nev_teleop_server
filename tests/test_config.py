import os
import tempfile
import pytest
import yaml

from config.schema import AppConfig, ZenohConfig, ServerConfig, RobotConfig, WebConfig, TelemetryConfig
from config.loader import load_config


class TestSchemaDefaults:
    def test_zenoh_default(self):
        c = ZenohConfig()
        assert c.locator == 'tcp/127.0.0.1:7447'

    def test_server_defaults(self):
        c = ServerConfig()
        assert c.heartbeat_rate == 5.0
        assert c.state_push_interval == 0.5
        assert c.station_timeout == 2.0

    def test_robot_default(self):
        c = RobotConfig()
        assert c.wheelbase == 0.650

    def test_web_default(self):
        c = WebConfig()
        assert c.port == 8080

    def test_telemetry_defaults(self):
        c = TelemetryConfig()
        assert c.disconnect_timeout == 3.0
        assert c.bw_calc_interval == 1.0
        assert c.seq_max == 65536
        assert c.camera_header_bytes == 12
        assert set(c.control_keys) == {'mux', 'twist', 'network', 'hunter', 'estop'}

    def test_telemetry_control_keys_set(self):
        c = TelemetryConfig(control_keys=['mux', 'twist'])
        assert c.control_keys_set == frozenset({'mux', 'twist'})


class TestAppConfigValidation:
    def test_valid_config_passes(self):
        cfg = AppConfig()
        cfg.validate()

    def test_negative_heartbeat_rate(self):
        cfg = AppConfig(server=ServerConfig(heartbeat_rate=-1))
        with pytest.raises(ValueError, match='heartbeat_rate'):
            cfg.validate()

    def test_zero_state_push_interval(self):
        cfg = AppConfig(server=ServerConfig(state_push_interval=0))
        with pytest.raises(ValueError, match='state_push_interval'):
            cfg.validate()

    def test_negative_station_timeout(self):
        cfg = AppConfig(server=ServerConfig(station_timeout=-1))
        with pytest.raises(ValueError, match='station_timeout'):
            cfg.validate()

    def test_zero_wheelbase(self):
        cfg = AppConfig(robot=RobotConfig(wheelbase=0))
        with pytest.raises(ValueError, match='wheelbase'):
            cfg.validate()

    def test_invalid_port(self):
        cfg = AppConfig(web=WebConfig(port=0))
        with pytest.raises(ValueError, match='port'):
            cfg.validate()

    def test_port_too_high(self):
        cfg = AppConfig(web=WebConfig(port=70000))
        with pytest.raises(ValueError, match='port'):
            cfg.validate()

    def test_negative_disconnect_timeout(self):
        cfg = AppConfig(telemetry=TelemetryConfig(disconnect_timeout=-1))
        with pytest.raises(ValueError, match='disconnect_timeout'):
            cfg.validate()

    def test_zero_bw_calc_interval(self):
        cfg = AppConfig(telemetry=TelemetryConfig(bw_calc_interval=0))
        with pytest.raises(ValueError, match='bw_calc_interval'):
            cfg.validate()

    def test_negative_seq_max(self):
        cfg = AppConfig(telemetry=TelemetryConfig(seq_max=-1))
        with pytest.raises(ValueError, match='seq_max'):
            cfg.validate()

    def test_zero_camera_header_bytes(self):
        cfg = AppConfig(telemetry=TelemetryConfig(camera_header_bytes=0))
        with pytest.raises(ValueError, match='camera_header_bytes'):
            cfg.validate()


class TestLoader:
    def test_load_from_yaml(self):
        data = {
            'zenoh_locator': 'tcp/10.0.0.1:7447',
            'web_port': 9090,
            'heartbeat_rate': 10.0,
            'wheelbase': 1.2,
            'disconnect_timeout': 5.0,
            'control_keys': ['mux', 'estop'],
        }
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            cfg = load_config(f.name)
        os.unlink(f.name)

        assert cfg.zenoh.locator == 'tcp/10.0.0.1:7447'
        assert cfg.web.port == 9090
        assert cfg.server.heartbeat_rate == 10.0
        assert cfg.robot.wheelbase == 1.2
        assert cfg.telemetry.disconnect_timeout == 5.0
        assert cfg.telemetry.control_keys == ['mux', 'estop']

    def test_load_nonexistent_file_uses_defaults(self):
        cfg = load_config('/tmp/does_not_exist_12345.yaml')
        assert cfg.zenoh.locator == 'tcp/127.0.0.1:7447'
        assert cfg.web.port == 8080

    def test_overrides(self):
        cfg = load_config('/tmp/does_not_exist_12345.yaml', {'web_port': 3000})
        assert cfg.web.port == 3000

    def test_none_overrides_ignored(self):
        cfg = load_config('/tmp/does_not_exist_12345.yaml', {'web_port': None})
        assert cfg.web.port == 8080
