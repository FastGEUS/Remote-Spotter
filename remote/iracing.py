"""Read-only iRacing SDK capture. YAML parsing and derived data stay on VPS."""
import base64
import ctypes
import json
import logging
import math
import platform
import re
import struct
import time
import zlib

LAYOUT='irsdk-selected-v1'
SECTIONS=('WeekendInfo','DriverInfo','SessionInfo','SplitTimeInfo')
VARIABLES=tuple(('SessionTime SessionNum SessionUniqueID SessionTick SessionState SessionFlags SessionTimeRemain SessionLapsRemain SessionLapsRemainEx SessionLapsTotal '
    'SessionTimeTotal SessionTimeOfDay IsOnTrack IsOnTrackCar IsInGarage IsGarageVisible IsReplayPlaying IsSpectator PlayerCarIdx '
    'PlayerCarMyIncidentCount PlayerCarTeamIncidentCount PlayerCarPosition PlayerCarClassPosition '
    'PlayerTrackSurface CarLeftRight Lap LapCompleted LapDistPct LapCurrentLapTime LapLastLapTime '
    'LapBestLapTime LapDeltaToSessionBestLap LapDeltaToSessionBestLap_OK Speed RPM Gear FuelLevel '
    'Throttle Brake Clutch ThrottleRaw BrakeRaw ClutchRaw SteeringWheelAngle SteeringWheelAngleMax Lat Lon Alt Yaw YawNorth '
    'VelocityX VelocityY VelocityZ LatAccel LongAccel VertAccel AirTemp TrackTemp TrackTempCrew TrackWetness WeatherDeclaredWet Precipitation WindVel '
    'WindDir RelativeHumidity FogLevel WaterTemp OilTemp OilPress Voltage EngineWarnings '
    'dcBrakeBias dcTractionControl dcABS dcPitSpeedLimiter dcDRS CarIdxLap CarIdxLapCompleted '
    'CarIdxLapDistPct CarIdxTrackSurface CarIdxOnPitRoad CarIdxPosition CarIdxClassPosition '
    'CarIdxLastLapTime CarIdxBestLapTime CarIdxF2Time CarIdxEstTime CarIdxSessionFlags '
    'OnPitRoad PitRepairLeft PitOptRepairLeft PitstopActive PlayerCarTowTime PitSvFuel CarDistAhead CarDistBehind PlayerTireCompound').split()) + tuple(
    wheel+field for wheel in ('LF','RF','LR','RR') for field in
    ('pressure','coldPressure','tempCL','tempCM','tempCR','wearL','wearM','wearR'))


def safe(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(list,tuple)):return [safe(v) for v in value[:128]]
    return value


