"""Official split times and bounded session journals, computed on the VPS.

Shared-memory sector flags have an explicitly undocumented channel order.
Keep channels separate until a viewer has verified their order in live LMU.
"""
import hashlib
import json
import math
from pathlib import Path


def positive(value):
    value = float(value)
    return value if math.isfinite(value) and 0 < value < 99999 else None


def splits(first, cumulative, total=None):
    first, cumulative = positive(first), positive(cumulative)
    second = cumulative-first if first and cumulative and cumulative > first else None
    total = positive(total) if total is not None else None
    third = total-cumulative if second and total and total > cumulative else None
    return [first, second, third]


def flag_state(reader, demo=False):
    session = reader.shmm.lmuScorInfo
    pilot = reader.shmm.lmuScorVeh()
    channels = list(session.mSectorFlag)
    phase = session.mGamePhase
    yellow = 1 in channels
    code = ('caution' if phase == 6 else 'finished' if phase == 8 else
            'stopped' if phase == 7 else 'yellow' if yellow else
            'green' if phase == 5 else 'starting' if phase in (3, 4) else 'waiting')
    yellow_state = session.mYellowFlagState
    if isinstance(yellow_state, bytes):
        yellow_state = int.from_bytes(yellow_state, 'little', signed=True)
    return {'session': code, 'phase': phase, 'yellowState': yellow_state,
            'pilotBlue': pilot.mFlag == 6, 'rawChannels': channels,
            'sectorFlags': ['yellow' if c == 1 else 'clear' if c == 0 else 'unknown' for c in channels] if demo else None,
            'channelOrder': 'synthetic S1,S2,S3' if demo else 'unverified',
            'source': 'LMU ScoringInfo.mSectorFlag / mGamePhase; VehicleScoringInfo.mFlag'}


def geometry(points, indices, demo=False):
    """Sector endpoints refer to captured crossing nodes, never track thirds."""
    if demo and len(points) > 4:
        indices = [round((len(points)-1)/3), round(2*(len(points)-1)/3)]
    if not indices or len(indices) != 2:
        return None
    a, b = indices
    if not all(isinstance(i, int) for i in indices) or not 0 < a < b < len(points)-1:
        return None
    return {'indices': [a, b], 'source': 'synthetic demo sectors' if demo else 'TinyPedal recorded sector crossings'}


