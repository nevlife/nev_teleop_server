import time
from typing import Dict, Tuple, Optional


def extract_timestamp_delay(data) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(data, dict):
        return None, None
    ts = data.get("ts", None)
    delay_ms = (time.time() - ts) * 1000.0 if ts else None
    return ts, delay_ms
