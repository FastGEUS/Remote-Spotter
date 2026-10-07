"""Qt smoke and actual embedded panel authentication. Linux offscreen check."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

from PySide6.QtCore import QUrl,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication
from remote.desktop.gui import STYLE,PilotWindow
from remote.desktop.viewer import ViewerWindow
from remote.desktop.config import Profile
from remote.desktop.state import State
from remote.desktop.tunnel import free_port,http_json
from remote.upstream import ROOT

def main(binary,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True)
    port=free_port();token=secrets.token_urlsafe(32);pilot_token=secrets.token_urlsafe(32)
    env={**os.environ,'SPOTTER_ROOT':str(ROOT),'SPOTTER_PYTHON':sys.executable,'SPOTTER_ADDR':f'127.0.0.1:{port}',
         'SPOTTER_PILOT_TOKEN':pilot_token,'SPOTTER_VIEW_TOKEN':token}
    server=subprocess.Popen([binary],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setStyleSheet(STYLE)
    def until(check,timeout=20):
        deadline=time.monotonic()+timeout
        while not check():
            if time.monotonic()>deadline:raise AssertionError('Qt condition timed out')
            app.processEvents();time.sleep(.01)
    pilot=None;viewer=None;collector=None
    try:
        for _ in range(100):
            try:http_json(f'http://127.0.0.1:{port}/healthz');break
            except OSError:time.sleep(.05)
        with tempfile.TemporaryDirectory() as temporary:
            pilot=PilotWindow(Profile('pilot',pilot_token,'unused',partner_name='Legacy partner'),directory=temporary)
            pilot.show();app.processEvents();pilot.grab().save(str(directory/'pilot-offline.png'))
            for phase,game,fresh,partner in [('online','garage',True,True),('online','live',False,True),('reconnecting','live',False,None),('online','waitingForGame',True,False)]:
                state=State('pilot',phase=phase,game=game,data_fresh=fresh,partner_connected=partner,partner_name='Legacy partner').presentation()
                pilot.show_state(state);app.processEvents()
                assert pilot.connect_button.isEnabled()==state['can_connect']
                assert pilot.title.text()==state['title']
            pilot.show_state(State('pilot',phase='online',game='live',data_fresh=True,partner_connected=True,partner_name='Legacy partner').presentation())
            app.processEvents();pilot.grab().save(str(directory/'pilot-online.png'))
            viewer=ViewerWindow(Profile('viewer',token,'unused',partner_name='Legacy partner'),directory=temporary)
            viewer.show()
            _,cookie=http_json(f'http://127.0.0.1:{port}/api/session',body={'token':token})
            viewer.viewer_session({'origin':f'http://127.0.0.1:{port}','cookie':cookie})
            try:until(lambda:viewer.stack.currentWidget()==viewer.web)
            except AssertionError:
                print('Cookie pending:',viewer.pending_cookie is not None,'Loaded origin:',viewer.loaded_origin,'Page:',viewer.web.url().toString(),'Banner:',viewer.banner.text())
                raise
            def javascript(script):
                result=[];viewer.page.runJavaScript(script,result.append);until(lambda:bool(result));return result[0]
            until(lambda:javascript("document.getElementById('login').hidden"))
            assert 'spotter_session' not in javascript('document.cookie')
            collector_env={**os.environ,'SPOTTER_PILOT_TOKEN':pilot_token}
            collector=subprocess.Popen([sys.executable,'-m','remote.collector','--demo','--allow-insecure-local','--url',f'ws://127.0.0.1:{port}/ws/pilot'],cwd=ROOT,env=collector_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            until(lambda:javascript("document.getElementById('standings').children.length") == 12)
            until(lambda:javascript("document.querySelectorAll('[data-overlay]').length") == 76)
            until(lambda:javascript("document.getElementById('connection').textContent")=='В эфире')
            viewer.show_state(State('viewer',phase='online',game='live',data_fresh=True,partner_connected=True,partner_name='Legacy partner').presentation())
            for _ in range(50):app.processEvents();time.sleep(.02)
            app.processEvents();viewer.grab().save(str(directory/'viewer-online.png'))
            viewer.navigate('overlays');until(lambda:javascript("document.getElementById('advanced-panels').open"))
            viewer.viewer_session({'origin':f'http://127.0.0.1:{port}','cookie':cookie})
            until(lambda:viewer.pending_cookie is None)
            assert javascript("document.getElementById('advanced-panels').open")
            print('QT GUI PASS: compact states, cookie bridge/HttpOnly, real WebSocket panel, 76 overlays, navigation and session renewal',flush=True)
            viewer.close();pilot.close();app.processEvents()
    finally:
        if collector:
            collector.terminate();collector.wait(timeout=5)
        if viewer:viewer.close()
        if pilot:pilot.close()
        if viewer:viewer.deleteLater()
        if pilot:pilot.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        server.terminate();server.wait(timeout=5)

if __name__=='__main__':main(str(Path(sys.argv[1]).resolve()),sys.argv[2])
