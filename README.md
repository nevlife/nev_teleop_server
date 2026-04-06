# NEV Teleop Server

NEV 원격 조종 시스템의 중간 서버. 로봇과 클라이언트 사이에서 Zenoh 릴레이, 텔레메트리 집계, 영상 중계를 수행합니다.

## 구조

```
main.py                      # 진입점 (asyncio 이벤트 루프)
config.yaml                  # 설정 파일
state.py                     # 공유 상태 (텔레메트리, 리소스, 제어)
robot_bridge.py              # 로봇 ↔ GCS Zenoh 브릿지
station_bridge.py            # 스테이션 → 로봇 명령 릴레이
config/                      # 설정 스키마 + 로더
telemetry/                   # 타임스탬프 파싱, 지연 계산
zenoh_utils/                 # Zenoh QoS, 세션 설정
web/
├── server.py                # FastAPI (HTTP/WebSocket)
├── video_relay.py           # H.264/H.265 NAL 브로드캐스터
├── rtc_relay.py             # WebRTC DataChannel 릴레이
└── static/                  # 웹 대시보드 (감시용)
```

## 역할

```
로봇 → Zenoh(nev/robot/*) → [서버] → Zenoh(nev/gcs/*) → 클라이언트(PySide6)
클라이언트 → Zenoh(nev/station/*) → [서버] → Zenoh(nev/gcs/*) → 로봇
```

- 로봇 텔레메트리 13개 토픽을 집계하여 단일 JSON으로 클라이언트에 전달
- 영상 NAL 중계 (H.264/H.265, 타임스탬프 헤더 추가)
- 스테이션 명령 릴레이 (아커만 조향 변환)
- 웹 대시보드 (감시/모니터링용)
- E-stop / 모드 전환

## 실행

```bash
python3 main.py
```

대시보드: `http://localhost:8000`

## Zenoh 토픽

### 구독 (로봇 → 서버)

| 토픽 | 내용 |
|------|------|
| `nev/robot/*` | mux, twist, network, hunter, estop, cpu, mem, gpu, disk, net, camera, video_stats, pong |

### 구독 (스테이션 → 서버)

| 토픽 | 내용 |
|------|------|
| `nev/station/*` | client_heartbeat, teleop, estop, cmd_mode, controller_heartbeat, ping |

### 발행 (서버 → 로봇/클라이언트)

| 토픽 | 내용 |
|------|------|
| `nev/gcs/heartbeat` | 서버 하트비트 |
| `nev/gcs/teleop` | 속도/각속도 명령 |
| `nev/gcs/estop` | E-stop (RELIABLE) |
| `nev/gcs/cmd_mode` | 모드 변경 (RELIABLE) |
| `nev/gcs/telemetry` | 텔레메트리 집계 JSON |
| `nev/gcs/camera` | 영상 NAL 중계 (확장 헤더) |
| `nev/gcs/station_pong` | 클라이언트 RTT 응답 |
| `nev/gcs/ping` | 로봇 RTT 측정 |

## 의존성

- [eclipse-zenoh](https://zenoh.io/) 1.8.0
- [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/)
- [aiortc](https://github.com/aiortc/aiortc)
- [PyYAML](https://pyyaml.org/)
