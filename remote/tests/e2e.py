"""Run against a built relay binary: python -m remote.tests.e2e /path/to/binary."""
import asyncio
import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, ConnectionClosed
from remote.collector import demo_frame
from remote.upstream import ROOT


async def main(binary):
    sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close()
    origin=f"http://127.0.0.1:{port}"
    base=f"ws://127.0.0.1:{port}"
    pilot_token=secrets.token_urlsafe(32);viewer_token=secrets.token_urlsafe(32)
    env={**os.environ,"SPOTTER_ROOT":str(ROOT),"SPOTTER_PYTHON":sys.executable,
         "SPOTTER_ADDR":f"127.0.0.1:{port}","SPOTTER_PILOT_TOKEN":pilot_token,"SPOTTER_VIEW_TOKEN":viewer_token}
    with tempfile.TemporaryFile() as logs:
        server=subprocess.Popen([binary],env=env,stdout=logs,stderr=logs)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(origin+"/healthz",timeout=.5).close();break
                except OSError:await asyncio.sleep(.05)
            else:raise RuntimeError("relay did not start")
            from remote.collector import run
            from types import SimpleNamespace
            bad_env=os.environ.get('SPOTTER_PILOT_TOKEN')
            os.environ['SPOTTER_PILOT_TOKEN']=viewer_token
            try:
                await run(SimpleNamespace(url=base+'/ws/pilot',allow_insecure_local=True,demo=True,hz=20))
                raise AssertionError('wrong pilot key accepted')
            except RuntimeError as exc:
                assert 'HTTP 401' in str(exc)
                assert viewer_token not in str(exc)
            finally:
                if bad_env is None:os.environ.pop('SPOTTER_PILOT_TOKEN',None)
                else:os.environ['SPOTTER_PILOT_TOKEN']=bad_env
            try:
                async with connect(base+"/ws/pilot",additional_headers={"Authorization":"Bearer "+viewer_token}):
                    raise AssertionError("viewer can publish")
            except InvalidStatus as exc:assert exc.response.status_code==401
            req=urllib.request.Request(origin+"/api/session",data=json.dumps({"token":viewer_token}).encode(),
                                       headers={"Origin":origin,"Content-Type":"application/json"})
            resp=urllib.request.urlopen(req,timeout=2)
            cookie=resp.headers["Set-Cookie"].split(";",1)[0]
            assert "HttpOnly" in resp.headers["Set-Cookie"]
            async with connect(base+"/ws/view",origin=origin,additional_headers={"Cookie":cookie}) as view:
                first=json.loads(await view.recv());assert first["state"] is None
                async with connect(base+"/ws/pilot",additional_headers={"Authorization":"Bearer "+pilot_token}) as pilot:
                    bad_env=os.environ.get('SPOTTER_PILOT_TOKEN')
                    os.environ['SPOTTER_PILOT_TOKEN']=pilot_token
                    waiting=None
                    try:
                        waiting=asyncio.create_task(run(SimpleNamespace(url=base+'/ws/pilot',allow_insecure_local=True,demo=True,hz=20)))
                        await asyncio.sleep(.2)
                        assert not waiting.done(), 'HTTP 409 must wait and retry, not exit the collector'
                    finally:
                        if waiting:
                            waiting.cancel()
                            try:await waiting
                            except asyncio.CancelledError:pass
                        if bad_env is None:os.environ.pop('SPOTTER_PILOT_TOKEN',None)
                        else:os.environ['SPOTTER_PILOT_TOKEN']=bad_env
                    frame=dict(type="ingest",protocolVersion=1,overlayProtocolVersion=1,mode="demo",streamId="e2e",sessionId="test",seq=0,
                               capturedAt=time.time()*1000,**demo_frame(0))
                    # Pretty-printed JSON must also be accepted by the JSON-lines worker.
                    await pilot.send(json.dumps(frame,indent=2))
                    for _ in range(30):
                        update=json.loads(await asyncio.wait_for(view.recv(),2))
                        if update["state"]:break
                    assert update["state"]["pilot"]["speedKph"]==225
                    assert update["state"]["compute"]["headless"] is True
                    assert update["sourceConnected"] is True
                    assert len(update["state"]["cars"])==12
                    assert len(update['state']['overlays']['catalog'])==76
                    assert not update['state']['overlays']['moduleErrors']
                    # A second pilot cannot replace the active source.
                    try:
                        async with connect(base+"/ws/pilot",additional_headers={"Authorization":"Bearer "+pilot_token}):
                            raise AssertionError("duplicate pilot accepted")
                    except InvalidStatus as exc:assert exc.response.status_code==409
                for _ in range(30):
                    update=json.loads(await asyncio.wait_for(view.recv(),2))
                    if not update["sourceConnected"]:break
                assert not update["sourceConnected"]
                # Reconnect creates a fresh worker and accepts a new stream.
                async with connect(base+"/ws/pilot",additional_headers={"Authorization":"Bearer "+pilot_token}) as pilot:
                    frame["streamId"]="reconnected";await pilot.send(json.dumps(frame))
                    for _ in range(30):
                        update=json.loads(await asyncio.wait_for(view.recv(),2))
                        if update["state"]["streamId"]=="reconnected":break
                    assert update["state"]["streamId"]=="reconnected"
                print("E2E PASS: role separation, login, raw ingest, server compute, viewer, duplicate protection, reconnect")
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=="__main__":asyncio.run(main(str(Path(sys.argv[1]).resolve())))
