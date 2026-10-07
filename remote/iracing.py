"""Read-only iRacing SDK capture. YAML parsing and derived data stay on VPS."""
import base64
import ctypes
import json
import math
import platform
import time
import zlib

LAYOUT='irsdk-selected-v1'
SECTIONS=('WeekendInfo','DriverInfo','SessionInfo','SplitTimeInfo')
VARIABLES=tuple(('SessionTime SessionNum SessionState SessionFlags SessionTimeRemain SessionLapsRemain '
    'SessionTimeOfDay IsOnTrack IsOnTrackCar IsReplayPlaying IsSpectator PlayerCarIdx '
    'PlayerCarMyIncidentCount PlayerCarTeamIncidentCount PlayerCarPosition PlayerCarClassPosition '
    'PlayerTrackSurface CarLeftRight Lap LapCompleted LapDistPct LapCurrentLapTime LapLastLapTime '
    'LapBestLapTime LapDeltaToSessionBestLap LapDeltaToSessionBestLap_OK Speed RPM Gear FuelLevel '
    'Throttle Brake Clutch SteeringWheelAngle SteeringWheelAngleMax Lat Lon Alt Yaw '
    'LatAccel LongAccel VertAccel AirTemp TrackTemp TrackTempCrew Precipitation WindVel '
    'WindDir RelativeHumidity FogLevel WaterTemp OilTemp OilPress Voltage EngineWarnings '
    'dcBrakeBias dcTractionControl dcABS dcPitSpeedLimiter dcDRS CarIdxLap CarIdxLapCompleted '
    'CarIdxLapDistPct CarIdxTrackSurface CarIdxOnPitRoad CarIdxPosition CarIdxClassPosition '
    'CarIdxLastLapTime CarIdxBestLapTime CarIdxF2Time CarIdxEstTime CarIdxSessionFlags '
    'OnPitRoad PitRepairLeft PitOptRepairLeft PitstopActive PlayerCarTowTime PitSvFuel').split()) + tuple(
    wheel+field for wheel in ('LF','RF','LR','RR') for field in
    ('pressure','tempCL','tempCM','tempCR','wearL','wearM','wearR'))


def safe(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(list,tuple)):return [safe(v) for v in value[:128]]
    return value


def encode_metadata(sections):
    raw=json.dumps(sections,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>262144:raise ValueError('iRacing session metadata exceeds limit')
    return base64.b64encode(zlib.compress(raw,1)).decode('ascii')


class IRacingReader:
    game='iracing'
    def __init__(self, *, sdk=None, test_file=None):
        if sdk is None:
            if not test_file and platform.system()!='Windows':
                raise RuntimeError('iRacing capture requires Windows')
            import irsdk
            sdk=irsdk.IRSDK(parse_yaml_async=False)
        self.sdk=sdk;self.test_file=test_file;self.next_open=0;self.generation=0
        self.metadata=None;self.metadata_checked=0;self.names=set()
        self.kernel=None
        if not test_file and platform.system()=='Windows':
            from ctypes import wintypes
            self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            self.kernel.OpenFileMappingW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
            self.kernel.OpenFileMappingW.restype=wintypes.HANDLE
            self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            self.kernel.CloseHandle.restype=wintypes.BOOL

    def close(self):
        event=getattr(self.sdk,'_data_valid_event',None)
        self.sdk.unfreeze_var_buffer_latest()
        self.sdk.shutdown()
        # pyirsdk clears this field without closing its owned event handle.
        if event and self.kernel:self.kernel.CloseHandle(event)
        self.metadata=None;self.names=set();self.next_open=time.monotonic()+1

    def read(self):
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
            if not self.sdk.startup(test_file=self.test_file):return None
            self.names=set(self.sdk.var_headers_names);self.generation+=1
            for buffer in getattr(getattr(self.sdk,'_header',None),'var_buf',[]):
                original=buffer.freeze
                def consistent_freeze(buffer=buffer,original=original):
                    before=(buffer.tick_count,getattr(buffer,'tick_count_begin',0))
                    original()
                    after=(buffer.tick_count,getattr(buffer,'tick_count_begin',0))
                    buffer.snapshot_consistent=before==after and (after[1]==0 or after[0]==after[1])
                buffer.freeze=consistent_freeze
        if not self.sdk.is_connected:
            self.close();return None
        self.sdk.freeze_var_buffer_latest()
        try:
            values={name:safe(self.sdk[name]) for name in VARIABLES if name in self.names}
            tick=getattr(self.sdk,'_var_buffer_latest',None)
            if tick and (not getattr(tick,'snapshot_consistent',True) or getattr(tick,'tick_count_begin',0) not in (0,tick.tick_count)):
                return None  # Version 1.3.7 SDK exposes torn-read markers.
        finally:self.sdk.unfreeze_var_buffer_latest()
        game_time=values.get('SessionTime')
        if not isinstance(game_time,(int,float)) or game_time<0:return None
        if self.metadata is None or now-self.metadata_checked>=1:
            self.metadata_checked=now
            # Pinned SDK method returns raw section bytes, not parsed YAML.
            sections={}
            for name in SECTIONS:
                raw=self.sdk._get_session_info_binary(name)
                if raw:
                    sections[name]=raw.decode('utf-8' if self.sdk.is_session_info_utf8 else 'cp1252',errors='replace')
            self.metadata=encode_metadata(sections)
        replay=bool(values.get('IsSpectator') or (values.get('IsReplayPlaying') and not values.get('IsOnTrack')))
        status='paused' if replay else 'live' if values.get('IsOnTrack') else 'garage'
        return {'gameTime':game_time,'status':status,'sourceMode':'iracing',
            'sourceSession':['iracing',self.generation,values.get('SessionNum',0)],
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
