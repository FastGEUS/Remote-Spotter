"""Read and send only. Run: python -m remote.collector --demo."""
import argparse
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import time
import uuid
from pathlib import Path
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus
from .profile import clean_token
from .recovery import CaptureState, AckWindow


def configure_logging():
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(Path(__file__).with_name('pilot.log'), maxBytes=500000,
                                            backupCount=2, encoding='utf-8'))
    except OSError:
        pass  # Capture can still run in a read-only installation.
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=handlers, force=True)


def demo_frame(t):
    length, lap_seconds = 4563.0, 16.0
    def pos(progress):
        angle = progress * math.tau
        return [650 * math.cos(angle) + 110 * math.cos(3 * angle), 420 * math.sin(angle)]
    cars = []
    for i in range(12):
        total = max(0, t / lap_seconds - i * 0.015)
        p = total % 1
        x, z = pos(p)
        cars.append({"id": i + 1, "driver": "Demo Pilot" if i == 0 else f"Driver {i+1:02d}",
                     "class": "Hypercar" if i < 4 else "LMGT3", "place": i+1,
                     "laps": int(total), "lapDistM": p * length, "x": x, "z": z,
                     "speedMps": 62.5, "inPit": False})
    return {"status": "live", "gameTime": t,
            "session": {"track": "DEMO • Synthetic circuit", "lengthM": length,
                        "phase": 5, "scoringTime": t, "sessionType": 10,
                        "endTime": 0, "maxLaps": 60},
            "cars": cars,
            "pilot": {"id": 1, "lap": int(t / lap_seconds) + 1,
                      "fuelL": max(0, 100 - t / lap_seconds * 2.5), "speedMps": 62.5,
                      "gear": 6, "rpm": 7200 + 500 * math.sin(t), "lapValid": True,
                      "throttle": 0.8 + 0.2 * math.sin(t), "brake": 0.0,
                      "strategyInputs": {"fuelCapacityL": 110,
                                         "virtualEnergyFraction": max(0, 1-t/lap_seconds*.02),
                                         "lapStartTime": int(t/lap_seconds)*lap_seconds,
                                         "lastLapTime": lap_seconds if t>=lap_seconds else 0,
                                         "inGarage": False},
                      "wheels": [{"temperatureK": 365+i*2, "pressureKpa": 180+i,
                                  "wear": 0.96, "brakeC": 410+i*25} for i in range(4)]},
            "demoMap": [pos(i / 160) for i in range(161)]}


async def run(args, *, token=None, on_event=None):
    # Desktop calls the same collector in a worker thread. No credentials in
    # argv, no second transport, and no telemetry calculations on the pilot.
    token = clean_token(token if token is not None else os.environ.get("SPOTTER_PILOT_TOKEN", ""))
    def event(kind, **fields):
        if on_event:
            on_event({"kind": kind, **fields})
    if not args.url.startswith("wss://") and not (args.allow_insecure_local and args.url.startswith("ws://127.0.0.1:")):
        raise RuntimeError("Use wss://, or --allow-insecure-local for loopback testing only")
    reader = None
    game=getattr(args,'game','lmu')
    if not args.demo:
        if game=='lmu':
            from .native import NativeReader
            reader = NativeReader()
        else:
            from .iracing import IRacingReader,AutoReader
            reader=IRacingReader() if game=='iracing' else AutoReader()
    from .rest_capture import RestCapture
    rest = RestCapture()
    if not args.demo and game=='lmu':
        rest.start()
    stream = str(uuid.uuid4())
    seq = 0
    start = time.monotonic()
    capture = CaptureState(args.demo, start)
    backoff = 1
    try:
        while True:
            try:
                async with connect(args.url, additional_headers={"Authorization": "Bearer " + token, "X-Spotter-Ack": "1"},
                                   open_timeout=10, ping_interval=5, ping_timeout=5, close_timeout=2,
                                   max_size=65536, max_queue=1, compression=None) as ws:
                    logging.info("Connected (%s)", "DEMO" if args.demo else game)
                    event("transport", connected=True)
                    connected_at = time.monotonic()
                    ack = AckWindow(ws) if ws.response.headers.get('X-Spotter-Ack') == '1' else None
                    if ack:
                        ack.start()
                    try:
                        while True:
                            if ack:
                                await ack.ready()
                            tick = time.monotonic()
                            raw = demo_frame(tick - start) if args.demo else reader.read()
                            sample = capture.update(raw, tick, reader)
                            if sample is not None:
                                mode='demo' if args.demo else sample.pop('sourceMode',getattr(reader,'game',game))
                                if mode=='lmu' and not args.demo and not rest.task:rest.start()
                                event("source", status=sample['status'], mode=mode)
                                frame = {"type": "ingest", "protocolVersion": 1,
                                         "streamId": stream, "sessionId": capture.session_id, "seq": seq,
                                         "capturedAt": time.time() * 1000,
                                         "mode": mode, **sample}
                                if not args.demo and mode=='lmu':
                                    frame['rest'] = dict(rest.records)
                                frame['overlayProtocolVersion'] = 1
                                payload = json.dumps(frame, allow_nan=False, separators=(",", ":"))
                                if ack:
                                    ack.sent(seq)
                                await asyncio.wait_for(ws.send(payload), timeout=2)
                                seq += 1
                            if tick-connected_at >= 5:
                                backoff = 1
                            await asyncio.sleep(max(0, 1 / args.hz - (time.monotonic() - tick)))
                    finally:
                        event("transport", connected=False)
                        if ack:
                            await ack.close()
            except InvalidStatus as exc:
                code=exc.response.status_code
                if code==401:
                    event("auth", code=401)
                    raise RuntimeError("HTTP 401: сервер отклонил ключ пилота. Проверьте SPOTTER_PILOT_TOKEN на VPS; ключ споттера не подходит.") from None
                if code==409:
                    event("busy", code=409)
                    logging.warning("HTTP 409: сервер ещё держит прежнее соединение или другой сборщик. Ожидаю освобождения; повтор через 2 с.")
                    await asyncio.sleep(2)
                    continue
                if code != 409:
                    logging.warning("Сервер отказал в подключении (HTTP %s); повтор через %s с",code,backoff)
                await asyncio.sleep(backoff)
                backoff=min(backoff*2,15)
            except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
                event("transport", connected=False)
                logging.warning("Capture/network unavailable (%s); retry in %ss", type(exc).__name__, backoff)
                if isinstance(exc,(ConnectionRefusedError,TimeoutError)):
                    logging.warning("Проверьте, что SSH-туннель открыт и сервер spotter запущен.")
                if reader:
                    reader.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
            except Exception as exc:
                event("transport", connected=False)
                # Includes WebSocket closure; never dump authentication headers.
                logging.warning("Connection ended (%s); retry in %ss", type(exc).__name__, backoff)
                if reader:
                    reader.close()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
    finally:
        event("transport", connected=False)
        rest.close()
        if reader:
            reader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8080/ws/pilot")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--game",choices=('auto','lmu','iracing'),default='auto')
    parser.add_argument("--allow-insecure-local", action="store_true")
    parser.add_argument("--hz", type=int, choices=(5, 10, 20), default=20)
    args = parser.parse_args()
    configure_logging()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
