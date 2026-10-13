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
import yaml
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from remote.desktop.config import load_startup_profile
from remote.desktop.gui import STYLE,PilotWindow
from remote.desktop.viewer import ViewerWindow
from remote.desktop.tunnel import free_port,http_json
from remote.iracing import IRacingReader
from remote.tests.iracing_fixture import BinaryFixture,values,sections
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
        index=[0];phase=['practice'];readers=[]
        def full_roster():
            metadata=sections();drivers=yaml.safe_load(metadata['DriverInfo'])['DriverInfo']
            drivers['Drivers']=[{'CarIdx':i,'UserName':f'Driver {i:02d} · full roster test',
                'CarNumber':str(i+1),'CarClassShortName':'GT3' if i%2 else 'GTP','CarClassID':i%2+1}
                for i in range(64)]
            metadata['DriverInfo']=yaml.safe_dump({'DriverInfo':drivers},allow_unicode=True,sort_keys=False)
            if phase[0]=='race':
                metadata={key:value.replace('SDK fixture circuit','New race circuit') for key,value in metadata.items()}
            return metadata
        def full_values(t):
            result=values(t);pct=result['LapDistPct'];lap=result['Lap']
            result['SessionUniqueID']=111 if phase[0]=='practice' else 222
            result['SessionNum']=0 if phase[0]=='practice' else 1
            result.update(CarIdxLapDistPct=[(pct+i*.01)%1 for i in range(64)],
                CarIdxTrackSurface=[3]*64,CarIdxLapCompleted=[lap-1]*64,
                CarIdxPosition=list(range(1,65)),CarIdxClassPosition=[i//2+1 for i in range(64)],
                CarIdxOnPitRoad=[False]*64,CarIdxLastLapTime=[10.+i/10 for i in range(64)],
                CarIdxBestLapTime=[10.+i/10 for i in range(64)],CarIdxF2Time=[i/10 for i in range(64)],
                CarIdxSessionFlags=[0]*64)
            result['CarIdxLapDistPct'][2]=pct
            for wheel in ('LF','RF','LR','RR'):
                result.update({wheel+'tempCL':80.,wheel+'tempCM':85.,wheel+'tempCR':90.,wheel+'pressure':180.})
            return result
        class FixtureReader(IRacingReader):
            def __init__(self):
                self.fixture=BinaryFixture(directory/'sdk.bin',values_fn=full_values,sections_fn=full_roster)
                super().__init__(test_file=str(self.fixture.path))
                readers.append(self)
            def read(self):
                if phase[0]!='closed':
                    self.fixture.write(index[0]*.1,index[0]+1);index[0]+=1
                sample=super().read()
                if sample and index[0]==35:
                    sample['iracingSnapshot']['values']['LFwearL']=1.5
                return sample
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
                viewer.resize(1920,1080)
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
                assert 'iRacing' in mode,{'mode':mode,'errors':errors,'relayLog':logs.read_text()[-5000:],
                    'panel':await javascript("JSON.stringify({connection:document.getElementById('connection').textContent,loginHidden:document.getElementById('login').hidden})")}
                assert await javascript("document.getElementById('standings').children.length")==8
                assert 'Driver 07' in await javascript("document.getElementById('standings').lastElementChild.textContent")
                assert await javascript("latest.state.cars.length")==64
                assert await javascript("document.body.classList.contains('embedded')")
                assert await javascript("[...document.querySelectorAll('.pitwall section')].every(n=>n.getBoundingClientRect().bottom<=innerHeight && n.scrollHeight<=n.clientHeight+2)")
                assert await javascript("document.querySelector('.positions .table-wrap').scrollHeight<=document.querySelector('.positions .table-wrap').clientHeight+1")
                assert await javascript("document.getElementById('wheels').firstElementChild.querySelector('b').textContent")=='85.0°'
                assert viewer.web.width()>=viewer.width()-2
                assert await javascript("document.querySelector('.radar-range').hidden")
                assert await javascript("document.querySelector('.radar-panel h2').textContent")=='Темп и трафик'
                assert await javascript("document.getElementById('radar').hidden && !document.getElementById('iracing-proximity').hidden")
                viewer.navigate('overlays');await until(lambda:viewer.isVisible())
                for _ in range(1000):
                    value=json.loads(await javascript("JSON.stringify({map:document.getElementById('map-status').textContent,panels:document.querySelectorAll('[data-overlay]').length,radar:document.querySelector('[data-overlay=radar] .panel-status')?.textContent})"))
                    if value['map']=='КРУГ ЗАПИСАН':break
                    await asyncio.sleep(.02)
                assert value['map']=='КРУГ ЗАПИСАН',value
                result,_=http_json(f'http://127.0.0.1:{server_port}/api/status',token=pilot_token)
                assert result['rejectedFrames']>=1 and result['sourceConnected'],result
                assert logs.read_text().count('pilot connected; server compute started')==1
                assert value['panels']==76 and value['radar']=='Не поддерживается',value
                assert 'Замер' in await javascript("document.querySelector('[data-overlay=tyre_wear] .panel-status').textContent")
                assert 'iRacing' in pilot.game_label.text()
                assert not errors,errors
                old_session=await javascript('latest.state.sessionId')
                phase[0]='closed'
                await asyncio.sleep(.1)
                readers[0].fixture.path.unlink(missing_ok=True)
                await until(lambda:pilot.last_state['game']=='waitingForGame',10)
                assert pilot.last_state['phase']=='online',pilot.last_state
                phase[0]='race';index[0]=0
                readers[0].fixture=BinaryFixture(directory/'sdk.bin',values_fn=full_values,sections_fn=full_roster)
                for _ in range(300):
                    value=json.loads(await javascript("JSON.stringify({session:latest.state.sessionId,track:latest.state.session.track,cars:latest.state.cars.length,status:latest.state.status,age:latest.sourceAgeMs})"))
                    if value['track']=='New race circuit' and value['status']=='live' and value['cars']==64 and value['session']!=old_session and value['age']<1000:break
                    await asyncio.sleep(.03)
                else:raise AssertionError(('No fresh race after simulator replacement',value))
                result,_=http_json(f'http://127.0.0.1:{server_port}/api/status',token=pilot_token)
                assert result['sourceConnected'] and result['gameStatus']=='live',result
                assert logs.read_text().count('pilot connected; server compute started')==1
                assert not errors,errors
                print('SIMULATOR RESTART PASS: practice → process exit → new race; new SDK session, roster and track, fresh VPS data, same SSH/collector transport',flush=True)
                pilot.close()
                await until(lambda:not pilot.worker.isRunning())
                assert viewer.worker.isRunning() and viewer.isVisible()
                for _ in range(100):
                    app.processEvents();await asyncio.sleep(.01)
                assert viewer.last_state['partner_connected'] is False
                viewer.close()
                await until(lambda:not viewer.worker.isRunning() and not pilot.isVisible() and not viewer.isVisible())
                print('IRACING E2E PASS: paired role credentials, automatic key beside app, actual SDK binary capture, both GUI roles, real OpenSSH, server calculation, invalid sensor frame rejected without reconnect, native cookie session, 64-car map source and centred standings, compact viewer, tyre temperatures, 76 capability cards, map, game-specific proximity, partner disconnect, clean shutdown',flush=True)
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
