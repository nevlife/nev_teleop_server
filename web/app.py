import asyncio
import json
import logging
import os
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_state = None
_robot_proto = None
_latest_json: str = '{}'
_json_lock = threading.Lock()
_latest_video_frame: bytes = b''
_video_lock = threading.Lock()


class ModeCmd(BaseModel):
    mode: int


class EstopCmd(BaseModel):
    active: bool


def create_app(state, robot_proto):
    global _state, _robot_proto
    _state = state
    _robot_proto = robot_proto

    app = FastAPI(title='NEV Teleop Dashboard')

    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    app.mount('/static', StaticFiles(directory=static_dir), name='static')

    @app.get('/')
    async def index():
        return FileResponse(os.path.join(static_dir, 'index.html'))

    @app.get('/video')
    async def video_page():
        return FileResponse(os.path.join(static_dir, 'video.html'))

    @app.websocket('/ws/telemetry')
    async def ws_telemetry(ws: WebSocket):
        await ws.accept()
        logger.info('WebSocket client connected')
        last_sent = ''
        try:
            while True:
                with _json_lock:
                    current = _latest_json
                if current != last_sent:
                    await ws.send_text(current)
                    last_sent = current
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            logger.info('WebSocket client disconnected')

    @app.websocket('/ws/video')
    async def ws_video(ws: WebSocket):
        await ws.accept()
        logger.info('Video WebSocket client connected')
        last_id = 0
        try:
            while True:
                with _video_lock:
                    frame = _latest_video_frame
                    fid = id(frame)
                if fid != last_id and len(frame) > 0:
                    await ws.send_bytes(frame)
                    last_id = fid
                await asyncio.sleep(0.005)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            logger.info('Video WebSocket client disconnected')

    @app.post('/api/cmd/mode')
    async def cmd_mode(cmd: ModeCmd):
        _robot_proto.send_cmd_mode(cmd.mode)
        logger.info(f'Web cmd_mode → {cmd.mode}')
        return JSONResponse({'ok': True, 'mode': cmd.mode})

    @app.post('/api/cmd/estop')
    async def cmd_estop(cmd: EstopCmd):
        _robot_proto.send_estop(cmd.active)
        logger.info(f'Web estop → {cmd.active}')
        return JSONResponse({'ok': True, 'active': cmd.active})

    @app.get('/api/status')
    async def api_status():
        return JSONResponse({
            'station_connected': _state.station_connected,
            'rtt_server_bot_ms': _state.network.rtt_server_bot_ms,
        })

    return app


def update_telemetry(state_json: str):
    global _latest_json
    with _json_lock:
        _latest_json = state_json


def update_video_frame(nal_bytes: bytes):
    global _latest_video_frame
    with _video_lock:
        _latest_video_frame = nal_bytes


def start_web(state, robot_proto, host='0.0.0.0', port=8000):
    import uvicorn
    app = create_app(state, robot_proto)

    def _run():
        uvicorn.run(app, host=host, port=port, log_level='warning')

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.info(f'Web dashboard started → http://{host}:{port}')
    return t
