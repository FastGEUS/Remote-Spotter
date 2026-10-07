import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from remote.desktop.config import Profile,save_profile,load_profile
from remote.desktop.state import State
from remote.desktop.tunnel import command,classify_error,Tunnel,TunnelError,prepare_hosts
from remote.desktop.session import Session,require_iracing_server


class DesktopConfigTests(unittest.TestCase):
    def test_legacy_partner_name_is_discarded_on_load_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            key=Path(directory)/'private';key.touch()
            path=save_profile(Profile('pilot','p'*32,str(key)),directory,protect=lambda raw:raw[::-1])
            value=json.loads(path.read_text());value['partner_name']='Private legacy name'
            path.write_text(json.dumps(value))
            profile=load_profile('pilot',directory,unprotect=lambda raw:raw[::-1])
            self.assertEqual(profile.partner_name,'')
            save_profile(profile,directory,protect=lambda raw:raw[::-1])
            self.assertNotIn('Private legacy name',path.read_text())

    def test_role_profile_uses_protected_token_and_rejects_wrong_role(self):
        with tempfile.TemporaryDirectory() as directory:
            key=Path(directory)/'private';key.touch()
            p=Profile('pilot','p'*32,str(key))
            path=save_profile(p,directory,protect=lambda raw:raw[::-1])
            self.assertNotIn('"token":',path.read_text())
            self.assertNotIn('p'*32,path.read_text())
            self.assertEqual(load_profile('pilot',directory,unprotect=lambda raw:raw[::-1]),p)
            value=path.read_text().replace('"pilot"','"viewer"');path.write_text(value)
            with self.assertRaises(ValueError):load_profile('pilot',directory,unprotect=lambda raw:raw[::-1])

    def test_host_and_public_key_validation(self):
        for host in ['-oProxyCommand=x','root@server','http://server','server;touch x']:
            with self.assertRaises(ValueError):Profile('pilot','p'*32,'/tmp/key',host=host).validate(False)
        with self.assertRaises(ValueError):Profile('pilot','p'*32,'/tmp/key.pub').validate(False)

    def test_owned_tunnel_auth_is_noninteractive_and_strict(self):
        args=command(Profile('pilot','p'*32,'C:/Users/Test User/key'),18082,'C:/Test User/known_hosts','empty',program='ssh')
        self.assertIn('StrictHostKeyChecking=yes',args);self.assertIn('BatchMode=yes',args)
        self.assertIn('127.0.0.1:18082:127.0.0.1:8080',args)
        self.assertIn('C:/Users/Test User/key',args)
        self.assertIn('UserKnownHostsFile="C:/Test User/known_hosts"',args)
        self.assertNotIn('p'*32,' '.join(args))

    def test_auth_and_changed_host_are_not_endless_network_retries(self):
        for raw,code in [('Permission denied (publickey)','key'),('Host key verification failed','host-trust'),('REMOTE HOST IDENTIFICATION HAS CHANGED','host-changed')]:
            error=classify_error(raw);self.assertEqual(error.code,code);self.assertTrue(error.permanent)
        self.assertFalse(classify_error('Connection timed out').permanent)

    def test_roles_do_not_rewrite_each_others_ssh_config(self):
        with tempfile.TemporaryDirectory() as directory:
            hosts,pilot=prepare_hosts(directory,'pilot')
            content=hosts.read_bytes();stamp=pilot.stat().st_mtime_ns
            viewer_hosts,viewer=prepare_hosts(directory,'viewer')
            prepare_hosts(directory,'pilot')
            self.assertNotEqual(pilot,viewer)
            self.assertEqual(hosts,viewer_hosts)
            self.assertEqual(hosts.read_bytes(),content)
            self.assertEqual(pilot.stat().st_mtime_ns,stamp)


