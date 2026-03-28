import asyncio
import logging
import struct
import time
from typing import Dict, List, Optional

from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, RTCIceCandidate

logger = logging.getLogger(__name__)

BACKPRESSURE_LIMIT = 256 * 1024  # 256 KB


class RTCRelay:

    def __init__(self, stun_servers: List[str] = None):
        self._stun_servers = stun_servers or ['stun:stun.l.google.com:19302']
        self._peers: Dict[int, RTCPeerConnection] = {}
        self._channels: Dict[int, object] = {}

    def _make_rtc_config(self) -> RTCConfiguration:
        ice_servers = [RTCIceServer(urls=s) for s in self._stun_servers]
        return RTCConfiguration(iceServers=ice_servers)

    async def create_offer(self, peer_id: int) -> dict:
        await self.remove_peer(peer_id)

        pc = RTCPeerConnection(self._make_rtc_config())
        self._peers[peer_id] = pc

        channel = pc.createDataChannel(
            'video',
            ordered=False,
            maxRetransmits=0,
        )
        self._channels[peer_id] = channel

        @channel.on('open')
        def on_open():
            logger.info(f'DataChannel opened for peer {peer_id}')

        @channel.on('close')
        def on_close():
            logger.info(f'DataChannel closed for peer {peer_id}')
            asyncio.ensure_future(self.remove_peer(peer_id))

        @pc.on('connectionstatechange')
        async def on_state_change():
            if pc.connectionState in ('failed', 'closed'):
                await self.remove_peer(peer_id)

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        return {
            'sdp': pc.localDescription.sdp,
            'sdp_type': pc.localDescription.type,
        }

    async def handle_answer(self, peer_id: int, msg: dict) -> None:
        pc = self._peers.get(peer_id)
        if not pc:
            return
        answer = RTCSessionDescription(sdp=msg['sdp'], type=msg['sdp_type'])
        await pc.setRemoteDescription(answer)

    async def handle_ice_candidate(self, peer_id: int, candidate_data: Optional[dict]) -> None:
        pc = self._peers.get(peer_id)
        if not pc or not candidate_data:
            return
        try:
            candidate = RTCIceCandidate(
                sdpMid=candidate_data.get('sdpMid'),
                sdpMLineIndex=candidate_data.get('sdpMLineIndex'),
                candidate=candidate_data.get('candidate', ''),
            )
            await pc.addIceCandidate(candidate)
        except Exception as e:
            logger.warning(f'ICE candidate error for peer {peer_id}: {e}')

    def broadcast_nal(self, nal: bytes) -> None:
        if not nal or not self._channels:
            return
        ts_header = struct.pack('!I', int(time.time() * 1000) & 0xFFFFFFFF)
        payload = ts_header + nal

        dead = []
        for peer_id, channel in list(self._channels.items()):
            try:
                if channel.readyState != 'open':
                    continue
                if hasattr(channel, 'bufferedAmount') and channel.bufferedAmount > BACKPRESSURE_LIMIT:
                    continue
                channel.send(payload)
            except Exception as e:
                logger.debug(f'DataChannel send error for peer {peer_id}: {e}')
                dead.append(peer_id)

        for peer_id in dead:
            asyncio.ensure_future(self.remove_peer(peer_id))

    async def remove_peer(self, peer_id: int) -> None:
        self._channels.pop(peer_id, None)
        pc = self._peers.pop(peer_id, None)
        if pc:
            await pc.close()

    async def cleanup(self) -> None:
        for peer_id in list(self._peers.keys()):
            await self.remove_peer(peer_id)
