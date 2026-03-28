import time
from typing import Dict, Tuple, Optional


def extract_timestamp_delay(data: Dict) -> Tuple[Optional[float], Optional[float]]:
    ts = data.pop('ts', None)
    delay_ms = (time.time() - ts) * 1000.0 if ts else None
    return ts, delay_ms
