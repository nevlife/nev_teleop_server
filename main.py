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
    format='%(asctime)s  %(levelname)-7s  %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('main')


async def run_send_loop(state: SharedState, proto: RobotProtocol, cfg):
    hb_interval        = 1.0 / cfg.server.heartbeat_rate
    push_interval      = cfg.server.state_push_interval
    station_timeout    = cfg.server.station_timeout
    disconnect_timeout = cfg.telemetry.disconnect_timeout

    last_hb   = 0.0
    last_push = 0.0
    _veh_disconnected = False

    while True:
        now = time.monotonic()

        if state.last_robot_recv > 0:
            age = now - state.last_robot_recv
            if age > disconnect_timeout and not _veh_disconnected:
                _veh_disconnected = True
                logger.warning('Robot disconnected')
            elif age < 1.0 and _veh_disconnected:
                _veh_disconnected = False
                logger.info('Robot reconnected')

        if state.station_connected and state.station_last_recv > 0:
            if now - state.station_last_recv > station_timeout:
                logger.warning('Station heartbeat timeout — marking disconnected')
                state.update_station_connected(False)

        proto.calc_bandwidth()

        if now - last_hb >= hb_interval:
            proto.send_heartbeat()
            last_hb = now

        if now - last_push >= push_interval:
            state._validate()
            proto.send_telemetry(state.to_json())
            last_push = now

        next_hb   = last_hb   + hb_interval   - now
        next_push = last_push + push_interval  - now
        sleep_for = max(0.001, min(next_hb, next_push))
        await asyncio.sleep(sleep_for)


async def run(cfg):
    locator = cfg.zenoh.locator

    if locator:
        sync_zenohd_config(locator)

    state = SharedState(cfg.telemetry)
    loop  = asyncio.get_running_loop()

    zconf = zenoh.Config()
    if locator:
        zconf.insert_json5('connect/endpoints', json.dumps([locator]))
    session = zenoh.open(zconf)
    logger.info(f'Zenoh session opened → {locator or "auto-discovery"}')

    robot_proto = RobotProtocol(state, loop, cfg.telemetry)
    robot_proto.start(session)

    station_bridge = StationBridge(state, loop, robot_proto, cfg.robot)
    station_bridge.start(session)

    logger.info('Server running (Zenoh relay only)')

    try:
        await run_send_loop(state, robot_proto, cfg)
    finally:
        station_bridge.stop()
        robot_proto.stop()
        session.close()
        logger.info('Shutdown complete')


def main():
    parser = argparse.ArgumentParser(description='NEV Teleop Server')
    parser.add_argument('--config',       default='config.yaml')
    parser.add_argument('--zenoh-locator', default=None)
    args = parser.parse_args()

    cfg = load_config(args.config, {
        'zenoh_locator': args.zenoh_locator,
    })

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        logger.info('Stopped by user')


if __name__ == '__main__':
    main()
