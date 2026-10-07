"""Synthetic SDK-compatible binary fixture, not a dump from a live iRacing car."""
import math
import struct
from pathlib import Path
import yaml
from remote.iracing import encode_metadata,LAYOUT


def values(t):
    pct=(t/10)%1;lap=int(t/10)+1
    return {'SessionTime':float(t),'SessionNum':0,'SessionState':4,'SessionFlags':4,'SessionTimeRemain':max(0.,600.-t),
        'SessionTimeOfDay':45000.+t,'PlayerCarIdx':2,'IsOnTrack':True,'IsOnTrackCar':True,'IsReplayPlaying':False,
        'IsSpectator':False,'Lap':lap,'LapCompleted':lap-1,'LapCurrentLapTime':float(t)%10,'LapLastLapTime':10 if lap>1 else 0,
        'LapBestLapTime':10 if lap>1 else 0,'LapDistPct':pct,'Speed':20*math.pi,'Yaw':pct*2*math.pi,
        'FuelLevel':100-t/10*2,'RPM':7000.,'Gear':5,'Throttle':.8,'Brake':.1,'Clutch':0.,
        'SteeringWheelAngle':.2,'SteeringWheelAngleMax':9.,'LatAccel':3.,'LongAccel':1.,
        'AirTemp':20.,'TrackTempCrew':30.,'Precipitation':0.,'CarLeftRight':2,'PlayerTrackSurface':3,
        'PlayerCarMyIncidentCount':0,'CarIdxLapDistPct':[(pct-.05)%1,-1.,pct,(pct+.05)%1],
        'CarIdxTrackSurface':[3,-1,3,3],'CarIdxLapCompleted':[lap-1,-1,lap-1,lap-1],
        'CarIdxPosition':[3,0,2,1],'CarIdxClassPosition':[2,0,1,1],'CarIdxOnPitRoad':[False]*4,
        'CarIdxLastLapTime':[11.,-1.,10.,9.],'CarIdxBestLapTime':[11.,-1.,10.,9.],
        'CarIdxF2Time':[2.,-1.,1.,0.],'CarIdxSessionFlags':[0]*4}


def sections():
    source={'WeekendInfo':{'TrackID':1,'TrackName':'SDK fixture circuit','TrackLength':'0.62831853 km','TrackConfigName':'road'},
        'DriverInfo':{'DriverCarIdx':2,'DriverCarFuelMaxLtr':110,'DriverCarSLBlinkRPM':8000,'Drivers':[
            {'CarIdx':0,'UserName':'GT driver','CarNumber':'009','CarClassShortName':'GT3','CarClassID':2},
            {'CarIdx':2,'UserName':'Fixture pilot','CarNumber':'007','CarClassShortName':'GT3','CarClassID':2},
            {'CarIdx':3,'UserName':'Prototype driver','CarNumber':'1','CarClassShortName':'GTP','CarClassID':1}]},
        'SessionInfo':{'Sessions':[{'SessionNum':0,'SessionType':'Race'}]},
        'SplitTimeInfo':{'Sectors':[{'SectorNum':0,'SectorStartPct':0},{'SectorNum':1,'SectorStartPct':.2},{'SectorNum':2,'SectorStartPct':.7}]}}
    return {key:yaml.safe_dump({key:value},allow_unicode=True,sort_keys=False,indent=1) for key,value in source.items()}


def frame(t=0,seq=0):
    return {'type':'ingest','protocolVersion':1,'streamId':'irs-fixture-stream','sessionId':'irs-fixture-session',
        'seq':seq,'capturedAt':1760000000000+t*1000,'gameTime':t,'mode':'iracing','status':'live',
        'iracingSnapshot':{'layout':LAYOUT,'values':values(t),'sessionData':encode_metadata(sections())}}


class BinaryFixture:
    def __init__(self,path):
        self.path=Path(path);example=values(0);self.spec=[];offset=0
        for key,value in example.items():
            sample=value[0] if isinstance(value,list) else value
            code='?' if isinstance(sample,bool) else 'i' if isinstance(sample,int) else 'd'
            kind={'?':1,'i':2,'d':5}[code];count=len(value) if isinstance(value,list) else 1
            self.spec.append((key,kind,code,count,offset));offset+=struct.calcsize('<'+code*count)
        self.var_start=112;self.data_start=112+144*len(self.spec);self.data_size=offset
        self.yaml_start=self.data_start+self.data_size
        metadata=('---\n'+'\n'.join(value+'\n' for value in sections().values())+'\n\0').encode()
        self.image=bytearray(self.yaml_start+len(metadata))
        struct.pack_into('<10i',self.image,0,1,1,60,1,len(metadata),self.yaml_start,len(self.spec),self.var_start,1,self.data_size)
        struct.pack_into('<4i',self.image,48,1,self.data_start,1,0)
        for i,(key,kind,code,count,offset) in enumerate(self.spec):
            struct.pack_into('<iii?3x32s64s32s',self.image,self.var_start+i*144,kind,offset,count,False,key.encode(),b'Fixture',b'')
        self.image[self.yaml_start:]=metadata;self.write(0,1)
    def write(self,t,tick):
        data=values(t)
        for key,kind,code,count,offset in self.spec:
            value=data[key];items=value if isinstance(value,list) else [value]
            struct.pack_into('<'+code*count,self.image,self.data_start+offset,*items)
        struct.pack_into('<4i',self.image,48,tick,self.data_start,tick,0)
        self.path.write_bytes(self.image)
