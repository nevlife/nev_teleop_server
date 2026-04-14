# NEV Teleop Server

NEV 원격 조종 시스템의 중간 서버. 차량(Bot)과 클라이언트(Station) 사이에서 Zenoh 릴레이, 텔레메트리 집계, 영상 중계를 수행합니다.

## 구조

```
main.py                      # 진입점 (asyncio 이벤트 루프)
config.yaml                  # 설정 파일
state.py                     # 공유 상태 (차량별 텔레메트리, 제어, 알림)
robot_bridge.py              # Bot ↔ Server Zenoh 브릿지
station_bridge.py            # Station → Server → Bot 명령 릴레이
config/                      # 설정 스키마 + 로더
telemetry/                   # 타임스탬프 파싱
zenoh_utils/                 # Zenoh 세션 설정
```

## 데이터 흐름

```
Bot → nev/robot/{id}/* → [Server] → nev/gcs/{id}/* → Client
Client → nev/station/{id}/* → [Server] → nev/gcs/{id}/* → Bot
```

## 실행

```bash
python3 main.py [--config config.yaml] [--zenoh-port 7447]
```

## 설정

`config.yaml`:

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `zenoh_port` | `7447` | Zenoh 라우터 리슨 포트 (TCP+UDP) |
| `telemetry_rate` | `2.0` | 텔레메트리 푸시 주기 (Hz) |
| `station_timeout` | `3.0` | 클라이언트 연결 타임아웃 (초) |
| `ping_rate` | `1.0` | server_ping 주기 (Hz) |
| `disconnect_timeout` | `3.0` | 봇 연결 끊김 판정 (초) |

## Zenoh 토픽

### 구독: Bot → Server (`nev/robot/{id}/*`)

| 토픽 | 처리 |
|------|------|
| `mux`, `twist`, `estop` | 상태 저장 → telemetry에 포함 |
| `cpu`, `mem`, `gpu`, `disk`, `net` | 리소스 저장 → telemetry에 포함 |
| `camera` | 12B→20B 헤더 확장 후 클라이언트로 릴레이 |
| `video_stats` | 인코딩 통계 저장 → telemetry에 포함 |
| `vehicle/*` | 동적 토픽 저장 → telemetry에 포함 |
| `server_pong` | srv↔bot RTT 계산 |
| `bot_pong` | 클라이언트로 즉시 릴레이 (cli↔bot RTT) |

### 구독: Client → Server (`nev/station/{id}/*`)

| 토픽 | 처리 |
|------|------|
| `teleop` | `{linear_x, steer_angle}` 봇으로 즉시 릴레이 |
| `estop` | 봇으로 즉시 릴레이 (RELIABLE) |
| `cmd_mode` | 봇으로 즉시 릴레이 (RELIABLE) |
| `controller_heartbeat` | 조이스틱 상태 저장 + station 연결 추적 |
| `station_ping` | station_pong 즉시 에코 |
| `bot_ping` | 봇으로 즉시 릴레이 |

### 발행: Server → Bot (`nev/gcs/{id}/*`)

| 토픽 | 방식 | 내용 |
|------|------|------|
| `server_ping` | 고정 1Hz | `{ts}` — heartbeat + RTT |
| `bot_ping` | 즉시 릴레이 | `{ts}` — cli↔bot RTT |
| `teleop` | 즉시 릴레이 | `{linear_x, steer_angle}` |
| `estop` | 즉시 릴레이 | `{active}` (RELIABLE) |
| `cmd_mode` | 즉시 릴레이 | `{mode}` (RELIABLE) |

### 발행: Server → Client (`nev/gcs/{id}/*`)

| 토픽 | 방식 | 내용 |
|------|------|------|
| `telemetry` | 고정 (telemetry_rate Hz) | 통합 JSON (전 차량 상태 + 제어 + 알림) |
| `camera` | 즉시 릴레이 | 20B 헤더 + NAL (vehicle_ts, encode_ms, server_rx_ts, veh_to_srv_ms) |
| `station_pong` | 즉시 에코 | `{ts}` — cli↔srv RTT |
| `bot_pong` | 즉시 릴레이 | `{ts}` — cli↔bot RTT |

## 판단/계산 영역

- **srv↔bot RTT**: server_ping/server_pong
- **대역폭 계산**: 영상/텔레메트리 수신 바이트 → Mbps (1초 주기)
- **카메라 릴레이 헤더**: 봇 12B 헤더에 server_rx_ts + veh_to_srv_ms 8B 추가 → 20B
- **봇 연결 감지**: 봇 데이터 3초 미수신 → 끊김
- **클라이언트 연결 감지**: controller_heartbeat 2초 미수신 → 끊김
- **Alerts 생성**: 상태 모순 감지 (E-Stop+이동, 제어 타임아웃, 스테이션 미연결 등)
- **상태 통합**: 전 차량 + 클라이언트 상태 → 단일 telemetry JSON

## 의존성

- [eclipse-zenoh](https://zenoh.io/) 1.8.0
- [PyYAML](https://pyyaml.org/)
