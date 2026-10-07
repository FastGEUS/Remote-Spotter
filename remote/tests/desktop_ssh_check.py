"""Optional integration test: actual OpenSSH client and local AsyncSSH peer.

pip install asyncssh==2.21.1 (test environment only).
"""
import asyncio
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import asyncssh

from remote.desktop.config import Profile
from remote.desktop.tunnel import Tunnel,TunnelError,free_port,http_json
from remote.upstream import ROOT

async def main(binary):
    server_port=free_port();token=secrets.token_urlsafe(32);viewer_token=secrets.token_urlsafe(32)
    env={**os.environ,'SPOTTER_ROOT':str(ROOT),'SPOTTER_PYTHON':sys.executable,
         'SPOTTER_ADDR':f'127.0.0.1:{server_port}','SPOTTER_PILOT_TOKEN':token,
         'SPOTTER_VIEW_TOKEN':viewer_token}
    relay=subprocess.Popen([binary],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    server=None;tunnel=None;viewer=None
    private=asyncssh.generate_private_key('ssh-ed25519');host_key=asyncssh.generate_private_key('ssh-ed25519')
    class Peer(asyncssh.SSHServer):
        def begin_auth(self,username):return True
        def public_key_auth_supported(self):return True
        def validate_public_key(self,username,key):return username=='spotter-test' and key.export_public_key()==private.export_public_key()
        def connection_requested(self,host,port,*args):return host=='127.0.0.1' and port==server_port
    try:
        for _ in range(100):
            try:await asyncio.to_thread(http_json,f'http://127.0.0.1:{server_port}/healthz');break
            except OSError:await asyncio.sleep(.05)
        server=await asyncssh.create_server(Peer,'127.0.0.1',0,server_host_keys=[host_key])
        port=server.get_port()
        with tempfile.TemporaryDirectory(prefix='Remote Spotter test ') as directory:
            folder=Path(directory);key_file=folder/'private key'
            key_file.write_bytes(private.export_private_key('openssh'));key_file.chmod(0o600)
            hosts=folder/'known_hosts'
            hosts.write_text(f'[127.0.0.1]:{port} '+host_key.export_public_key().decode())
            profile=Profile('pilot',token,str(key_file),host='127.0.0.1',user='spotter-test',ssh_port=port,server_port=server_port)
            tunnel=Tunnel(profile,folder)
            viewer_profile=Profile('viewer',viewer_token,str(key_file),host='127.0.0.1',user='spotter-test',ssh_port=port,server_port=server_port)
            viewer=Tunnel(viewer_profile,folder)
            await asyncio.gather(tunnel.start(),viewer.start())
            status,_=await asyncio.to_thread(http_json,tunnel.origin+'/api/status',token=token)
            assert status['version']=='0.4.7';process=tunnel.process
            await tunnel.stop();assert process.returncode is not None
            assert viewer.process.returncode is None
            health,_=await asyncio.to_thread(http_json,viewer.origin+'/healthz')
            assert health['status']=='ok'
            # Wrong known_hosts must fail permanently and never be overwritten.
            wrong=asyncssh.generate_private_key('ssh-ed25519')
            bad_entry=f'[127.0.0.1]:{port} '+wrong.export_public_key().decode()
            hosts.write_text(bad_entry)
            tunnel=Tunnel(profile,folder)
            try:
                await tunnel.start();raise AssertionError('Changed host key accepted')
            except TunnelError as exc:assert exc.code=='host-changed' and exc.permanent
            finally:await tunnel.stop()
            assert hosts.read_text()==bad_entry
            await viewer.stop()
            print('OPENSSH PASS: both roles concurrent, closing pilot preserves viewer, real public-key login and forwarding, paths with spaces, status, owned-process cleanup, changed host rejected')
    finally:
        if tunnel:await tunnel.stop()
        if viewer:await viewer.stop()
        if server:server.close();await server.wait_closed()
        relay.terminate();relay.wait(timeout=5)

if __name__=='__main__':asyncio.run(main(str(Path(sys.argv[1]).resolve())))
