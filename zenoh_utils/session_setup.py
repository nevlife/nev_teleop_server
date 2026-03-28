import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def sync_zenohd_config(locator: str, zenohd_path: str = 'zenohd.json5') -> None:
    m = re.search(r':(\d+)$', locator)
    if not m:
        logger.warning(f'Failed to parse zenoh_locator port: {locator!r} — zenohd.json5 not updated')
        return
    
    port = m.group(1)
    
    config_content = (
        '{\n'
        '  listen: {\n'
        f'    endpoints: ["tcp/0.0.0.0:{port}"],\n'
        '  },\n'
        '  scouting: {\n'
        '    multicast: {\n'
        '      enabled: false,\n'
        '    },\n'
        '  },\n'
        '}\n'
    )
    
    Path(zenohd_path).write_text(config_content)
    logger.info(f'zenohd.json5 → port {port}')
