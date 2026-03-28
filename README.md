# NEV Teleop Server

NEV 원격 조종 시스템의 중간 서버. 로봇 텔레메트리를 수집하고, 웹 대시보드와 H.265 영상 스트리밍을 제공합니다.

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
├── video_relay.py           # H.265 NAL 브로드캐스터
├── rtc_relay.py             # WebRTC DataChannel 릴레이
└── static/                  # 웹 대시보드 (HTML/JS/CSS)
tests/                       # 유닛 테스트
```

## 실행

```bash
pip install -r requirements.txt
python main.py --config config.yaml
```

대시보드: `http://localhost:8080`

## 주요 기능

- 로봇 텔레메트리 13개 토픽 수신 (mux, twist, hunter, estop, cpu, gpu, mem, disk, net, camera 등)
- 조이스틱 스테이션 명령 릴레이 (아커만 조향 변환)
- H.265 영상 스트리밍 (WebRTC DataChannel + WebSocket 폴백)
- 실시간 웹 대시보드 (텔레메트리, 시스템 리소스, 영상)
- E-stop / 모드 전환 (웹 UI + 조이스틱)

## Zenoh 토픽

### 구독 (로봇 → 서버)

| 토픽 | 내용 |
|------|------|
| `nev/robot/*` | mux, twist, network, hunter, estop, cpu, mem, gpu, disk, net, camera, hb_ack, video_stats |

### 구독 (스테이션 → 서버)

| 토픽 | 내용 |
|------|------|
| `nev/station/*` | client_heartbeat, teleop, estop, cmd_mode, controller_heartbeat |

### 발행 (서버 → 로봇)

| 토픽 | 내용 |
|------|------|
| `nev/gcs/heartbeat` | 서버 하트비트 |
| `nev/gcs/teleop` | 속도/각속도 명령 |
| `nev/gcs/estop` | E-stop (RELIABLE) |
| `nev/gcs/cmd_mode` | 모드 변경 (RELIABLE) |

## 의존성

- [eclipse-zenoh](https://zenoh.io/)
- [FastAPI](https://fastapi.tiangolo.com/) + [uvicorn](https://www.uvicorn.org/)
- [aiortc](https://github.com/aiortc/aiortc)
- [PyYAML](https://pyyaml.org/)
