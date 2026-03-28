#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import time

import uvicorn
import zenoh

from config import load_config
from zenoh_utils import sync_zenohd_config
from state import SharedState
from robot_bridge import RobotProtocol
from station_bridge import StationBridge
from web.server import create_app
from web.rtc_relay import RTCRelay

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
            state._broadcast_sync()
            last_push = now

        await asyncio.sleep(0.01)


async def run(cfg):
    locator = cfg.zenoh.locator

    if locator:
        sync_zenohd_config(locator)

    state = SharedState(cfg.telemetry)
    loop  = asyncio.get_running_loop()

    rtc_relay = None
    if cfg.web.rtc_enabled:
        rtc_relay = RTCRelay(stun_servers=cfg.web.rtc_stun_servers)
        logger.info('WebRTC DataChannel relay enabled')

    zconf = zenoh.Config()
    if locator:
        zconf.insert_json5('connect/endpoints', json.dumps([locator]))
    session = zenoh.open(zconf)
    logger.info(f'Zenoh session opened → {locator or "auto-discovery"}')

    robot_proto = RobotProtocol(state, loop, cfg.telemetry, rtc_relay=rtc_relay)
    robot_proto.start(session)

    station_bridge = StationBridge(state, loop, robot_proto, cfg.robot)
    station_bridge.start(session)

    app = create_app(state, robot_proto, cfg.web, rtc_relay=rtc_relay)
    uv_cfg = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=cfg.web.port,
        log_level='warning',
        loop='none',
    )
    server = uvicorn.Server(uv_cfg)
    logger.info(f'Web  http://0.0.0.0:{cfg.web.port}')

    try:
        await asyncio.gather(
            run_send_loop(state, robot_proto, cfg),
            server.serve(),
        )
    finally:
        if rtc_relay:
            await rtc_relay.cleanup()
        station_bridge.stop()
        robot_proto.stop()
        session.close()
        logger.info('Shutdown complete')


def main():
    parser = argparse.ArgumentParser(description='NEV Teleop Server')
    parser.add_argument('--config',       default='config.yaml')
    parser.add_argument('--zenoh-locator', default=None)
    parser.add_argument('--web-port',      type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config, {
        'zenoh_locator': args.zenoh_locator,
        'web_port':      args.web_port,
    })

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        logger.info('Stopped by user')


if __name__ == '__main__':
    main()
