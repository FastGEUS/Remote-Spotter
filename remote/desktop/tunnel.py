"""Owned OpenSSH process. Never borrows/kills an existing user tunnel."""
import asyncio
import contextlib
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlsplit
from .lifecycle import own, release


class TunnelError(RuntimeError):
    def __init__(self, message, code='network', permanent=False):
        super().__init__(message)
        self.code, self.permanent = code, permanent


def ssh_program():
    if os.name == 'nt':
        for directory in ('Sysnative', 'System32'):
            path = Path(os.environ.get('SystemRoot', r'C:\Windows')) / directory / 'OpenSSH/ssh.exe'
            if path.is_file():
                return str(path)
    found = shutil.which('ssh')
    if found:
        return found
    raise TunnelError('Не найден OpenSSH Client Windows. Включите компонент «Клиент OpenSSH».', 'ssh-missing', True)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def classify_error(raw):
    text = raw.lower()
    if 'remote host identification has changed' in text:
        return TunnelError('Ключ VPS изменился. Проверьте сервер; прежнее доверие сохранено.', 'host-changed', True)
    if 'host key verification failed' in text or 'no ' in text and 'host key is known' in text:
        return TunnelError('Нужно подтвердить SSH-ключ этого VPS.', 'host-trust', True)
    if any(word in text for word in ('permission denied', 'load key', 'bad permissions', 'unprotected private key')):
        return TunnelError('SSH не принял ключ. Проверьте выбранный файл и доступ к серверу. Для ключа с паролем нужен ssh-agent.', 'key', True)
    if 'address already in use' in text or 'cannot listen to port' in text:
        return TunnelError('Локальный порт занят; выбираем другой.', 'port')
    return TunnelError('Нет связи с VPS. Повторяем подключение автоматически.')


def command(profile, port, known_hosts, empty_config, program=None):
    # OpenSSH parses -o using its config grammar; spaces inside a path need
    # quotes in that grammar as well as ordinary argv escaping by subprocess.
    hosts_path = str(known_hosts).replace('\\', '/')
    return [program or ssh_program(), '-F', str(empty_config), '-N', '-T',
            '-p', str(profile.ssh_port), '-i', profile.ssh_key,
            '-L', f'127.0.0.1:{port}:127.0.0.1:{profile.server_port}',
            '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no',
            '-o', 'KbdInteractiveAuthentication=no', '-o', 'IdentitiesOnly=yes',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=5',
            '-o', 'ServerAliveCountMax=3', '-o', 'ConnectTimeout=8',
            '-o', 'ConnectionAttempts=1', '-o', 'StrictHostKeyChecking=yes',
            '-o', f'UserKnownHostsFile="{hosts_path}"', '-o', 'LogLevel=DEBUG1',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none', f'{profile.user}@{profile.host}']


def prepare_hosts(directory, role=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'known_hosts'
    if not target.exists():
        trusted = Path.home() / '.ssh/known_hosts'
        try:
            with target.open('xb') as file:
                file.write(trusted.read_bytes() if trusted.is_file() else b'')
        except FileExistsError:
            pass
    target.chmod(0o600)
    empty = directory / ('ssh_config-' + role if role else 'ssh_config')
    try:
        with empty.open('x') as file:
            file.write('# Remote Spotter owns its connection parameters.\n')
    except FileExistsError:
        pass
    return target, empty


def http_json(url, *, token=None, cookie=None, body=None):
    # Loopback requests do not use environment HTTP proxies.
    parts = urlsplit(url)
    headers = {'Origin': f'{parts.scheme}://{parts.netloc}', 'Cache-Control': 'no-store'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if cookie:
        headers['Cookie'] = cookie
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=2) as response:
        data = response.read(65537)
        if len(data) > 65536:
            raise TunnelError('Сервер прислал слишком большой ответ')
        return (json.loads(data) if data else None), response.headers.get('Set-Cookie')


class Tunnel:
    def __init__(self, profile, directory, port=None):
        self.profile, self.directory = profile, Path(directory)
        self.port = port or free_port()
        self.process = None
        self._reader = None
        self._stop_task = None
        self._stderr = ''
        self._forward_ready = asyncio.Event()

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.port}'

    async def _read_errors(self):
        process = self.process
        while chunk := await process.stderr.read(1024):
            self._stderr = (self._stderr + chunk.decode(errors='replace'))[-8192:]
            if f'Local forwarding listening on 127.0.0.1 port {self.port}.' in self._stderr:
                self._forward_ready.set()

    async def start(self):
        try:
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1', self.port))
        except OSError:
            raise TunnelError('Локальный порт занят; выбираем другой.', 'port') from None
        hosts, config = prepare_hosts(self.directory, self.profile.role)
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        self._stderr = ''
        self._forward_ready.clear()
        self.process = await asyncio.create_subprocess_exec(*command(self.profile, self.port, hosts, config),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE, **kwargs)
        own(self.process)
        self._reader = asyncio.create_task(self._read_errors())
        deadline = asyncio.get_running_loop().time() + 14
        while asyncio.get_running_loop().time() < deadline:
            if self.process.returncode is not None:
                await self._reader
            self.check()
            if not self._forward_ready.is_set():
                await asyncio.sleep(.1)
                continue
            try:
                value, _ = await asyncio.to_thread(http_json, self.origin + '/healthz')
                if value == {'status': 'ok', 'scope': 'relay-only'}:
                    # Our SSH process confirmed binding the forwarding socket.
                    # A raced/occupied port is never borrowed from another app.
                    await asyncio.sleep(.15)
                    self.check()
                    return
            except (OSError, ValueError):
                pass
            await asyncio.sleep(.25)
        raise TunnelError('SSH открыт, но служба spotter на VPS не отвечает. Повторяем подключение.')

    def check(self):
        if self.process and self.process.returncode is not None:
            raise classify_error(self._stderr)

    async def stop(self):
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._stop())
        try:
            await asyncio.shield(self._stop_task)
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_task)
            raise

    async def _stop(self):
        process, reader = self.process, self._reader
        if process:
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 3)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):process.kill()
                    await asyncio.wait_for(process.wait(), 1)
            release(process)
            if reader:
                # A stderr pipe must not keep the desktop alive after SSH exits.
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):await reader
            self.process = self._reader = None


