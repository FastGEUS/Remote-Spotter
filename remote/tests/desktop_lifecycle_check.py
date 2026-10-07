"""Exercise real entrypoints in separate processes, not pre-imported windows.

Test-only substitutes avoid Windows DPAPI/VPS credentials on the Linux runner.
The actual QApplication, role locks, browser, close path and entrypoints run.
"""
import asyncio
import json
import contextlib
import os
from pathlib import Path
import runpy
import subprocess
import socket
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]


def child(role, mode, directory):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox, QDialog
    from remote.desktop import gui
    from remote.desktop.config import Profile
    from remote.desktop.lifecycle import own, release
    directory=Path(directory)
    profile=Profile(role,'test-token-not-a-real-credential','unused')
    gui.data_dir=lambda:directory
    if mode=='pair':
        from remote.desktop import config
        app_dir=directory/'App with spaces';app_dir.mkdir(exist_ok=True)
        (app_dir/'lmu_spotter').touch()
        presets=directory/'pair-presets';presets.mkdir(exist_ok=True)
        (presets/(role+'.json')).write_text(json.dumps({'schemaVersion':1,'role':role,'token':role[0]*64,'ssh_key':'unused'}))
        config.preset_path=lambda role:presets/(role+'.json')
        config.application_dir=lambda:app_dir
        config.dpapi=lambda value,decrypt=False:value[::-1]
        gui.save_profile=lambda value,folder:config.save_profile(value,folder,protect=lambda raw:raw[::-1])
        class ForbiddenSetup:
            def __init__(self,*args,**kwargs):raise AssertionError('Pair build must never ask for tokens')
        gui.Setup=ForbiddenSetup
    else:gui.load_startup_profile=lambda role,directory:(None if mode=='setup' else profile,False)
    gui.QMessageBox.information=lambda *args: (directory/(role+'-duplicate')).touch()
    if mode=='setup':
        class Setup(QDialog):
            def __init__(self,role):
                super().__init__();self.profile=profile
                QTimer.singleShot(20,self.accept)
        gui.Setup=Setup

    class TestSession:
        def __init__(self,*args,**kwargs):
            if mode=='pair':
                actual=args[0];assert actual.token==role[0]*64
                assert actual.ssh_key==str((directory/'App with spaces/lmu_spotter').resolve())
        async def run(self):
            from remote.desktop.tunnel import free_port
            port=free_port()
            code=f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(4); time.sleep(60)"
            process=await asyncio.create_subprocess_exec(sys.executable,'-c',code,
                stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            own(process)
            for _ in range(200):
                try:
                    reader,writer=await asyncio.open_connection('127.0.0.1',port)
                    writer.close();await writer.wait_closed();break
                except OSError:await asyncio.sleep(.01)
            ready=directory/(role+'-child.tmp');ready.write_text(str(port))
            ready.replace(directory/(role+'-child'))
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if mode=='stuck':await asyncio.Event().wait()
                # A repeated cancel must not interrupt this real cleanup.
                await asyncio.sleep(.25)
            finally:
                process.kill();await process.wait();release(process)
                (directory/(role+'-cleanup')).touch()
    gui.Session=TestSession
    async def scan(profile):
        try:await asyncio.Event().wait()
        finally:(directory/(role+'-scan-cleanup')).touch()
    gui.scan_host=scan
    original=gui.ConnectionWindow.__init__
    def initialize(window,*args,**kwargs):
        original(window,*args,**kwargs)
        if mode=='gui-stuck':
            def blocked_close():time.sleep(20)
            window.begin_shutdown=blocked_close
        def tick():
            if window.isVisible() and not window.closing:
                if role=='viewer' and not hasattr(window,'test_web_ready'):
                    # Exercise closing a visible document, not just the native
                    # waiting page, while real child cleanup remains pending.
                    window.page.setHtml('<body style="background:white">Dashboard</body>')
                    window.stack.setCurrentWidget(window.web)
                    window.test_web_ready=True
                (directory/(role+'-visible')).touch()
            if not window.worker and mode!='setup':window.connect_session()
            if mode=='scan' and not window.scan:
                window.scan=gui.HostScan(profile,window);window.scan.start()
            if (directory/('close-'+role)).exists():
                window.close()
                if role=='viewer':
                    assert not window.isVisible(),'Closing viewer must disappear before worker cleanup'
                    assert window.stack.currentWidget()!=window.web,'Browser must be hidden before unloading'
                    assert window.page.backgroundColor().name()=='#111315'
                    if window.worker and window.worker.isRunning():
                        (directory/'viewer-hidden-during-cleanup').touch()
        timer=QTimer(window);timer.setInterval(30);timer.timeout.connect(tick);timer.start()
        window.test_timer=timer
    gui.ConnectionWindow.__init__=initialize
    assert 'PySide6.QtWebEngineWidgets' not in sys.modules
    runpy.run_module('remote.desktop.'+role+'_entry',run_name='__main__')


def wait_for(check, timeout=25):
    deadline=time.monotonic()+timeout
    while not check():
        if time.monotonic()>deadline:raise AssertionError('Entrypoint condition timed out')
        time.sleep(.03)


def running(port):
    # /proc may expose host PIDs while child.pid is namespace-local. A live
    # socket is unambiguous and also proves a leaked child no longer owns ports.
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=.1):return True
    except OSError:return False


