"""Host trust bootstrap using real OpenSSH client, without client authentication."""
import asyncio
import base64
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from remote.desktop.config import Profile
from remote.desktop import tunnel
from remote.desktop.lifecycle import own as own_process


class HostProbeValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile('pilot','p'*64,'do-not-open-this-private-key',host='127.0.0.1',ssh_port=22022)
        blob=b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'+bytes(range(32))
        self.key=base64.b64encode(blob).decode()
        self.line=f'[127.0.0.1]:22022 ssh-ed25519 {self.key}'

    def test_credential_free_probe_is_separate_from_strict_tunnel(self):
        args=tunnel.host_probe_command(self.profile,'C:/Test User/probe','empty',program='ssh')
        for value in ('PreferredAuthentications=none','IdentityAgent=none','IdentityFile=none',
                      'ClearAllForwardings=yes','StrictHostKeyChecking=accept-new',
                      'UserKnownHostsFile="C:/Test User/probe"'):
            self.assertIn(value,args)
        self.assertNotIn(self.profile.ssh_key,args);self.assertNotIn(self.profile.token,' '.join(args))
        real=tunnel.command(self.profile,18082,'trusted','empty',program='ssh')
        self.assertIn('StrictHostKeyChecking=yes',real)
        self.assertNotIn('StrictHostKeyChecking=accept-new',real)

    def test_wrong_endpoint_key_type_and_incomplete_keys_are_rejected(self):
        for invalid in ('',self.line.replace('22022','22023'),self.line.replace('ssh-ed25519 ','ssh-rsa '),
                        self.line.replace(self.key,'AAAA'),self.line+'\n'+self.line.replace(self.key,self.key[:-4]+'AAAA')):
            with self.subTest(invalid=invalid):
                with self.assertRaises(tunnel.TunnelError):tunnel.parse_host_key(invalid,self.profile)
        line,fingerprint=tunnel.parse_host_key('# comment\n'+self.line+'\n',self.profile)
        self.assertEqual(line,self.line);self.assertTrue(fingerprint.startswith('SHA256:'))

    def test_kex_failure_is_not_reported_as_vpn_or_missing_private_key(self):
        error=tunnel.host_probe_error('choose_kex: unsupported KEX method sntrup761x25519-sha512@openssh.com',self.profile)
        self.assertEqual(error.code,'ssh-version');self.assertTrue(error.permanent)
        self.assertIn('OpenSSH',str(error));self.assertNotIn('VPN',str(error))
        self.assertIn('порт',str(tunnel.host_probe_error('Connection refused',self.profile)))


@unittest.skipUnless(importlib.util.find_spec('asyncssh') and shutil.which('ssh') and shutil.which('ssh-keygen'),
                     'Real OpenSSH client fixture requires asyncssh and ssh-keygen')
class OpenSSHHostProbeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncssh
        self.temporary=tempfile.TemporaryDirectory(prefix='Spotter probe test ')
        self.root=Path(self.temporary.name);self.addCleanup(self.temporary.cleanup)
        private=asyncssh.generate_private_key('ssh-ed25519')
        self.host_key=asyncssh.generate_private_key('ssh-ed25519')
        (self.root/'host_key.pub').write_bytes(self.host_key.export_public_key())
        (self.root/'client_key').write_bytes(private.export_private_key('openssh'))
        (self.root/'client_key').chmod(0o600)
        (self.root/'client_key.pub').write_bytes(private.export_public_key())
        self.auth_keys=[]
        fixture=self
        class Peer(asyncssh.SSHServer):
            def begin_auth(self,username):return True
            def public_key_auth_supported(self):return True
            def validate_public_key(self,username,key):
                fixture.auth_keys.append(key)
                return username=='fixture' and key.export_public_key()==private.export_public_key()
            def connection_requested(self,host,port,*args):
                return host=='127.0.0.1' and port==fixture.profile.server_port
        self.server=await asyncssh.create_server(Peer,'127.0.0.1',0,server_host_keys=[self.host_key])
        self.port=self.server.get_port()
        self.profile=Profile('pilot','p'*64,str(self.root/'client_key'),host='127.0.0.1',user='fixture',ssh_port=self.port)

    async def asyncTearDown(self):
        self.server.close();await self.server.wait_closed()

    async def test_probe_then_user_trust_then_real_authenticated_tunnel(self):
        app=self.root/'App trust';app.mkdir();trusted=app/'known_hosts';trusted.touch()
        original=trusted.read_bytes()
        # A missing keyscan must have no effect on this path.
        with patch.object(tunnel,'ssh_program',return_value=shutil.which('ssh')):
            line,fingerprint=await tunnel.scan_host(self.profile)
        public=(self.root/'host_key.pub').read_text().split()
        self.assertEqual(line,f'[127.0.0.1]:{self.port} {public[0]} {public[1]}')
        expected=subprocess.run(['ssh-keygen','-lf',str(self.root/'host_key.pub'),'-E','sha256'],
                                check=True,capture_output=True,text=True).stdout.split()[1]
        self.assertEqual(fingerprint,expected)
        self.assertEqual(trusted.read_bytes(),original)
        self.assertEqual(self.auth_keys,[])

        connection=tunnel.Tunnel(self.profile,app)
        try:
            with self.assertRaises(tunnel.TunnelError) as error:await connection.start()
            self.assertEqual(error.exception.code,'host-trust')
        finally:await connection.stop()
        self.assertEqual(trusted.read_bytes(),original)

        # This append models the existing GUI's explicit Yes after fingerprint review.
        trusted.write_text(line+'\n')
        async def health(reader,writer):
            try:
                await reader.readuntil(b'\r\n\r\n')
                body=b'{"status":"ok","scope":"relay-only"}'
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
                await writer.drain()
            finally:
                writer.close();await writer.wait_closed()
        server=await asyncio.start_server(health,'127.0.0.1',0)
        self.profile.server_port=server.sockets[0].getsockname()[1]
        connection=tunnel.Tunnel(self.profile,app)
        try:
            await connection.start()
            self.assertTrue(self.auth_keys)
        finally:
            await connection.stop();server.close();await server.wait_closed()

        # Existing trust must not be overwritten when the server key disagrees.
        wrong=(self.root/'client_key.pub').read_text().split()
        trusted.write_text(f'[127.0.0.1]:{self.port} {wrong[0]} {wrong[1]}\n')
        previous=trusted.read_bytes();connection=tunnel.Tunnel(self.profile,app)
        try:
            with self.assertRaises(tunnel.TunnelError) as error:await connection.start()
            self.assertEqual(error.exception.code,'host-changed')
            self.assertEqual(trusted.read_bytes(),previous)
        finally:await connection.stop()

    async def test_cancel_during_handshake_reaps_probe_child(self):
        connected=asyncio.Event();finish=asyncio.Event();processes=[]
        async def stalled(reader,writer):
            try:
                await reader.readline();connected.set();await finish.wait()
            finally:writer.close();await writer.wait_closed()
        server=await asyncio.start_server(stalled,'127.0.0.1',0)
        self.profile.ssh_port=server.sockets[0].getsockname()[1]
        def track(process):processes.append(process);own_process(process)
        try:
            with patch.object(tunnel,'own',side_effect=track):
                task=asyncio.create_task(tunnel.scan_host(self.profile))
                await asyncio.wait_for(connected.wait(),3)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            self.assertEqual(len(processes),1);self.assertIsNotNone(processes[0].returncode)
        finally:
            finish.set();server.close();await server.wait_closed()

    async def test_closed_port_reports_connection_refusal(self):
        self.profile.ssh_port=tunnel.free_port()
        with self.assertRaises(tunnel.TunnelError) as error:await tunnel.scan_host(self.profile)
        self.assertIn('отклонил',str(error.exception))


if __name__=='__main__':unittest.main()