def host_probe_command(profile, known_hosts, empty_config, program=None):
    """Fetch an untrusted host key without offering any client credentials.

    Windows ssh-keyscan 9.2 can advertise an unsupported sntrup KEX. The
    regular ssh client filters its supported algorithms correctly (#2140).
    accept-new applies ONLY to this disposable probe file, never to the
    app/user trust stores. GUI confirmation precedes the real strict tunnel.
    """
    hosts_path = str(known_hosts).replace('\\', '/')
    return [program or ssh_program(), '-F', str(empty_config), '-N', '-T',
            '-p', str(profile.ssh_port),
            '-o', 'BatchMode=yes', '-o', 'PreferredAuthentications=none',
            '-o', 'PubkeyAuthentication=no', '-o', 'PasswordAuthentication=no',
            '-o', 'KbdInteractiveAuthentication=no', '-o', 'IdentityAgent=none',
            '-o', 'IdentityFile=none', '-o', 'ClearAllForwardings=yes',
            '-o', 'StrictHostKeyChecking=accept-new', '-o', 'HostKeyAlgorithms=ssh-ed25519',
            '-o', f'UserKnownHostsFile="{hosts_path}"', '-o', 'GlobalKnownHostsFile=none',
            '-o', 'HashKnownHosts=no', '-o', 'CheckHostIP=no', '-o', 'UpdateHostKeys=no',
            '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'LogLevel=ERROR', f'{profile.user}@{profile.host}']


def parse_host_key(raw, profile):
    """Validate one complete Ed25519 wire-format key for this exact endpoint."""
    lines = sorted(set(line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')))
    target = profile.host.lower() if profile.ssh_port == 22 else f'[{profile.host.lower()}]:{profile.ssh_port}'
    try:
        if len(lines) != 1:raise ValueError('Ambiguous host key')
        parts = lines[0].split()
        if len(parts) != 3 or parts[0].lower() != target or parts[1] != 'ssh-ed25519':
            raise ValueError('Wrong endpoint or key type')
        blob = base64.b64decode(parts[2], validate=True)
        if len(blob) != 51 or blob[:19] != b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20':
            raise ValueError('Malformed Ed25519 key')
    except (ValueError, IndexError) as exc:
        raise TunnelError('OpenSSH не вернул корректный SSH-ключ ED25519 этого VPS.', 'host-scan', True) from exc
    fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')
    return ' '.join(parts), fingerprint


def host_probe_error(raw, profile):
    text = raw.lower()
    if any(value in text for value in ('unsupported kex', 'no matching key exchange', 'no matching host key', 'bad configuration option')):
        return TunnelError('OpenSSH на этом ПК несовместим с настройками SSH сервера. Обновите Клиент OpenSSH Windows.', 'ssh-version', True)
    if 'could not resolve hostname' in text:
        return TunnelError('Не удалось определить адрес VPS. Проверьте адрес сервера и DNS.', 'host-scan', True)
    if 'connection refused' in text:
        return TunnelError(f'VPS отклонил SSH-подключение к порту {profile.ssh_port}. Проверьте службу SSH и правила доступа.', 'host-scan')
    if any(value in text for value in ('timed out', 'no route to host', 'network is unreachable')):
        return TunnelError(f'Нет ответа VPS по SSH на порту {profile.ssh_port}. Проверьте сеть и доступ через VPN.', 'host-scan')
    return TunnelError('Не удалось получить SSH-ключ VPS через OpenSSH. Подробности сохранены в журнале приложения.', 'host-scan')


async def scan_host(profile):
    # Probe auth is deliberately expected to fail after saving the public
    # host key. It must not use the pilot key, an agent, or trusted known_hosts.
    with tempfile.TemporaryDirectory(prefix='spotter-host-') as temporary:
        directory = Path(temporary)
        hosts, config = directory/'candidate_hosts', directory/'ssh_config'
        config.write_text('# Isolated host key probe\n', encoding='ascii')
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        process = await asyncio.create_subprocess_exec(*host_probe_command(profile, hosts, config),
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE, **kwargs)
        own(process)
        try:
            try:
                _, stderr = await asyncio.wait_for(process.communicate(), 15)
            except asyncio.TimeoutError as exc:
                raise TunnelError('Проверка SSH-ключа VPS превысила 15 секунд. Проверьте соединение с сервером.', 'host-scan') from exc
        finally:
            try:
                if process.returncode is None:
                    with contextlib.suppress(ProcessLookupError):process.kill()
                    await asyncio.wait_for(process.wait(), 2)
            finally:
                release(process)
        if not hosts.is_file():
            raw = stderr.decode(errors='replace')[-4000:]
            logging.warning('SSH host probe failed: %s', raw)
            raise host_probe_error(raw, profile)
        return parse_host_key(hosts.read_text(encoding='utf-8'), profile)
