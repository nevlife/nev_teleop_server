/* H.264 video stream via WebSocket + jmuxer.
   If codec is h265, show message to use native viewer instead. */
let videoWs = null;
let jmuxer = null;
let videoFrameCount = 0;
let videoByteCount = 0;
let videoStatsTime = performance.now();
let currentCodec = '';
let videoActive = false;

function initVideo() {
    connectVideoWs();
}

function startJmuxer() {
    if (jmuxer) return;
    jmuxer = new JMuxer({
        node: 'video-player',
        mode: 'video',
        flushingTime: 0,
        fps: 30,
        debug: false,
    });
    videoActive = true;
}

function stopJmuxer() {
    if (jmuxer) {
        jmuxer.destroy();
        jmuxer = null;
    }
    videoActive = false;
}

function onCodecUpdate(codec) {
    if (codec === currentCodec) return;
    currentCodec = codec;

    const noVideo = document.getElementById('no-video');
    const player = document.getElementById('video-player');

    if (codec === 'h264') {
        noVideo.style.display = 'none';
        player.style.display = 'block';
        startJmuxer();
    } else {
        stopJmuxer();
        player.style.display = 'none';
        noVideo.style.display = 'block';
        noVideo.textContent = `Codec: ${codec} — use native viewer (video_viewer.py)`;
    }
}

function connectVideoWs() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    videoWs = new WebSocket(`${proto}//${location.host}/ws/video`);
    videoWs.binaryType = 'arraybuffer';

    const noVideo = document.getElementById('no-video');
    const statsEl = document.getElementById('video-stats');

    videoWs.onopen = () => {
        statsEl.textContent = 'connected, waiting for codec info...';
    };

    videoWs.onclose = () => {
        noVideo.style.display = 'block';
        noVideo.textContent = 'Video disconnected';
        stopJmuxer();
        currentCodec = '';
        setTimeout(connectVideoWs, 2000);
    };

    videoWs.onerror = () => videoWs.close();

    videoWs.onmessage = (e) => {
        if (!videoActive || !(e.data instanceof ArrayBuffer) || e.data.byteLength === 0) return;

        const data = new Uint8Array(e.data);
        jmuxer.feed({ video: data });

        videoFrameCount++;
        videoByteCount += data.byteLength;

        const now = performance.now();
        if (now - videoStatsTime >= 1000) {
            const dt = (now - videoStatsTime) / 1000;
            const fps = (videoFrameCount / dt).toFixed(1);
            const bw = ((videoByteCount * 8) / (dt * 1e6)).toFixed(2);
            const avg = videoFrameCount > 0 ? (videoByteCount / videoFrameCount / 1024).toFixed(1) : '0';
            statsEl.textContent = `${currentCodec} | ${fps} fps | ${bw} Mbps | ${avg} KB/frame`;
            videoFrameCount = 0;
            videoByteCount = 0;
            videoStatsTime = now;
        }
    };
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initVideo);
} else {
    initVideo();
}
