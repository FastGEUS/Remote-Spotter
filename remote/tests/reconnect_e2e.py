"""Fault recovery against the real relay: stalled pilot, retry and VPS restart."""
import asyncio
import contextlib
import http.cookiejar
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
from types import SimpleNamespace
from websockets.asyncio.client import connect
from remote.collector import demo_frame, run
from remote.upstream import ROOT


async def main(binary):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    origin=f'http://127.0.0.1:{port}';base=f'ws://127.0.0.1:{port}'
    token=secrets.token_urlsafe(32);view_token=secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory() as state, tempfile.TemporaryFile() as logs:
        env={**os.environ,'SPOTTER_ROOT':str(ROOT),'SPOTTER_PYTHON':sys.executable,'SPOTTER_ADDR':f'127.0.0.1:{port}',
             'SPOTTER_PILOT_TOKEN':token,'SPOTTER_VIEW_TOKEN':view_token,'SPOTTER_STATE_DIR':state}
        server=None;collector=None;idle=None
        saved=os.environ.get('SPOTTER_PILOT_TOKEN');os.environ['SPOTTER_PILOT_TOKEN']=token
        async def start():
            process=subprocess.Popen([binary],env=env,stdout=logs,stderr=logs)
            for _ in range(100):
                try:urllib.request.urlopen(origin+'/healthz',timeout=.2).close();return process
                except OSError:await asyncio.sleep(.05)
            process.kill();process.wait();raise AssertionError('server start failed')
        async def until(view,predicate,timeout=25):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                e=json.loads(await asyncio.wait_for(view.recv(),2))
                if e.get('state') and predicate(e):return e['state']
            raise AssertionError('telemetry did not recover')
        try:
            server=await start()
            req=urllib.request.Request(origin+'/api/session',data=json.dumps({'token':view_token}).encode(),
                                       headers={'Origin':origin,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=2) as r:cookie=r.headers['Set-Cookie'].split(';',1)[0]
            async with connect(base+'/ws/view',origin=origin,additional_headers={'Cookie':cookie}) as view:
                idle=await connect(base+'/ws/pilot',additional_headers={'Authorization':'Bearer '+token})
                frame=dict(type='ingest',protocolVersion=1,mode='demo',streamId='idle',sessionId='old',seq=0,capturedAt=time.time()*1000,**demo_frame(0))
                await idle.send(json.dumps(frame))
                await until(view,lambda e:e['state']['streamId']=='idle')
                collector=asyncio.create_task(run(SimpleNamespace(url=base+'/ws/pilot',allow_insecure_local=True,demo=True,hz=20)))
                await asyncio.sleep(.25)
                assert not collector.done(), 'busy source exited collector'
                # Idle client still automatically pongs. Data deadline must expire.
                recovered=await until(view,lambda e:e['state']['streamId']!='idle' and e['sourceConnected'] and e['state']['seq']>=5)
                await asyncio.wait_for(idle.wait_closed(),2)
                assert not collector.done()
                stream,seq=recovered['streamId'],recovered['seq']
                print('PASS: HTTP 409 waits; silent publisher expires even with pongs; collector takes free slot')
            server.terminate();await asyncio.to_thread(server.wait,5);server=None
            await asyncio.sleep(.25)
            assert not collector.done(), 'relay restart exited collector'
            server=await start()
            # A signed viewer cookie remains valid with the same server key.
            async with connect(base+'/ws/view',origin=origin,additional_headers={'Cookie':cookie}) as view:
                recovered=await until(view,lambda e:e['state']['streamId']==stream and e['state']['seq']>seq and e['sourceConnected'],timeout=15)
                assert not collector.done()
                print('PASS: server restart resumes same collector stream and viewer login; received frames ACKed')
        finally:
            if collector:
                collector.cancel()
                with contextlib.suppress(asyncio.CancelledError):await collector
            if idle:await idle.close()
            if server:
                server.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):await asyncio.to_thread(server.wait,5)
                if server.poll() is None:server.kill();server.wait()
            if saved is None:os.environ.pop('SPOTTER_PILOT_TOKEN',None)
            else:os.environ['SPOTTER_PILOT_TOKEN']=saved


if __name__=='__main__':asyncio.run(main(str(Path(sys.argv[1]).resolve())))
