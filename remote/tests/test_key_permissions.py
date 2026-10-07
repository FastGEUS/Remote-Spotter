"""Automatic key protection, session ordering, and Windows-only ACL regression."""
import asyncio
import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from remote.desktop import key_permissions as permissions
from remote.desktop.config import Profile
from remote.desktop.session import Session
from remote.desktop.tunnel import TunnelError


class KeyPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="Spotter's [key] & test ")
        self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.key=self.root/'lmu_spotter'
        self.key.write_bytes(b'-----BEGIN OPENSSH PRIVATE KEY-----\nTEST-ONLY-SECRET\n-----END OPENSSH PRIVATE KEY-----\n')
        self.original=self.key.read_bytes()

    async def test_non_windows_does_not_change_key_or_spawn_console(self):
        with patch.object(permissions,'IS_WINDOWS',False),patch.object(permissions.asyncio,'create_subprocess_exec') as spawn:
            self.assertFalse(await permissions.prepare_private_key(self.key))
            spawn.assert_not_called()
        self.assertEqual(self.key.read_bytes(),self.original)

    async def test_path_is_data_and_validated_result_is_required(self):
        calls=[];actual=asyncio.create_subprocess_exec
        async def spawn(*args,**kwargs):
            calls.append((args,dict(kwargs)))
            kwargs.pop('creationflags')
            return await actual(sys.executable,'-c','print("KEY_ACL_FIXED",end="")',**kwargs)
        with patch.object(permissions,'IS_WINDOWS',True),patch.object(permissions,'powershell_program',return_value='powershell.exe'),patch.object(permissions.asyncio,'create_subprocess_exec',side_effect=spawn):
            self.assertTrue(await permissions.prepare_private_key(self.key))
        args,kwargs=calls[0]
        self.assertIn('-NonInteractive',args);self.assertIn('Hidden',args)
        self.assertEqual(kwargs['creationflags'],0x08000000)
        self.assertEqual(kwargs['env'][permissions.KEY_PATH_ENV],str(self.key))
        script=base64.b64decode(args[-1]).decode('utf-16-le')
        self.assertEqual(script,permissions.REPAIR_SCRIPT)
        self.assertNotIn(str(self.key),script);self.assertNotIn('TEST-ONLY-SECRET',script)
        self.assertEqual(self.key.read_bytes(),self.original)

    async def test_public_key_or_unrelated_file_is_not_modified(self):
        self.key.write_text('ssh-ed25519 public-key-only')
        with patch.object(permissions,'IS_WINDOWS',True),patch.object(permissions.asyncio,'create_subprocess_exec') as spawn:
            with self.assertRaises(permissions.KeyPermissionError):await permissions.prepare_private_key(self.key)
            spawn.assert_not_called()
        self.assertEqual(self.key.read_text(),'ssh-ed25519 public-key-only')

    async def test_denied_acl_repair_gives_gui_error_and_preserves_file(self):
        actual=asyncio.create_subprocess_exec
        async def spawn(*args,**kwargs):
            kwargs.pop('creationflags')
            return await actual(sys.executable,'-c','import sys;sys.stderr.write("KEY_ACL_FAILED HRESULT=-1");sys.exit(1)',**kwargs)
        with patch.object(permissions,'IS_WINDOWS',True),patch.object(permissions,'powershell_program',return_value='powershell.exe'),patch.object(permissions.asyncio,'create_subprocess_exec',side_effect=spawn):
            with self.assertRaises(permissions.KeyPermissionError) as error:await permissions.prepare_private_key(self.key)
            self.assertNotIn('TEST-ONLY-SECRET',str(error.exception))
        self.assertEqual(self.key.read_bytes(),self.original)

    async def test_cancel_and_timeout_reap_hidden_process(self):
        actual=asyncio.create_subprocess_exec
        for cancel in (True,False):
            created=asyncio.Event();processes=[]
            async def spawn(*args,**kwargs):
                kwargs.pop('creationflags')
                process=await actual(sys.executable,'-c','import time;time.sleep(60)',**kwargs)
                processes.append(process);created.set();return process
            with patch.object(permissions,'IS_WINDOWS',True),patch.object(permissions,'powershell_program',return_value='powershell.exe'),patch.object(permissions,'REPAIR_TIMEOUT',5 if cancel else .05),patch.object(permissions.asyncio,'create_subprocess_exec',side_effect=spawn):
                task=asyncio.create_task(permissions.prepare_private_key(self.key))
                await created.wait()
                if cancel:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):await task
                else:
                    with self.assertRaises(permissions.KeyPermissionError):await task
            self.assertIsNotNone(processes[0].returncode)


class KeyPreparationSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_roles_prepare_before_ssh_and_stop_on_failure(self):
        for role in ('pilot','viewer'):
            events=[];instances=[]
            class FakeTunnel:
                def __init__(self,*args,port=None):self.port=port;self.started=False;self.stopped=False;instances.append(self)
                async def start(self):self.started=True
                async def stop(self):self.stopped=True
            with tempfile.TemporaryDirectory() as directory,patch('remote.desktop.session.prepare_private_key',new=AsyncMock(side_effect=permissions.KeyPermissionError('ACL unavailable'))) as prepare:
                session=Session(Profile(role,'p'*64,'chosen-key'),directory,events.append,tunnel_factory=FakeTunnel)
                await session.run()
            prepare.assert_awaited_once_with('chosen-key')
            self.assertFalse(instances[0].started);self.assertTrue(instances[0].stopped)
            self.assertEqual(session.state.phase,'error');self.assertEqual(events[-1]['code'],'key-permissions')

    async def test_network_retries_do_not_relaunch_permission_helper(self):
        order=[];attempts=[]
        async def prepare(path):order.append('prepare')
        class FakeTunnel:
            def __init__(self,*args,port=None):self.port=port;attempts.append(self)
            async def start(self):
                order.append('ssh')
                if len(attempts)==1:raise TunnelError('Network retry')
                raise TunnelError('Stop fixture','fixture',True)
            async def stop(self):pass
        # Shorten only the retry delay for this deterministic test.
        async def no_delay(delay):pass
        with tempfile.TemporaryDirectory() as directory,patch('remote.desktop.session.prepare_private_key',side_effect=prepare) as helper,patch('remote.desktop.session.asyncio.sleep',side_effect=no_delay):
            session=Session(Profile('pilot','p'*64,'chosen-key'),directory,lambda event:None,tunnel_factory=FakeTunnel)
            await session.run()
        self.assertEqual(order,['prepare','ssh','ssh']);helper.assert_awaited_once()


@unittest.skipUnless(os.name=='nt' and shutil.which('ssh-keygen'), 'Native Windows ACL round trip requires Windows/OpenSSH')
class WindowsKeyAclRoundTrip(unittest.IsolatedAsyncioTestCase):
    async def test_repair_overly_broad_acl_preserves_key_and_is_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="Spotter's [key] & test ") as temporary:
            key=Path(temporary)/'lmu_spotter'
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True,capture_output=True)
            original=key.read_bytes()
            # Give Everyone explicit read access to reproduce the user's error.
            subprocess.run(['icacls.exe',str(key),'/grant','*S-1-1-0:R'],check=True,capture_output=True)
            result=subprocess.run(['ssh-keygen','-y','-f',str(key)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertTrue(await permissions.prepare_private_key(key))
            self.assertEqual(key.read_bytes(),original)
            result=subprocess.run(['ssh-keygen','-y','-f',str(key)],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(await permissions.prepare_private_key(key))


if __name__=='__main__':unittest.main()