def main():
    processes=[]
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary)
        def start(role,mode='active'):
            process=subprocess.Popen([sys.executable,'-m','remote.tests.desktop_lifecycle_check','--child',role,mode,str(directory)],
                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            processes.append(process);return process
        def done(process,timeout=12):
            out,err=process.communicate(timeout=timeout)
            assert process.returncode==0,(process.returncode,out.decode(),err.decode())
        try:
            # A hidden/background role must not block the other role.
            pilot=start('pilot','scan');viewer=start('viewer')
            wait_for(lambda:all((directory/(r+'-visible')).exists() and (directory/(r+'-child')).exists() for r in ('pilot','viewer')))
            assert pilot.poll() is None and viewer.poll() is None
            duplicate=start('pilot');done(duplicate)
            assert (directory/'pilot-duplicate').exists()
            children=[int((directory/(r+'-child')).read_text()) for r in ('pilot','viewer')]
            for role in ('pilot','viewer'):(directory/('close-'+role)).touch()
            done(pilot);done(viewer)
            assert (directory/'viewer-hidden-during-cleanup').exists()
            assert all((directory/(r+'-cleanup')).exists() for r in ('pilot','viewer'))
            assert (directory/'pilot-scan-cleanup').exists()
            assert not any(running(pid) for pid in children)
            assert not any((directory/(r+'.lock')).exists() for r in ('pilot','viewer'))
            # Relaunch immediately after close, including first-run modal setup.
            for role in ('pilot','viewer'):
                for suffix in ('-visible','-child'):(directory/(role+suffix)).unlink()
                (directory/('close-'+role)).unlink()
                process=start(role,'setup')
                wait_for(lambda:(directory/(role+'-visible')).exists())
                assert process.poll() is None
                (directory/('close-'+role)).touch();done(process)
            # A stuck native/network task still has a bounded process lifetime.
            for mode in ('stuck','gui-stuck'):
                (directory/'close-pilot').unlink();(directory/'pilot-visible').unlink()
                (directory/'pilot-child').unlink(missing_ok=True)
                process=start('pilot',mode)
                wait_for(lambda:(directory/'pilot-visible').exists() and (directory/'pilot-child').exists())
                pid=int((directory/'pilot-child').read_text())
                start_time=time.monotonic();(directory/'close-pilot').touch();done(process,10)
                assert time.monotonic()-start_time<9
                wait_for(lambda:not running(pid),3)
                assert not (directory/'pilot.lock').exists()
            (directory/'close-pilot').unlink();(directory/'pilot-visible').unlink()
            process=start('pilot','setup');wait_for(lambda:(directory/'pilot-visible').exists())
            (directory/'close-pilot').touch();done(process)
            for role in ('pilot','viewer'):
                (directory/('close-'+role)).unlink();(directory/(role+'-visible')).unlink()
                process=start(role,'pair');wait_for(lambda:(directory/(role+'-visible')).exists())
                assert (directory/(role+'.json')).exists()
                assert role[0]*64 not in (directory/(role+'.json')).read_text()
                (directory/('close-'+role)).touch();done(process)
            print('DESKTOP LIFECYCLE PASS: viewer hides visible web document before child cleanup, dark browser background, real entrypoints visible, both roles concurrent, role duplicate guard, repeated close, scan cancel, immediate relaunch, setup modal, paired startup without token form, protected local profile, stuck-worker and blocked-GUI deadlines, owned child cleanup')
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.communicate()


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child':child(*sys.argv[2:])
    else:main()
