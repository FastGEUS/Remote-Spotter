"""Real relay regression: waiting -> native frames + REST -> bad REST -> recovery."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from websockets.asyncio.client import connect
from remote.tests.test_rest_recovery import lmu_frame
from remote.upstream import ROOT


async def main(binary):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    base = f'ws://127.0.0.1:{port}'
    pilot_token, view_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as state, tempfile.TemporaryFile() as logs:
        env = {**os.environ, 'SPOTTER_ROOT': str(ROOT), 'SPOTTER_PYTHON': sys.executable,
               'SPOTTER_STATE_DIR': state, 'SPOTTER_ADDR': f'127.0.0.1:{port}',
               'SPOTTER_PILOT_TOKEN': pilot_token, 'SPOTTER_VIEW_TOKEN': view_token}
        server = subprocess.Popen([binary], env=env, stdout=logs, stderr=logs)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(origin+'/healthz', timeout=.2).close()
                    break
                except OSError:
                    await asyncio.sleep(.05)
            else:
                raise AssertionError('Relay did not start')
            req = urllib.request.Request(origin+'/api/session',
                  data=json.dumps({'token': view_token}).encode(),
                  headers={'Origin': origin, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=2) as response:
                cookie = response.headers['Set-Cookie'].split(';', 1)[0]
            async with connect(base+'/ws/view', origin=origin,
                               additional_headers={'Cookie': cookie}) as view:
                received = []
                async def read_view():
                    async for raw in view:
                        envelope = json.loads(raw)
                        if envelope.get('state'):
                            received.append(envelope)
                view_task = asyncio.create_task(read_view())
                try:
                    async with connect(base+'/ws/pilot', additional_headers={
                        'Authorization': 'Bearer '+pilot_token, 'X-Spotter-Ack': '1'}) as pilot:
                        assert pilot.response.headers.get('X-Spotter-Ack') == '1'
                        waiting = lmu_frame()
                        waiting.update(status='waitingForGame', pilot=None, cars=[], gameTime=0)
                        waiting.pop('rawSnapshot')
                        waiting.pop('rest')
                        await pilot.send(json.dumps(waiting))
                        assert json.loads(await asyncio.wait_for(pilot.recv(), 10)) == {'type': 'ack', 'seq': 0}
                        for seq in range(1, 181):
                            tick = time.monotonic()
                            frame = lmu_frame(seq)
                            if seq <= 20:
                                frame['status'] = 'garage'
                            if 61 <= seq <= 120:
                                frame['rest']['/rest/garage/UIScreen/RepairAndRefuel'] = {
                                    'ok': True, 'capturedAt': frame['capturedAt'],
                                    'data': {'pitMenu': {'pitMenu': [{'name': 'FUEL:'}]}}}
                            await pilot.send(json.dumps(frame, allow_nan=False))
                            ack = json.loads(await asyncio.wait_for(pilot.recv(), 10))
                            assert ack == {'type': 'ack', 'seq': seq}, ack
                            await asyncio.sleep(max(0, .05-(time.monotonic()-tick)))
                        for _ in range(40):
                            if received and received[-1]['state']['seq'] == 180:
                                break
                            await asyncio.sleep(.05)
                        latest = received[-1]
                        assert latest['sourceConnected'] and latest['state']['seq'] == 180
                        assert latest['state']['pilot']['speedKph'] == 225
                        assert 'lastCarSetup' in latest['state']['overlays']['restAvailable']
                        assert not latest['state']['overlays']['restErrors']
                        bad = [e for e in received if e['state'].get('overlays') and
                               'absoluteRefill' in e['state']['overlays']['restErrors']]
                        assert bad, 'Damaged REST stage was never presented'
                        assert all(e['sourceConnected'] and e['state']['pilot']['speedKph'] == 225 for e in bad)
                        print('REST E2E PASS: waiting -> garage -> driving, 180 native frames at up to 20 Hz on one socket; '
                              'garage setup, parser failure isolation, recovery, viewer updates')
                finally:
                    view_task.cancel()
                    try:
                        await view_task
                    except asyncio.CancelledError:
                        pass
            logs.seek(0)
            log_text = logs.read().decode('utf-8', errors='replace')
            assert 'Traceback' not in log_text and 'compute source closed' not in log_text
            assert log_text.count('pilot connected;') == 1
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    asyncio.run(main(str(Path(sys.argv[1]).resolve())))
