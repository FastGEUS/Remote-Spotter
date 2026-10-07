"""Own the SSH lifecycle, existing collector and authenticated VPS status."""
import asyncio
import contextlib
from pathlib import Path
from types import SimpleNamespace
import urllib.error

from .state import State
from .tunnel import Tunnel, TunnelError, http_json
from .key_permissions import prepare_private_key, KeyPermissionError


def require_iracing_server(value):
    if 'iracing' not in (value.get('supportedGames') or []):
        raise TunnelError('Обновите VPS до 0.4.7 из пакета 0.6.0: этот сервер ещё не поддерживает iRacing.', 'server-version', True)


class Session:
    def __init__(self, profile, directory, emit, *, demo=False, tunnel_factory=Tunnel):
        self.profile, self.directory, self.emit = profile, directory, emit
        self.demo, self.tunnel_factory = demo, tunnel_factory
        self.state = State(profile.role,game_mode=profile.game)
        self.last_published = None
        self.transport_connected = False

    def publish(self):
        value = self.state.presentation()
        if value != self.last_published:
            self.last_published = dict(value)
            self.emit({'kind': 'state', **value})

    def capture_event(self, event):
        if event['kind'] == 'transport':
            self.transport_connected = event['connected']
            self.state.phase = 'online' if event['connected'] else 'reconnecting'
            if not event['connected']:
                self.state.data_fresh = False
        elif event['kind'] == 'source':
            self.state.game = event['status']
            self.state.game_mode=event.get('mode',self.state.game_mode)
        elif event['kind'] == 'busy':
            self.state.phase = 'reconnecting'
            self.state.reason = 'Канал пилота занят. Закройте прежний сборщик или демо.'
        self.publish()

    async def login(self, tunnel):
        _, cookie = await asyncio.to_thread(http_json, tunnel.origin + '/api/session', body={'token': self.profile.token})
        if not cookie or not cookie.startswith('spotter_session='):
            raise TunnelError('Не получена сессия споттера')
        # Cookie is handed directly to the browser cookie store, never to JS,
        # URL, logs, localStorage or command-line arguments.
        self.emit({'kind': 'viewer-session', 'origin': tunnel.origin, 'cookie': cookie})
        return cookie.split(';', 1)[0]

    async def serve(self, tunnel):
        collector = None
        cookie = None
        try:
            if self.profile.role == 'pilot':
                if not self.demo and self.profile.game!='lmu':
                    value,_=await asyncio.to_thread(http_json,tunnel.origin+'/api/status',token=self.profile.token)
                    require_iracing_server(value)
                from remote.collector import run
                args = SimpleNamespace(url=tunnel.origin.replace('http:', 'ws:') + '/ws/pilot',
                    allow_insecure_local=True, demo=self.demo, hz=20,game=self.profile.game)
                collector = asyncio.create_task(run(args, token=self.profile.token, on_event=self.capture_event))
            if self.profile.role == 'viewer':
                cookie = await self.login(tunnel)
                self.state.phase, self.state.reason = 'online', ''
            while True:
                tunnel.check()
                if collector and collector.done():
                    await collector
                    raise TunnelError('Сборщик завершился. Повторяем запуск.')
                try:
                    value, _ = await asyncio.to_thread(http_json, tunnel.origin + '/api/status',
                        token=self.profile.token if self.profile.role == 'pilot' else None, cookie=cookie)
                except urllib.error.HTTPError as exc:
                    if exc.code == 401:
                        if self.profile.role == 'viewer':
                            cookie = await self.login(tunnel)
                            continue
                        raise TunnelError('VPS отклонил ключ пилота. Нужен ключ именно этой роли.', 'token', True) from None
                    if exc.code == 404:
                        raise TunnelError('Обновите VPS до 0.4.7 из пакета 0.6.0: сервер ещё не поддерживает статусы приложения.', 'server-version', True) from None
                    raise
                self.state.apply_server(value)
                if self.profile.role == 'pilot' and self.transport_connected:
                    self.state.phase, self.state.reason = 'online', ''
                self.publish()
                await asyncio.sleep(1)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                role='пилота' if self.profile.role=='pilot' else 'споттера'
                raise TunnelError(f'VPS отклонил ключ {role}. Нужен ключ именно этой роли.', 'token', True) from None
            if exc.code==404:
                raise TunnelError('Обновите VPS до 0.4.7 из пакета 0.6.0.', 'server-version', True) from None
            raise
        finally:
            if collector:
                collector.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await collector

    async def run(self):
        port_file = Path(self.directory) / (self.profile.role + '-port')
        try:
            port = int(port_file.read_text())
            if not 1 <= port <= 65535:raise ValueError()
        except (OSError, ValueError):
            port = 18082 if self.profile.role == 'pilot' else 18081
        backoff, attempt = 1, 0
        key_prepared = False
        try:
            while True:
                self.state.phase = 'connecting' if not attempt else 'reconnecting'
                self.state.partner_connected = None
                self.state.data_fresh = False
                self.publish()
                tunnel = self.tunnel_factory(self.profile, self.directory, port=port)
                port = tunnel.port
                started = asyncio.get_running_loop().time()
                try:
                    if not key_prepared:
                        try:await prepare_private_key(self.profile.ssh_key)
                        except KeyPermissionError as exc:
                            raise TunnelError(str(exc), 'key-permissions', True) from exc
                        key_prepared = True
                    await tunnel.start()
                    # Stable origin preserves the viewer's existing panel layout
                    # across launches. A busy port gets its own new saved value.
                    port_file.parent.mkdir(parents=True, exist_ok=True)
                    port_file.write_text(str(tunnel.port))
                    await self.serve(tunnel)
                except TunnelError as exc:
                    self.state.reason = str(exc)
                    if exc.permanent:
                        self.state.phase = 'error'
                        self.state.partner_connected = None
                        self.state.data_fresh = False
                        self.publish()
                        self.emit({'kind': 'error', 'code': exc.code, 'message': str(exc)})
                        return
                    if exc.code == 'port':
                        port = None
                except RuntimeError as exc:
                    # Collector's 401 or unavailable Windows reader is a real
                    # configuration problem, not an endless tunnel retry.
                    self.state.phase, self.state.reason = 'error', str(exc)
                    self.state.partner_connected = None
                    self.state.data_fresh = False
                    self.publish()
                    self.emit({'kind': 'error', 'code': 'collector', 'message': str(exc)})
                    return
                except (OSError, ValueError, KeyError):
                    self.state.reason = 'Сервер временно недоступен. Восстанавливаем подключение.'
                finally:
                    await tunnel.stop()
                self.state.phase = 'reconnecting'
                self.state.partner_connected = None
                self.state.data_fresh = False
                self.publish()
                if asyncio.get_running_loop().time() - started >= 5:
                    backoff = 1
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
                attempt += 1
        finally:
            self.transport_connected = False
            self.state.partner_connected = None
            self.state.data_fresh = False
            # Preserve a actionable final error until another explicit Connect.
            if self.state.phase != 'error':
                self.state.phase = 'offline'
                self.publish()
