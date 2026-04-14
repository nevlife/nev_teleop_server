#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import time

import zenoh

from config import load_config
from zenoh_utils import sync_zenohd_config
from state import SharedState
from robot_bridge import RobotProtocol
from station_bridge import StationBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("robot_bridge").setLevel(logging.DEBUG)
logger = logging.getLogger("main")


async def run_send_loop(state: SharedState, proto: RobotProtocol, cfg):
    push_interval = 1.0 / cfg.server.telemetry_rate
    station_timeout = cfg.server.station_timeout
    disconnect_timeout = cfg.telemetry.disconnect_timeout
    ping_interval = 1.0 / cfg.server.ping_rate

    last_push = 0.0
    last_ping = 0.0
    _veh_disconnected: set[str] = set()

    while True:
        now = time.monotonic()

        for vid, veh in list(state.vehicles.items()):
            if veh.last_robot_recv > 0:
                age = now - veh.last_robot_recv
                if age > disconnect_timeout and vid not in _veh_disconnected:
                    _veh_disconnected.add(vid)
                    logger.warning(f"[{vid}] Robot disconnected")
                elif age < 1.0 and vid in _veh_disconnected:
                    _veh_disconnected.discard(vid)
                    logger.info(f"[{vid}] Robot reconnected")

        if state.station_connected and state.station_last_recv > 0:
            if now - state.station_last_recv > station_timeout:
                logger.warning("Station heartbeat timeout — marking disconnected")
                state.update_station_connected(False)

        proto.calc_bandwidth()
        proto.check_rtt_stale()

        if now - last_ping >= ping_interval:
            for vid in list(state.vehicles.keys()):
                proto.send_server_ping(vid)
            last_ping = now

        if now - last_push >= push_interval:
            state.validate()
            state_json = state.to_json()
            proto.send_telemetry(state_json)

            for veh in state.vehicles.values():
                veh.network.relay_max_ms = 0.0
            last_push = now

        next_push = last_push + push_interval - now
        next_ping = last_ping + ping_interval - now
        sleep_for = max(0.001, min(next_push, next_ping))
        await asyncio.sleep(sleep_for)


async def run(cfg):
    port = cfg.zenoh.port

    sync_zenohd_config(port)

    state = SharedState(cfg.telemetry)
    loop = asyncio.get_running_loop()

    listen_eps = [f"tcp/0.0.0.0:{port}", f"udp/0.0.0.0:{port}"]
    zconf = zenoh.Config()
    zconf.insert_json5("mode", '"router"')
    zconf.insert_json5("listen/endpoints", json.dumps(listen_eps))
    session = zenoh.open(zconf)
    logger.info(f"Zenoh router opened -> listening on {listen_eps}")

    robot_proto = RobotProtocol(state, loop, cfg.telemetry)
    robot_proto.start(session)

    station_bridge = StationBridge(state, loop, robot_proto)
    station_bridge.start(session)

    logger.info("Server running (Zenoh relay)")

    try:
        await run_send_loop(state, robot_proto, cfg)
    finally:
        station_bridge.stop()
        robot_proto.stop()
        session.close()
        logger.info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="NEV Teleop Server")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--zenoh-port", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(
        args.config,
        {
            "zenoh_port": args.zenoh_port,
        },
    )

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        logger.info("Stopped by user")


if __name__ == "__main__":
    main()