class SectorTiming:
    def __init__(self, directory):
        self.directory = Path(directory)/'sector_history'
        self.directory.mkdir(exist_ok=True)
        self.key = None
        self.current = None
        self.pending = None
        self.history = []
        self.last_comparison = None
        self.file = None
        self.storage_error = None

    def save(self):
        if not self.file:
            return
        try:
            temporary = self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version': 1, 'context': self.context,
                                             'laps': self.history}, allow_nan=False), encoding='utf-8')
            temporary.replace(self.file)
            self.storage_error = None
        except OSError:
            self.storage_error = 'journal-write-failed'

    def update(self, reader, frame, info):
        v, t = reader.shmm.lmuScorVeh(), reader.shmm.lmuTeleVeh()
        key = (frame.get('streamId', ''), frame.get('sessionId', ''), v.mID, frame['session']['track'])
        if key != self.key:
            self.key, self.current, self.pending, self.history = key, None, None, []
            self.last_comparison = None
            self.context = {'streamId': key[0], 'sessionId': key[1], 'pilotId': key[2], 'track': key[3],
                            'source': 'LMU official scoring splits; S2=CurSector2-CurSector1; S3=LastLapTime-LastSector2'}
            self.file = self.directory/(hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]+'.json')
            if self.file.exists():
                try:
                    saved = json.loads(self.file.read_text())
                    if saved.get('context') == self.context:
                        self.history = saved['laps'][-200:]
                except (OSError, ValueError, KeyError, TypeError):
                    self.storage_error = 'journal-read-failed'
        now, start = float(t.mElapsedTime), float(t.mLapStartET)
        lap = t.mLapNumber
        best = [positive(x) for x in info.sectors.sessionBest.sectorBestTB]
        sector = reader.lap.sector_index()
        elapsed = now-start if math.isfinite(now-start) and now >= start >= 0 else None
        valid = v.mCountLapFlag == 2 and not t.mLapInvalidated
        in_pit = bool(v.mInPits)
        if self.current and start > self.current['start']:
            previous = self.current
            if previous['eligible'] and start-previous['start'] < 100000:
                self.pending = {**previous, 'totalExpected': start-previous['start'], 'endedAt': start}
            self.current = None
        elif self.current and (start < self.current['start'] or lap < self.current['lap']):
            self.current = self.pending = None
        if self.current is None:
            self.current = {'lap': lap, 'start': start, 'eligible': elapsed is not None and elapsed <= .75,
                            'valid': valid, 'inPit': in_pit, 'splits': [None, None, None],
                            'reference': best[:]}
        self.current['valid'] &= valid
        self.current['inPit'] |= in_pit
        reported = splits(v.mCurSector1, v.mCurSector2)
        # CurSector fields may still belong to the previous lap just after S/F.
        if sector >= 1 and reported[0] is not None and elapsed is not None and reported[0] <= elapsed+.25:
            self.current['splits'][0] = reported[0]
        if sector == 2 and reported[1] is not None and elapsed is not None and sum(reported[:2]) <= elapsed+.25:
            self.current['splits'][1] = reported[1]
        if self.pending:
            p = self.pending
            official = splits(v.mLastSector1, v.mLastSector2, v.mLastLapTime)
            matches = all(x is not None for x in official) and abs(sum(official)-p['totalExpected']) <= .75
            matches &= all(x is None or y is not None and abs(x-y) <= .05 for x, y in zip(p['splits'][:2], official[:2]))
            # Invalid laps can leave the previous valid LastLapTime in memory.
            if matches and p['valid']:
                times, total = official, sum(official)
            elif elapsed is not None and elapsed > 1:
                times, total = p['splits'], None
            else:
                times = None
            if times is not None:
                entry = {'lap': p['lap'], 'lapStart': p['start'], 'sectors': times, 'total': total,
                         'valid': p['valid'], 'inPit': p['inPit'],
                         'reference': p['reference'],
                         'status': 'complete' if total is not None else 'invalid' if not p['valid'] else 'missing-official-time'}
                # S3 becomes comparable only once the complete official lap
                # is confirmed. Invalid/missing laps must clear old comparisons.
                self.last_comparison = entry if total is not None and p['valid'] and not p['inPit'] else None
                if self.last_comparison and self.current['start']==p['endedAt']:
                    # Official S3 can arrive just after the next lap starts.
                    # It belongs to the completed prior lap, so include it in
                    # the new lap's benchmark without rewriting that prior delta.
                    self.current['reference'] = [min(old,value) if old is not None else value
                        for old,value in zip(self.current['reference'],times)]
                if not any(row['lapStart'] == p['start'] for row in self.history):
                    self.history = (self.history+[entry])[-200:]
                    self.save()
                self.pending = None
        current = self.current['splits'][:]
        offset = sum(current[:sector]) if all(x is not None for x in current[:sector]) else None
        running = elapsed-offset if elapsed is not None and offset is not None and elapsed >= offset else None
        last = splits(v.mLastSector1, v.mLastSector2, v.mLastLapTime)
        delta, reference, comparison_lap = [None]*3, [None]*3, [None]*3
        for i in range(3):
            sample = self.current if current[i] is not None else self.last_comparison
            if sample is None or (sample is self.current and (not sample['eligible'] or not sample['valid'] or sample['inPit'])):
                continue
            value = current[i] if sample is self.current else sample['sectors'][i]
            benchmark = sample['reference'][i]
            if value is not None and benchmark is not None:
                delta[i], reference[i], comparison_lap[i] = value-benchmark, benchmark, sample['lap']
        return {'lap': lap, 'currentSector': sector+1, 'elapsed': running, 'current': current,
                'last': last, 'best': best, 'delta': delta,
                'reference': reference, 'comparisonLap': comparison_lap,
                'history': self.history, 'historyLimit': 200, 'storageError': self.storage_error,
                'valid': valid, 'source': self.context['source']}
