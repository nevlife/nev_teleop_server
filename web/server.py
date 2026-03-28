import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .video_relay import video_relay

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / 'static'


class CmdModeReq(BaseModel):
    mode: int

class EStopReq(BaseModel):
    active: bool


def create_app(state, proto, web_cfg=None, rtc_relay=None):
    app = FastAPI(title='NEV Teleop Server', docs_url=None, redoc_url=None)

    _ws_state_queue_size = web_cfg.ws_state_queue_size if web_cfg else 20
    _ws_video_queue_size = web_cfg.ws_video_queue_size if web_cfg else 5

    app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')

    @app.get('/', response_class=HTMLResponse)
    async def index():
        return (STATIC_DIR / 'index.html').read_text()

    @app.get('/api/state')
    async def get_state():
        return json.loads(state.to_json())

    @app.post('/api/cmd_mode')
    async def set_cmd_mode(req: CmdModeReq):
        if req.mode not in (-1, 0, 1, 2):
            return {'ok': False, 'error': f'invalid mode: {req.mode}'}
        state.control.mode = req.mode
        proto.send_cmd_mode(req.mode)
        logger.info(f'Mode → {req.mode} (browser)')
        return {'ok': True, 'mode': req.mode, 'station_connected': state.station_connected}

    @app.post('/api/estop')
    async def set_estop(req: EStopReq):
        state.control.estop = req.active
        proto.send_estop(req.active)
        logger.info(f'E-stop → {req.active} (browser)')
        return {'ok': True, 'active': req.active}

    @app.websocket('/ws')
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_ws_state_queue_size)
        state.add_subscriber(queue)
        logger.info(f'Browser WebSocket connected: {ws.client}')

        async def _send_loop():
            await ws.send_text(state.to_json())
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    await ws.send_text(data)
                except asyncio.TimeoutError:
                    await ws.send_text(state.to_json())

        async def _recv_loop():
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                msg_type = msg.get('type')
                if msg_type == 'video_metrics':
                    state.network.browser_decode_ms = float(msg.get('decode_ms', 0.0))
                elif msg_type == 'rtc_request' and rtc_relay:
                    offer = await rtc_relay.create_offer(id(ws))
                    await ws.send_text(json.dumps({'type': 'rtc_offer', **offer}))
                elif msg_type == 'rtc_answer' and rtc_relay:
                    await rtc_relay.handle_answer(id(ws), msg)
                elif msg_type == 'rtc_ice' and rtc_relay:
                    await rtc_relay.handle_ice_candidate(id(ws), msg.get('candidate'))

        try:
            await asyncio.gather(_send_loop(), _recv_loop())
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            if rtc_relay:
                await rtc_relay.remove_peer(id(ws))
            state.remove_subscriber(queue)
            logger.info(f'Browser WebSocket disconnected: {ws.client}')

    @app.websocket('/ws/video')
    async def ws_video(ws: WebSocket):
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=_ws_video_queue_size)
        video_relay.add_subscriber(queue)
        logger.info(f'Video WebSocket connected: {ws.client}')

        try:
            while True:
                try:
                    nal = await asyncio.wait_for(queue.get(), timeout=10.0)
                    await ws.send_bytes(nal)
                except asyncio.TimeoutError:
                    continue
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            video_relay.remove_subscriber(queue)
            logger.info(f'Video WebSocket disconnected: {ws.client}')

    return app
