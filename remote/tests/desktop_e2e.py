"""Real relay + collector + owned subprocess, simulated SSH network peer."""
import asyncio
import contextlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from unittest.mock import patch

from remote.desktop.config import Profile
from remote.desktop.session import Session
from remote.desktop.tunnel import Tunnel,free_port,http_json
from remote.upstream import ROOT

async def main(binary):
    server_port=free_port();pilot_token=secrets.token_urlsafe(32);viewer_token=secrets.token_urlsafe(32)
    env={**os.environ,'SPOTTER_ROOT':str(ROOT),'SPOTTER_PYTHON':sys.executable,
         'SPOTTER_ADDR':f'127.0.0.1:{server_port}','SPOTTER_PILOT_TOKEN':pilot_token,'SPOTTER_VIEW_TOKEN':viewer_token}
    logs=tempfile.TemporaryFile();server=subprocess.Popen([binary],env=env,stdout=logs,stderr=logs)
    tunnels=[];events={'pilot':[],'viewer':[]};tasks=[]
    class Tracked(Tunnel):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);tunnels.append(self)
    def forward(profile,port,*args):
        return [sys.executable,str(Path(__file__).with_name('desktop_forwarder.py')),str(server_port),str(port)]
    async def until(check,timeout=25):
        deadline=asyncio.get_running_loop().time()+timeout
        while not check():
            if asyncio.get_running_loop().time()>deadline:raise AssertionError('Timed out waiting for desktop state')
            for task in tasks:
                if task.done():await task;raise AssertionError('Session exited early')
            await asyncio.sleep(.05)
    try:
        await until(lambda:server.poll() is None,.1)
        for _ in range(100):
            try:http_json(f'http://127.0.0.1:{server_port}/healthz');break
            except OSError:await asyncio.sleep(.05)
        with tempfile.TemporaryDirectory() as directory,patch('remote.desktop.tunnel.command',forward):
            profiles={r:Profile(r,pilot_token if r=='pilot' else viewer_token,'unused',server_port=server_port,partner_name='Друг') for r in events}
            sessions={r:Session(p,directory,events[r].append,demo=True,tunnel_factory=Tracked) for r,p in profiles.items()}
            tasks.extend(asyncio.create_task(s.run()) for s in sessions.values())
            await until(lambda:any(e.get('kind')=='viewer-session' for e in events['viewer']) and sessions['pilot'].state.phase=='online' and sessions['viewer'].state.data_fresh)
            # A real viewer socket, just as embedded QtWebEngine opens one.
            from websockets.asyncio.client import connect
            event=next(e for e in events['viewer'] if e['kind']=='viewer-session')
            cookie=event['cookie'].split(';',1)[0]
            async with connect(event['origin'].replace('http:','ws:')+'/ws/view',origin=event['origin'],additional_headers={'Cookie':cookie}) as ws:
                frame=await ws.recv()
                assert 'presentation' in frame
                await until(lambda:sessions['pilot'].state.partner_connected is True)
            await until(lambda:sessions['pilot'].state.partner_connected is False)
            # Simulated dropped SSH process: both tunnel and capture are recreated.
            pilot_tunnel=next(t for t in tunnels if t.profile.role=='pilot')
            old_process=pilot_tunnel.process;old_process.kill();await old_process.wait()
            await until(lambda:len([t for t in tunnels if t.profile.role=='pilot'])>=2 and sessions['pilot'].state.phase=='online')
            assert any(e.get('phase')=='reconnecting' for e in events['pilot'])
            assert sessions['viewer'].state.phase=='online'
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            assert all(t.process is None for t in tunnels)
            assert all(s.state.phase=='offline' for s in sessions.values())
            print('DESKTOP E2E PASS: authenticated panel session, capture, server compute, partner presence, tunnel process restart, cancellation cleanup')
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        logs.close()

if __name__=='__main__':asyncio.run(main(str(Path(sys.argv[1]).resolve())))
