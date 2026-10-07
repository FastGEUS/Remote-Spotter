"""Actual SDK binary → collector → OpenSSH → relay → embedded Qt panel.

Uses synthetic SDK-compatible bytes and a local SSH peer; not live game QA.
"""
import asyncio
import contextlib
import os
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from unittest.mock import patch
import asyncssh
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from remote.desktop.config import load_startup_profile
from remote.desktop.gui import STYLE,PilotWindow
from remote.desktop.viewer import ViewerWindow
from remote.desktop.tunnel import free_port,http_json
from remote.iracing import IRacingReader
from remote.tests.iracing_fixture import BinaryFixture
from remote.upstream import ROOT


async def main(binary):
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setStyleSheet(STYLE)
    pilot=None;viewer=None;peer=None;relay=None
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary);server_port=free_port();pilot_token=secrets.token_urlsafe(32);viewer_token=secrets.token_urlsafe(32)
        env={**os.environ,'SPOTTER_ROOT':str(ROOT),'SPOTTER_PYTHON':sys.executable,'SPOTTER_ADDR':f'127.0.0.1:{server_port}',
             'SPOTTER_PILOT_TOKEN':pilot_token,'SPOTTER_VIEW_TOKEN':viewer_token,'SPOTTER_STATE_DIR':str(directory/'server')}
        logs=directory/'relay.log'
        output=logs.open('w')
        relay=subprocess.Popen([binary],env=env,stdout=output,stderr=output)
        private=asyncssh.generate_private_key('ssh-ed25519');host_key=asyncssh.generate_private_key('ssh-ed25519')
        key_file=directory/'lmu_spotter';key_file.write_bytes(private.export_private_key('openssh'));key_file.chmod(0o600)
        class Peer(asyncssh.SSHServer):
            def begin_auth(self,username):return True
            def public_key_auth_supported(self):return True
            def validate_public_key(self,username,key):return username=='fixture' and key.export_public_key()==private.export_public_key()
            def connection_requested(self,host,port,*args):return host=='127.0.0.1' and port==server_port
        peer=await asyncssh.create_server(Peer,'127.0.0.1',0,server_host_keys=[host_key]);ssh_port=peer.get_port()
        (directory/'known_hosts').write_text(f'[127.0.0.1]:{ssh_port} '+host_key.export_public_key().decode())
        index=[0]
        class FixtureReader(IRacingReader):
            def __init__(self):
                self.fixture=BinaryFixture(directory/'sdk.bin');super().__init__(test_file=str(self.fixture.path))
            def read(self):
                self.fixture.write(index[0]*.1,index[0]+1);index[0]+=1
                return super().read()
        async def until(check,timeout=30):
            deadline=asyncio.get_running_loop().time()+timeout
            while not check():
                if asyncio.get_running_loop().time()>deadline:
                    raise AssertionError('Condition timed out; relay log: '+logs.read_text()[-5000:])
                app.processEvents();await asyncio.sleep(.01)
        async def javascript(script):
            result=[];viewer.page.runJavaScript(script,result.append)
            await until(lambda:bool(result),5);return result[0]
        try:
            for _ in range(100):
                try:http_json(f'http://127.0.0.1:{server_port}/healthz');break
                except OSError:await asyncio.sleep(.05)
            presets=directory/'presets';presets.mkdir()
            for role in ('pilot','viewer'):
                (presets/(role+'.json')).write_text(json.dumps({'schemaVersion':1,'role':role,
                    'token':pilot_token if role=='pilot' else viewer_token,'ssh_key':'unused',
                    'host':'127.0.0.1','user':'fixture','ssh_port':ssh_port,'server_port':server_port,
                    'game':'iracing','partner_name':'Fixture partner'}))
            with patch('remote.desktop.config.preset_path',lambda role:presets/(role+'.json')),patch('remote.desktop.config.application_dir',lambda:directory):
                profiles={role:load_startup_profile(role,directory)[0] for role in ('pilot','viewer')}
            with patch('remote.iracing.IRacingReader',FixtureReader):
                pilot=PilotWindow(profiles['pilot'],directory=directory);viewer=ViewerWindow(profiles['viewer'],directory=directory)
                errors=[]
                # Catch errors from dashboard scripts, including the expanded drawer.
                viewer.page.javaScriptConsoleMessage=lambda level,message,line,source:errors.append(message) if 'Error' in str(level) else None
                pilot.show();viewer.show();pilot.connect_session();viewer.connect_session()
                await until(lambda:viewer.stack.currentWidget()==viewer.web)
                await until(lambda:pilot.last_state['phase']=='online' and viewer.last_state['game_mode']=='iracing')
                for _ in range(300):
                    mode=await javascript("document.getElementById('mode').textContent")
                    if 'iRacing' in mode:break
                    await asyncio.sleep(.02)
                assert 'iRacing' in mode
                assert await javascript("document.getElementById('standings').children.length")==3
                assert await javascript("document.querySelector('.radar-range').hidden")
                assert await javascript("document.querySelector('.radar-panel h2').textContent")=='Темп и соседство'
                viewer.navigate('overlays');await until(lambda:viewer.isVisible())
                for _ in range(1000):
                    value=json.loads(await javascript("JSON.stringify({map:document.getElementById('map-status').textContent,panels:document.querySelectorAll('[data-overlay]').length,radar:document.querySelector('[data-overlay=radar] .panel-status')?.textContent})"))
                    if value['map']=='КРУГ ЗАПИСАН':break
                    await asyncio.sleep(.02)
                assert value['map']=='КРУГ ЗАПИСАН',value
                assert value['panels']==76 and value['radar']=='Не поддерживается',value
                assert 'Снимок' in await javascript("document.querySelector('[data-overlay=tyre_wear] .panel-status').textContent")
                assert 'iRacing' in pilot.game_label.text()
                assert not errors,errors
                pilot.close()
                await until(lambda:not pilot.worker.isRunning())
                assert viewer.worker.isRunning() and viewer.isVisible()
                for _ in range(100):
                    app.processEvents();await asyncio.sleep(.01)
                assert viewer.last_state['partner_connected'] is False
                viewer.close()
                await until(lambda:not viewer.worker.isRunning() and not pilot.isVisible() and not viewer.isVisible())
                print('IRACING E2E PASS: paired role credentials, automatic key beside app, actual SDK binary capture, both GUI roles, real OpenSSH, server calculation, native cookie session, 76 capability cards, map, proximity-only radar, partner disconnect, clean shutdown',flush=True)
        finally:
            for window in (pilot,viewer):
                if window:
                    window.close()
                    for _ in range(800):
                        if not window.worker or not window.worker.isRunning():break
                        app.processEvents();await asyncio.sleep(.01)
                    window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            peer.close();await peer.wait_closed()
            relay.terminate()
            try:relay.wait(timeout=5)
            except subprocess.TimeoutExpired:relay.kill();relay.wait()
            output.close()

if __name__=='__main__':asyncio.run(main(str(Path(sys.argv[1]).resolve())))
