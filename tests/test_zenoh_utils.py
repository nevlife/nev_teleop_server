import os
import tempfile
from pathlib import Path

from zenoh_utils.session_setup import sync_zenohd_config


class TestSyncZenohdConfig:
    def test_generates_config_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_zenohd_config("tcp/0.0.0.0:7447", Path(tmpdir))
            content = (Path(tmpdir) / "zenohd.json5").read_text()
            assert '"tcp/0.0.0.0:7447"' in content
            assert "enabled: false" in content

    def test_extracts_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_zenohd_config("tcp/10.0.0.1:9999", Path(tmpdir))
            content = (Path(tmpdir) / "zenohd.json5").read_text()
            assert '"tcp/0.0.0.0:9999"' in content

    def test_invalid_locator_no_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_zenohd_config("invalid_locator", Path(tmpdir))
