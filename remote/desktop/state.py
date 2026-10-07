"""Connection is independent from the game's current state and data freshness."""
from dataclasses import dataclass, asdict


@dataclass
class State:
    role: str
    phase: str = 'offline'
    game: str = 'waitingForGame'
    partner_connected: bool | None = None
    partner_name: str = ''
    data_fresh: bool = False
    reason: str = ''
    source_age_ms: int = -1
    ingest_age_ms: int = -1
    compute_ms: float = 0
    game_mode: str = 'auto'

    def presentation(self):
        title = {'offline': 'Вы офлайн', 'connecting': 'Подключаемся…',
                 'online': 'Вы онлайн', 'reconnecting': 'Восстановление связи',
                 'error': 'Нет подключения', 'stopping': 'Отключаемся…'}[self.phase]
        source = {'waitingForGame': 'Ожидание запуска', 'garage': 'В гараже',
                  'paused': 'Пауза / нет обновлений', 'live': 'На трассе'}
        caption = source.get(self.game, 'Ожидание телеметрии')
        if self.phase == 'online' and self.game == 'live' and not self.data_fresh:
            caption = 'Нет свежих данных'
        partner = 'Споттер' if self.role == 'pilot' else 'Пилот'
        partner = (partner if self.partner_connected else
                   f'{partner} · офлайн' if self.partner_connected is False else '—')
        partner_status = ('Онлайн' if self.partner_connected else
                          'Офлайн' if self.partner_connected is False else '—')
        return {**asdict(self), 'partner_name': '', 'title': title, 'game_caption': caption, 'partner': partner,
                'partner_status': partner_status,
                'button': 'Подключено' if self.phase == 'online' else 'Подключиться',
                'can_connect': self.phase in ('offline', 'error')}

    def apply_server(self, value):
        self.partner_connected = value['viewersConnected'] > 0 if self.role == 'pilot' else value['sourceConnected']
        self.source_age_ms = value['sourceAgeMs']
        self.ingest_age_ms = value['ingestAgeMs']
        self.compute_ms = value['computeMs']
        if self.role == 'viewer':
            self.game = value.get('gameStatus') or 'waitingForGame'
        if value.get('gameMode') in ('lmu','iracing','demo'):self.game_mode=value['gameMode']
        self.data_fresh = bool(value['sourceConnected'] and 0 <= self.source_age_ms < 1000
                               and 0 <= self.ingest_age_ms < 1000)
