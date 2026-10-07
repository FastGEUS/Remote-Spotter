"""Capture recovery and bounded delivery; no driving calculations on the PC."""
import asyncio
import contextlib
import json
import logging
import uuid
from collections import deque


class CaptureState:
    def __init__(self, demo, now):
        self.demo = demo
        self.session_id = str(uuid.uuid4())
        self.source = None
        self.game_time = None
        self.session = None
        self.last_change = self.last_remap = now
        self.missing_since = None

    def update(self, sample, now, reader=None):
        if sample is None:
            if self.missing_since is None:
                self.missing_since = now
            if reader and now-self.last_remap >= 5:
                reader.close()
                self.last_remap = now
            # A failed consistency copy isn't a new game session.
            if self.session is not None and now-self.missing_since < .5:
                return None
            return {'status': 'waitingForGame', 'gameTime': self.game_time or 0,
                    'session': self.session or {'track': '', 'lengthM': 0, 'phase': 0, 'scoringTime': 0},
                    'cars': [], 'pilot': None}
        self.missing_since = None
        source = sample.pop('sourceSession', 'demo' if self.demo else 'lmu')
        if source != self.source or self.game_time is not None and sample['gameTime'] < self.game_time:
            self.source = source
            self.session_id = str(uuid.uuid4())
            self.last_change = self.last_remap = now
        if sample['gameTime'] != self.game_time:
            self.last_change = now
        elif sample['status'] == 'live' and now-self.last_change > 1:
            sample['status'] = 'paused'
        # Stale mappings can also say garage/not-realtime while LMU is running.
        if reader and now-self.last_change > 5 and now-self.last_remap >= 5:
            logging.warning('%s: данные не обновляются; повторно открываю shared memory.',getattr(reader,'game','lmu'))
            reader.close()
            self.last_remap = now
        self.game_time, self.session = sample['gameTime'], dict(sample['session'])
        return sample


class AckWindow:
    """At most two unacknowledged frames. ACK confirms receipt by the relay.

    Calculation can follow later; the viewer uses the processed sample's age.
    """
    def __init__(self, websocket):
        self.ws = websocket
        self.pending = deque()
        self.changed = asyncio.Event()
        self.task = None
        self.first = True

    async def receive(self):
        try:
            while True:
                raw = await asyncio.wait_for(self.ws.recv(), 10 if self.first else 5)
                ack = json.loads(raw)
                if not isinstance(ack, dict) or ack.get('type') != 'ack' or not self.pending or ack.get('seq') != self.pending[0]:
                    raise RuntimeError('Invalid server acknowledgement')
                self.pending.popleft()
                self.first = False
                self.changed.set()
        finally:
            self.changed.set()

    def start(self):
        self.task = asyncio.create_task(self.receive())

    async def ready(self):
        while True:
            if self.task.done():
                await self.task  # Propagate close / ACK timeout to reconnect loop.
            if len(self.pending) < 2:
                return
            self.changed.clear()
            await asyncio.wait_for(self.changed.wait(), 10 if self.first else 5)

    def sent(self, seq):
        self.pending.append(seq)

    async def close(self):
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self.task