def encode_metadata(sections):
    raw=json.dumps(sections,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>262144:raise ValueError('iRacing session metadata exceeds limit')
    return base64.b64encode(zlib.compress(raw,1)).decode('ascii')


def split_metadata(raw, encoding):
    """Select sections from one byte copy; never parse YAML on the pilot PC.

    Real session strings need not separate sections with an empty line. The
    SDK's section helper depends on that formatting and can lose the roster.
    """
    source=raw.rstrip(b'\x00').decode(encoding,errors='replace')
    headers=list(re.finditer(r'(?m)^([A-Za-z][A-Za-z0-9_]*):[ \t]*\r?$',source))
    sections={}
    for i,match in enumerate(headers):
        if match[1] in SECTIONS:
            end=headers[i+1].start() if i+1<len(headers) else len(source)
            sections[match[1]]=source[match.start():end].rstrip()+'\n'
    return sections


class IRacingReader:
    game='iracing'
    def __init__(self, *, sdk=None, test_file=None, sdk_factory=None):
        if sdk is None:
            if not test_file and platform.system()!='Windows':
                raise RuntimeError('iRacing capture requires Windows')
            import irsdk
            sdk_factory=sdk_factory or (lambda:irsdk.IRSDK(parse_yaml_async=False))
            sdk=sdk_factory()
        self.sdk_factory=sdk_factory
        self.sdk=sdk;self.test_file=test_file;self.next_open=0;self.generation=0
        self.metadata=None;self.metadata_checked=0;self.names=set()
        self.metadata_version=None;self.last_read_log=-30.;self.read_errors=0
        self.layout=None;self.last_tick=None;self.tick_changed=0.;self.event_handles=set()
        self.kernel=None
        if not test_file and platform.system()=='Windows':
            from ctypes import wintypes
            self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            self.kernel.OpenFileMappingW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
            self.kernel.OpenFileMappingW.restype=wintypes.HANDLE
            self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            self.kernel.CloseHandle.restype=wintypes.BOOL
            self.kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype=wintypes.DWORD

    def _wait_valid_event(self):
        # startup() can discard this field on timeout. Retain ownership before
        # that happens, including attempts made while the simulator is loading.
        event=getattr(self.sdk,'_data_valid_event',None)
        if not event:return False
        self.event_handles.add(event)
        return self.kernel.WaitForSingleObject(event,32)==0

    def _layout(self):
        header=self.sdk._header
        return (header.version,header.num_vars,header.var_header_offset,header.num_buf,header.buf_len)

    def close(self):
        event=getattr(self.sdk,'_data_valid_event',None)
        if event:self.event_handles.add(event)
        try:
            try:self.sdk.unfreeze_var_buffer_latest()
            finally:self.sdk.shutdown()
        finally:
            if self.kernel:
                for handle in self.event_handles:self.kernel.CloseHandle(handle)
            self.event_handles.clear()
            self.metadata=None;self.metadata_version=None;self.names=set();self.layout=None
            self.last_tick=None;self.tick_changed=0.;self.next_open=time.monotonic()+1
            # A new SDK instance also clears connection-workaround state which
            # pyirsdk.shutdown() leaves behind after a simulator replacement.
            if self.sdk_factory:self.sdk=self.sdk_factory()

    def read(self):
        try:return self._read()
        except (OSError,ValueError,KeyError,TypeError,IndexError,BufferError,struct.error) as exc:
            # Memory may change while the game loads or exits. Keep the relay
            # alive while only the invalid SDK view is discarded.
            self.read_errors+=1
            now=time.monotonic()
            if now-self.last_read_log>=5:
                logging.warning('iRacing SDK read unavailable (%s); reopening SDK, transport kept (errors=%s)',type(exc).__name__,self.read_errors)
                self.last_read_log=now
            self.close()
            return None

    def _read(self):
        now=time.monotonic()
        if not self.sdk.is_initialized:
            if now<self.next_open:return None
            self.next_open=now+1
            if self.kernel:
                # Probe the existing mapping: never create it, never call the
                # SDK's HTTP sim-status request with an unbounded timeout.
                mapping=self.kernel.OpenFileMappingW(4,False,'Local\\IRSDKMemMapFileName')
                if not mapping:return None
                self.kernel.CloseHandle(mapping)
                self.sdk._check_sim_status=lambda:True
                self.sdk._wait_valid_data_event=self._wait_valid_event
            if not self.sdk.startup(test_file=self.test_file):
                # Never retain a partially initialized view during loading.
                self.close();return None
            self.names=set(self.sdk.var_headers_names);self.generation+=1
            self.layout=self._layout();self.tick_changed=now
            logging.info('iRacing SDK initialized: %s selected channels available; missing=%s',
                len(self.names.intersection(VARIABLES)),','.join(sorted(set(VARIABLES)-self.names)))
            for buffer in getattr(getattr(self.sdk,'_header',None),'var_buf',[]):
                original=buffer.freeze
                def consistent_freeze(buffer=buffer,original=original):
                    before=(buffer.tick_count,getattr(buffer,'tick_count_begin',0))
                    original()
                    after=(buffer.tick_count,getattr(buffer,'tick_count_begin',0))
                    buffer.snapshot_consistent=before==after and (after[1]==0 or after[0]==after[1])
                    buffer.snapshot_tick=after[0]
                buffer.freeze=consistent_freeze
        if self._layout()!=self.layout:
            logging.info('iRacing SDK channel layout changed; reopening for the new simulator')
            self.close();return None
        if not self.sdk.is_connected:
            self.close();return None
        values=None;snapshot_tick=None
        for _ in range(3):
            self.sdk.freeze_var_buffer_latest()
            try:
                tick=getattr(self.sdk,'_var_buffer_latest',None)
                # Test the copy, not the live tick after unpacking it. Once
                # frozen, a later write to shared memory cannot corrupt it.
                if tick and not getattr(tick,'snapshot_consistent',True):continue
                values={name:safe(self.sdk[name]) for name in VARIABLES if name in self.names}
                snapshot_tick=getattr(tick,'snapshot_tick',None)
                break
            finally:self.sdk.unfreeze_var_buffer_latest()
        if values is None:return None
        if isinstance(snapshot_tick,int):
            if self.last_tick is not None and snapshot_tick<self.last_tick:
                logging.info('iRacing SDK ticks restarted; reopening for the new simulator')
                self.close();return None
            if snapshot_tick!=self.last_tick:
                self.last_tick=snapshot_tick;self.tick_changed=now
            elif now-self.tick_changed>=2.5:
                logging.info('iRacing SDK ticks stopped; releasing old simulator mapping, transport kept')
                self.close();return None
        game_time=values.get('SessionTime')
        if not isinstance(game_time,(int,float)) or game_time<0:return None
        version=self.sdk.session_info_update
        if self.metadata is None or (version!=self.metadata_version and now-self.metadata_checked>=.25):
            self.metadata_checked=now
            header=self.sdk._header
            before=(version,header.session_info_offset,header.session_info_len)
            raw=self.sdk._shared_mem[before[1]:before[1]+before[2]]
            after=(self.sdk.session_info_update,header.session_info_offset,header.session_info_len)
            if before==after:
                sections=split_metadata(raw,'utf-8' if self.sdk.is_session_info_utf8 else 'cp1252')
                if 'WeekendInfo' in sections and 'DriverInfo' in sections:
                    self.metadata=encode_metadata(sections);self.metadata_version=version
            if self.metadata is None:return None
        replay=bool(values.get('IsSpectator') or (values.get('IsReplayPlaying') and not values.get('IsOnTrack')))
        status='paused' if replay else 'live' if values.get('IsOnTrack') and not values.get('IsInGarage') else 'garage'
        return {'gameTime':game_time,'status':status,'sourceMode':'iracing',
            'sourceSession':['iracing',self.generation,values.get('SessionUniqueID'),values.get('SessionNum',0)],
            'session':{'track':'iRacing','lengthM':0,'phase':0,'scoringTime':game_time},
            'cars':[],'pilot':None,'iracingSnapshot':{'layout':LAYOUT,'values':values,'sessionData':self.metadata}}


class AutoReader:
    def __init__(self, readers=None):
        if readers is None:
            from .native import NativeReader
            readers=[IRacingReader(),NativeReader()]
        self.readers=readers;self.active=None;self.game='iracing'
    def read(self):
        candidates=[self.active] if self.active else self.readers
        for reader in candidates:
            value=reader.read()
            if value is not None:
                self.active=reader;self.game=getattr(reader,'game','lmu')
                value['sourceMode']=self.game
                return value
        return None
    def close(self):
        for reader in self.readers:reader.close()
        self.active=None
