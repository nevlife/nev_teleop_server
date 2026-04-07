#!/usr/bin/env python3
"""Zenoh 수신 테스트 (서버). 라우터 모드로 리스닝 + nev/test/ping 구독."""
import argparse
import json
import time
import zenoh


def on_sample(sample):
    try:
        data = json.loads(bytes(sample.payload))
        rtt_info = ''
        ts = data.get('ts')
        if ts:
            delay_ms = (time.time() - ts) * 1000
            rtt_info = f'  delay={delay_ms:.1f}ms'
        print(f'RECV [{data.get("seq", "?")}] {bytes(sample.payload).decode()}{rtt_info}')
    except Exception as e:
        print(f'RECV raw ({len(bytes(sample.payload))}B): {e}')


def main():
    parser = argparse.ArgumentParser(description='Zenoh receive test')
    parser.add_argument('--port', type=int, default=7447)
    args = parser.parse_args()

    conf = zenoh.Config()
    listen_ep = f'tcp/0.0.0.0:{args.port}'
    conf.insert_json5('mode', '"router"')
    conf.insert_json5('listen/endpoints', json.dumps([listen_ep]))

    print(f'Starting Zenoh router on {listen_ep} ...')
    session = zenoh.open(conf)
    print(f'Listening! Waiting for messages on nev/test/ping ...')

    sub = session.declare_subscriber('nev/test/ping', on_sample)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        sub.undeclare()
        session.close()
        print('Done')


if __name__ == '__main__':
    main()
