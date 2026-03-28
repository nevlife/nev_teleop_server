import os
import tempfile

from zenoh_utils.session_setup import sync_zenohd_config


class TestSyncZenohdConfig:
    def test_generates_config_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json5', delete=False) as f:
            path = f.name
        try:
            sync_zenohd_config('tcp/0.0.0.0:7447', path)
            content = open(path).read()
            assert '"tcp/0.0.0.0:7447"' in content
            assert 'enabled: false' in content
        finally:
            os.unlink(path)

    def test_extracts_port(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json5', delete=False) as f:
            path = f.name
        try:
            sync_zenohd_config('tcp/10.0.0.1:9999', path)
            content = open(path).read()
            assert '"tcp/0.0.0.0:9999"' in content
        finally:
            os.unlink(path)

    def test_invalid_locator_no_crash(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json5', delete=False) as f:
            path = f.name
        try:
            sync_zenohd_config('invalid_locator', path)
        finally:
            os.unlink(path)