class DesktopStateTests(unittest.TestCase):
    def test_partner_labels_and_events_never_expose_legacy_names(self):
        for role,label in [('pilot','Споттер'),('viewer','Пилот')]:
            for connected,expected in [(True,label),(False,label+' · офлайн'),(None,'—')]:
                state=State(role,partner_name='Private legacy name',partner_connected=connected)
                presentation=state.presentation()
                self.assertEqual(presentation['partner'],expected)
                self.assertNotIn('Private legacy name',json.dumps(presentation))

    def test_iracing_requires_capable_server_before_capture(self):
        require_iracing_server({'supportedGames':['lmu','iracing']})
        with self.assertRaises(TunnelError) as error:require_iracing_server({'version':'0.4.6'})
        self.assertTrue(error.exception.permanent)
        self.assertEqual(error.exception.code,'server-version')

    def test_waiting_garage_stale_and_partner_presence_are_separate(self):
        s=State('pilot',phase='online',game='garage',partner_name='Споттер')
        value={'sourceConnected':True,'viewersConnected':0,'sourceAgeMs':40,'ingestAgeMs':10,'computeMs':2,'gameStatus':'garage'}
        s.apply_server(value)
        self.assertEqual(s.presentation()['title'],'Вы онлайн')
        self.assertEqual(s.presentation()['game_caption'],'В гараже')
        self.assertIn('офлайн',s.presentation()['partner'])
        s.game='live';s.apply_server({**value,'viewersConnected':1,'sourceAgeMs':2000})
        self.assertEqual(s.presentation()['game_caption'],'Нет свежих данных')
        self.assertEqual(s.presentation()['partner'],'Споттер')


class DesktopLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_stop_and_cancel_wait_for_one_cleanup(self):
        started=asyncio.Event()
        class Process:
            pid=0;returncode=None;terminations=0
            def terminate(self):self.terminations+=1
            async def wait(self):
                started.set();await asyncio.sleep(.05);self.returncode=0
        tunnel=Tunnel(Profile('pilot','p'*32,'key'),'.')
        process=Process();tunnel.process=process
        # A pipe reader that never produces EOF must still be closed.
        reader=asyncio.create_task(asyncio.Event().wait());tunnel._reader=reader
        first=asyncio.create_task(tunnel.stop());await started.wait()
        first.cancel();second=asyncio.create_task(tunnel.stop())
        with self.assertRaises(asyncio.CancelledError):await first
        await second
        self.assertEqual(process.terminations,1)
        self.assertIsNone(tunnel.process);self.assertTrue(reader.cancelled())

    async def test_permanent_failure_stops_and_keeps_error(self):
        events=[];created=[]
        class Fake:
            def __init__(self,*args,port=None):self.port=port;self.stopped=False;created.append(self)
            async def start(self):raise TunnelError('Bad key','key',True)
            async def stop(self):self.stopped=True
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Profile('pilot','p'*32,'key'),directory,events.append,tunnel_factory=Fake)
            await s.run()
        self.assertEqual(len(created),1);self.assertTrue(created[0].stopped)
        self.assertEqual(s.state.phase,'error');self.assertEqual(events[-1]['code'],'key')

    async def test_cancellation_closes_owned_tunnel(self):
        started=asyncio.Event();instances=[]
        class Fake:
            def __init__(self,*args,port=None):self.port=port;self.stopped=False;instances.append(self)
            async def start(self):started.set();await asyncio.Event().wait()
            async def stop(self):self.stopped=True
        with tempfile.TemporaryDirectory() as directory:
            s=Session(Profile('pilot','p'*32,'key'),directory,lambda e:None,tunnel_factory=Fake)
            task=asyncio.create_task(s.run());await started.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(instances[0].stopped)
        self.assertEqual(s.state.phase,'offline')

    async def test_cancelled_process_is_reaped(self):
        import sys
        tunnel=Tunnel(Profile('pilot','p'*32,'key'),'.')
        tunnel.process=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(30)',stderr=asyncio.subprocess.PIPE)
        process=tunnel.process;tunnel._reader=asyncio.create_task(tunnel._read_errors())
        await tunnel.stop()
        self.assertIsNotNone(process.returncode);self.assertIsNone(tunnel.process)
