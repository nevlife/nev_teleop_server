import asyncio
import logging

logger = logging.getLogger(__name__)


class VideoRelay:

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def add_subscriber(self, q: asyncio.Queue) -> None:
        self._subscribers.append(q)

    def remove_subscriber(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def broadcast_nal(self, nal: bytes) -> None:
        if not nal or not self._subscribers:
            return
        dead = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(nal)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(nal)
                except Exception:
                    dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            self.remove_subscriber(q)

    async def cleanup(self) -> None:
        self._subscribers.clear()


video_relay = VideoRelay()
