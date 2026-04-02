import zenoh


GCS_QOS = {
    'nev/gcs/heartbeat': dict(
        reliability=zenoh.Reliability.BEST_EFFORT,
        congestion_control=zenoh.CongestionControl.DROP,
        priority=zenoh.Priority.DATA_LOW
    ),
    'nev/gcs/teleop': dict(
        reliability=zenoh.Reliability.BEST_EFFORT,
        congestion_control=zenoh.CongestionControl.DROP,
        priority=zenoh.Priority.INTERACTIVE_HIGH
    ),
    'nev/gcs/estop': dict(
        reliability=zenoh.Reliability.RELIABLE,
        congestion_control=zenoh.CongestionControl.BLOCK,
        priority=zenoh.Priority.REAL_TIME
    ),
    'nev/gcs/cmd_mode': dict(
        reliability=zenoh.Reliability.RELIABLE,
        congestion_control=zenoh.CongestionControl.BLOCK,
        priority=zenoh.Priority.INTERACTIVE_HIGH
    ),
    'nev/gcs/ping': dict(
        reliability=zenoh.Reliability.BEST_EFFORT,
        congestion_control=zenoh.CongestionControl.DROP,
        priority=zenoh.Priority.DATA_LOW,
    ),
    'nev/gcs/station_pong': dict(
        reliability=zenoh.Reliability.BEST_EFFORT,
        congestion_control=zenoh.CongestionControl.DROP,
        priority=zenoh.Priority.DATA_LOW,
    ),
}
