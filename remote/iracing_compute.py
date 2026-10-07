"""iRacing-only server adapter. Never synthesizes missing LMU sensor channels."""
import base64
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import zlib
import yaml
from .iracing import LAYOUT, VARIABLES, SECTIONS
from .compute import number, integer, text


def num(value, low=-1e9, high=1e9):
    if value is None:return None
    return number(value,low,high)


def meta_number(value, default=None):
    try:
        result=float(str(value).split()[0]);return result if math.isfinite(result) else default
    except (ValueError,TypeError,IndexError):return default


def decode_metadata(encoded):
    if not isinstance(encoded,str) or len(encoded)>350000:raise ValueError('Invalid iRacing metadata')
    try:
        inflater=zlib.decompressobj()
        raw=inflater.decompress(base64.b64decode(encoded,validate=True),262145)
        if len(raw)>262144 or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError('iRacing metadata limit')
        sections=json.loads(raw)
    except (zlib.error,ValueError) as exc:raise ValueError('Invalid iRacing metadata') from exc
    if not isinstance(sections,dict) or set(sections)-set(SECTIONS):raise ValueError('Invalid SDK sections')
    result={}
    for key,source in sections.items():
        if not isinstance(source,str):raise ValueError('Invalid SDK YAML')
        # Preserve unquoted driver/team names and leading-zero car numbers.
        source=re.sub(r'(?m)^(\s*(?:UserName|TeamName|DriverSetupName|AbbrevName|Initials): )(.+)$',
            lambda m:m[1]+(m[2] if m[2].startswith(('"',"'")) else json.dumps(m[2],ensure_ascii=False)),source)
        try:
            for index,token in enumerate(yaml.scan(source,Loader=yaml.CSafeLoader)):
                if index>50000 or isinstance(token,(yaml.tokens.AliasToken,yaml.tokens.AnchorToken,yaml.tokens.TagToken)):
                    raise ValueError('SDK YAML aliases/tags are not accepted')
            value=yaml.load(source,Loader=yaml.CBaseLoader)
        except yaml.YAMLError as exc:raise ValueError('Invalid SDK YAML') from exc
        if not isinstance(value,dict) or not isinstance(value.get(key),dict):raise ValueError('Invalid SDK section shape')
        result[key]=value[key]
    drivers=result.get('DriverInfo',{}).get('Drivers',[])
    if not isinstance(drivers,list) or len(drivers)>128:raise ValueError('Invalid iRacing roster')
    ids=[]
    for driver in drivers:
        if not isinstance(driver,dict):raise ValueError('Invalid SDK driver')
        idx=meta_number(driver.get('CarIdx'))
        if idx is None or not idx.is_integer() or not 0<=idx<128:raise ValueError('Invalid SDK car index')
        ids.append(int(idx))
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate SDK car indices')
    return result


def validate(frame):
    if frame.get('type')!='ingest' or frame.get('protocolVersion')!=1 or frame.get('mode')!='iracing':raise ValueError('Unsupported protocol')
    text(frame['streamId']);text(frame['sessionId']);integer(frame['seq']);number(frame['capturedAt'],0,1e14)
    number(frame['gameTime'],0)
    if frame['status'] not in ('live','garage','paused','waitingForGame'):raise ValueError('Invalid source status')
    snapshot=frame.get('iracingSnapshot')
    if not snapshot:
        if frame['status']!='waitingForGame':raise ValueError('Missing iRacing snapshot')
        return None
    if snapshot.get('layout')!=LAYOUT:raise ValueError('Update iRacing collector and VPS together')
    values=snapshot.get('values')
    if not isinstance(values,dict) or set(values)-set(VARIABLES):raise ValueError('Unexpected SDK variables')
    for key,value in values.items():
        if value is None:continue
        if isinstance(value,list):
            if len(value)>128:raise ValueError('SDK array exceeds limit')
            for item in value:
                if item is not None and not isinstance(item,bool):number(item,0 if key.endswith('Flags') else -1e9,0xffffffff if key.endswith('Flags') else 1e9)
        elif not isinstance(value,bool):number(value,0 if key.endswith('Flags') else -1e9,0xffffffff if key.endswith('Flags') else 1e9)
    for key,lo,hi in [('Speed',0,250),('FuelLevel',0,1000),('RPM',0,100000),('Gear',-1,9),
                      ('Throttle',0,1),('Brake',0,1),('Clutch',0,1),('PlayerCarIdx',-1,127),('Lap',0,100000)]:
        num(values.get(key),lo,hi)
    for key,lo,hi in [('CarIdxLapDistPct',-1,1),('CarIdxTrackSurface',-1,3),('CarIdxPosition',0,128),
                      ('CarIdxClassPosition',0,128),('CarIdxLapCompleted',-1,100000),
                      ('CarIdxLastLapTime',-1,100000),('CarIdxBestLapTime',-1,100000)]:
        items=values.get(key)
        if items is not None and not isinstance(items,list):raise ValueError('SDK scoring channel must be an array')
        for value in items or []:num(value,lo,hi)
    for key,lo,hi in [('PlayerCarIdx',-1,127),('Lap',0,100000),('Gear',-1,9)]:
        if values.get(key) is not None:integer(values[key],lo,hi)
    if values.get('SessionTime') is not None and abs(values['SessionTime']-frame['gameTime'])>.001:
        raise ValueError('SDK time does not match capture time')
    return snapshot


def sector_starts(metadata):
    sectors=metadata.get('SplitTimeInfo',{}).get('Sectors',[])
    if not isinstance(sectors,list) or len(sectors)>64:return []
    values=sorted(meta_number(row.get('SectorStartPct')) for row in sectors
                  if isinstance(row,dict) and meta_number(row.get('SectorStartPct')) is not None)
    return values if values and values[0]==0 and all(0<=p<1 for p in values) and len(set(values))==len(values) else []


class TrackMap:
    """Approximate path from a complete driven lap, projected by SDK progress.

    No opponent world coordinates exist in this transport. Speed/yaw integration
    avoids depending on legacy GPS variables; these maps are visibly estimates.
    """
    def __init__(self,directory,key,length):
        self.rows=[];self.partial={};self.previous=None;self.position=[0.,0.];self.eligible=False
        self.length=length;self.source='server speed/yaw integration; approximate driven line'
        self.error=None;self.file=directory/('track-'+hashlib.sha256(key.encode()).hexdigest()[:24]+'.json')
        try:
            saved=json.loads(self.file.read_text());rows=saved['rows']
            if saved.get('key')==key and 10<len(rows)<=1252 and rows[0][0]==0 and rows[-1][0]==1:
                for row in rows:
                    if len(row)!=3:raise ValueError()
                    for value in row:number(value)
                if any(a[0]>=b[0] for a,b in zip(rows,rows[1:])):raise ValueError()
                self.rows=rows
        except (OSError,ValueError,KeyError,TypeError):pass
        self.key=key
    def update(self,now,lap,pct,speed,yaw,in_pit):
        if self.rows:return
        previous=self.previous
        self.previous=(now,lap,pct,speed,yaw)
        if pct is None or speed is None or yaw is None or in_pit:
            self.partial={};self.eligible=False;return
        if previous is None:return
        dt=now-previous[0]
        if not 0<dt<=.25 or previous[2] is None or previous[3] is None or previous[4] is None:
            self.partial={};self.eligible=False;return
        average_speed=(speed+previous[3])/2
        angle=previous[4]+math.atan2(math.sin(yaw-previous[4]),math.cos(yaw-previous[4]))/2
        self.position[0]+=average_speed*math.cos(angle)*dt
        self.position[1]-=average_speed*math.sin(angle)*dt
        if lap==previous[1]+1 and previous[2]>.95 and pct<.05:
            if self.eligible and len(self.partial)>80:
                rows=sorted(self.partial.values(),key=lambda row:row[0])
                start=rows[0];end=self.position
                drift=math.dist(start[1:],end)
                if rows[0][0]<.015 and rows[-1][0]>.95 and drift<max(30,self.length*.03):
                    dx,dz=end[0]-start[1],end[1]-start[2]
                    self.rows=[[p,x-start[1]-p*dx,z-start[2]-p*dz] for p,x,z in rows]
                    self.rows[0]=[0,0,0];self.rows.append([1,0,0])
                    try:
                        temporary=self.file.with_suffix('.tmp');temporary.write_text(json.dumps({'key':self.key,'rows':self.rows},allow_nan=False));temporary.replace(self.file)
                    except OSError:self.error='map-write-failed'
                    return
            self.partial={0:[0,*self.position]};self.eligible=pct<.015
        elif lap!=previous[1] or pct<previous[2] or pct-previous[2]>.05:
            self.partial={};self.eligible=False
        if self.eligible:self.partial[min(1249,int(pct*1250))]=[pct,*self.position]
    def at(self,pct):
        if pct is None or not self.rows:return None
        index=max(1,min(len(self.rows)-1,bisect.bisect_right([row[0] for row in self.rows],pct)))
        a,b=self.rows[index-1:index+1];ratio=(pct-a[0])/(b[0]-a[0])
        return [a[1]+(b[1]-a[1])*ratio,a[2]+(b[2]-a[2])*ratio]
    def presentation(self,starts):
        points=[row[1:] for row in self.rows] if self.rows else [row[1:] for row in sorted(self.partial.values())]
        indices=[min(range(len(self.rows)),key=lambda i:abs(self.rows[i][0]-p)) for p in starts[1:]] if self.rows and len(starts)==3 else None
        geometry={'indices':indices,'source':'iRacing SplitTimeInfo boundaries on approximate recorded path'} if indices and 0<indices[0]<indices[1]<len(points)-1 else None
        return {'points':points,'status':'recorded' if self.rows else 'recording','source':self.source,
                'approximate':True,'sectorGeometry':geometry,'storageError':self.error}


class Sectors:
    def __init__(self):self.previous=None;self.current=None;self.last=[None]*3;self.best=[None]*3;self.history=[]
    def update(self,now,lap,pct,elapsed,starts,clean,in_pit):
        if len(starts)!=3 or pct is None or elapsed is None:return None
        sector=bisect.bisect_right(starts,pct)-1
        previous=self.previous;self.previous=(now,lap,pct,elapsed,sector)
        if self.current is None:self.current={'lap':lap,'times':[None]*3,'eligible':False,'clean':clean,'inPit':in_pit,'reference':self.best[:],'lapStart':now-elapsed}
        current=self.current
        if previous and 0<now-previous[0]<=.25:
            if lap==previous[1] and sector==previous[4]+1 and pct>previous[2]:
                crossing=previous[3]+(elapsed-previous[3])*(starts[sector]-previous[2])/(pct-previous[2])
                prior=current['times'][:sector-1]
                if all(value is not None for value in prior):current['times'][sector-1]=crossing-sum(prior)
            elif lap==previous[1]+1 and previous[2]>.95 and pct<.05:
                total=previous[3]+(now-previous[0])*(1-previous[2])/(1+pct-previous[2])
                if all(value is not None for value in current['times'][:2]):current['times'][2]=total-sum(current['times'][:2])
                if current['eligible'] and all(value is not None and value>0 for value in current['times']):
                    self.last=current['times'][:]
                    entry={'lap':current['lap'],'lapStart':current['lapStart'],'sectors':self.last[:],'total':sum(self.last),
                           'valid':None,'inPit':current['inPit'],'status':'estimated','reference':current['reference'],
                           'observedClean':current['clean'] and clean}
                    self.history=(self.history+[entry])[-200:]
                    if entry['observedClean'] and not entry['inPit']:
                        self.best=[min(a,b) if a is not None else b for a,b in zip(self.best,self.last)]
                self.current={'lap':lap,'times':[None]*3,'eligible':pct<.015,'clean':clean,'inPit':in_pit,'reference':self.best[:],'lapStart':now-elapsed}
                current=self.current
            elif lap!=previous[1] or pct<previous[2]:self.current=None;return None
        elif previous:
            self.current=None;return None
        current['clean'] &= clean;current['inPit'] |= in_pit
        done=current['times'];offset=sum(done[:sector]) if all(v is not None for v in done[:sector]) else None
        delta=[v-r if v is not None and r is not None and current['eligible'] and current['clean'] and not current['inPit'] else None for v,r in zip(done,current['reference'])]
        return {'lap':lap,'currentSector':sector+1,'elapsed':max(0,elapsed-offset) if offset is not None else None,
                'current':done[:],'last':self.last[:],'best':self.best[:],'delta':delta,'reference':current['reference'],
                'comparisonLap':[lap]*3,'history':self.history,'valid':None,'storageError':None,
                'source':'Estimated SDK lap-progress crossings, nominal 20 Hz; not official split times'}


def flags(values,idx):
    raw=int(values.get('SessionFlags') or 0)
    personal=values.get('CarIdxSessionFlags')
    own=int(personal[idx] or 0) if isinstance(personal,list) and 0<=idx<len(personal) else raw
    bits=raw|own
    code=('stopped' if bits&0x10 else 'black' if bits&0x30000 else 'repair' if bits&0x100000 else
          'finished' if bits&1 else 'caution' if bits&0xc000 else 'yellow' if bits&0x108 else
          'white' if bits&2 else 'green' if bits&0x80000404 else 'starting' if bits&0x60000000 else 'waiting')
    return {'session':code,'pilotBlue':bool(bits&0x20),'rawBits':raw,'pilotBits':own,'rawChannels':[],
            'sectorFlags':['unknown']*3,'channelOrder':'not-provided-by-iracing',
            'source':'iRacing SessionFlags and player CarIdxSessionFlags'}


class IRacingEngine:
    def __init__(self, directory=None):
        from .compute import Engine
        from .overlays import catalog
        self.sampler=Engine();self.catalog=catalog();self.directory=Path(directory or os.environ.get('SPOTTER_STATE_DIR',Path.home()/'.local/share/RemoteSpotterServer'))/'iracing'
        self.directory.mkdir(parents=True,exist_ok=True)
        self.key=None;self.seq=-1;self.time=None;self.encoded=None;self.metadata={};self.mapping=None;self.sectors=Sectors();self.traces=[];self.incidents=None;self.pilot_id=None
    def update(self,frame):
        snapshot=validate(frame)
        metadata=decode_metadata(snapshot['sessionData']) if snapshot and snapshot['sessionData']!=self.encoded else self.metadata
        length=meta_number(metadata.get('WeekendInfo',{}).get('TrackLength'),0)*1000
        if not 0<=length<=100000:raise ValueError('Invalid iRacing track length')
        key=(frame['streamId'],frame['sessionId'])
        if key==self.key and frame['seq']<=self.seq:raise ValueError('Out-of-order sequence')
        if key!=self.key:
            self.sampler.reset_history();self.mapping=None;self.sectors=Sectors();self.traces=[];self.incidents=None;self.pilot_id=None;self.time=None
            self.encoded=None;self.metadata={}
            if snapshot:metadata=decode_metadata(snapshot['sessionData'])
        discontinuity=self.time is not None and (frame['seq']!=self.seq+1 or not 0<=frame['gameTime']-self.time<=.25)
        self.key=key;self.seq=frame['seq'];self.time=frame['gameTime']
        if snapshot:self.encoded=snapshot['sessionData'];self.metadata=metadata
        values=snapshot['values'] if snapshot else {};now=frame['gameTime'];live=frame['status']=='live'
        weekend=metadata.get('WeekendInfo',{});driver_info=metadata.get('DriverInfo',{})
        track=str(weekend.get('TrackDisplayName') or weekend.get('TrackName') or 'iRacing')[:128]
        starts=sector_starts(metadata)
        map_key=json.dumps([weekend.get('TrackID'),weekend.get('TrackConfigName'),track,length])
        if self.mapping is None or self.mapping.key!=map_key:self.mapping=TrackMap(self.directory,map_key,length)
        idx=int(values['PlayerCarIdx']) if values.get('PlayerCarIdx') is not None else -1;drivers=driver_info.get('Drivers',[])
        def array(name,index,default=None):
            value=values.get(name);return value[index] if isinstance(value,list) and 0<=index<len(value) else default
        def progress(index):return num(array('CarIdxLapDistPct',index),-1,1)
        cars=[]
        for driver in drivers:
            car_idx=int(meta_number(driver.get('CarIdx')))
            if str(driver.get('CarIsPaceCar','0')).lower() in ('1','true'):continue
            pct=progress(car_idx);pct=pct if pct is not None and pct>=0 else None
            surface=array('CarIdxTrackSurface',car_idx,-1)
            position=int(array('CarIdxPosition',car_idx,0) or 0)
            laps=int(array('CarIdxLapCompleted',car_idx,0) or 0)
            if not 0<=position<=128 or not -1<=laps<=100000:raise ValueError('Invalid SDK scoring')
            cars.append({'id':car_idx,'driver':str(driver.get('UserName',''))[:128],
                'class':str(driver.get('CarClassShortName') or driver.get('CarClassID') or 'Unknown')[:128],
                'classId':str(driver.get('CarClassID','')),'number':str(driver.get('CarNumber',''))[:8],
                'place':position,'classPlace':int(array('CarIdxClassPosition',car_idx,0) or 0),
                'laps':max(0,laps),'lapDistM':pct*length if pct is not None else None,'lapProgress':pct,
                'inPit':bool(array('CarIdxOnPitRoad',car_idx,False)) or surface==1,'inWorld':surface!=-1,
                'speedMps':values.get('Speed') if car_idx==idx else None,
                'lastLapTime':num(array('CarIdxLastLapTime',car_idx),-1,100000),
                'bestLapTime':num(array('CarIdxBestLapTime',car_idx),-1,100000),
                'positionSource':'iRacing SDK; map coordinates projected from lap progress'})
        own=next((car for car in cars if car['id']==idx),None)
        if idx!=self.pilot_id or discontinuity or not live:
            self.sampler.reset_history();self.sectors=Sectors();self.traces=[]
        self.pilot_id=idx
        pilot=None;timing=None;fuel={'status':'unavailable','consumptionLPerLap':None,'lapsRemaining':None}
        incidents=values.get('PlayerCarMyIncidentCount')
        clean=values.get('PlayerTrackSurface') not in (-1,0,1) and (self.incidents is None or incidents==self.incidents)
        self.incidents=incidents
        if own and values.get('IsOnTrackCar',values.get('IsOnTrack')) and frame['status'] not in ('waitingForGame','paused'):
            lap=int(values.get('Lap',0));elapsed=num(values.get('LapCurrentLapTime'),-1,100000)
            pilot={'id':idx,'lap':lap,'fuelL':values.get('FuelLevel'),'speedMps':values.get('Speed'),
                'speedKph':values['Speed']*3.6 if values.get('Speed') is not None else None,
                'gear':values.get('Gear'),'rpm':values.get('RPM'),'throttle':values.get('Throttle'),
                'brake':values.get('Brake'),'clutch':values.get('Clutch'),'lapValid':None,'lapValiditySource':'not-reported',
                'wheels':[]}
            for wheel in ('LF','RF','LR','RR'):
                temps=[num(values.get(wheel+'tempC'+p),-100,500) for p in ('L','M','R')]
                wears=[num(values.get(wheel+'wear'+p),0,1) for p in ('L','M','R')]
                valid_temp=all(v is not None for v in temps) and any(v>0 for v in temps)
                valid_wear=all(v is not None for v in wears) and (any(v>0 for v in wears) or valid_temp)
                pressure=num(values.get(wheel+'pressure'),0,1000)
                pressure=pressure if pressure and pressure>0 else None
                pilot['wheels'].append({'temperatureC':statistics.fmean(temps) if valid_temp else None,
                    'wear':statistics.fmean(wears) if valid_wear else None,'pressureKpa':pressure,
                    'brakeC':None,'carcassTemperaturesC':temps if valid_temp else [None]*3,
                    'temperatureSource':'carcass; SDK pit snapshot',
                    'status':'pit-snapshot' if valid_temp or valid_wear or pressure is not None else 'unavailable'})
            if live:
                if pilot['fuelL'] is not None:
                    self.sampler.update_fuel({**pilot,'lapValid':clean},own,now)
                    avg=statistics.fmean(self.sampler.history) if self.sampler.history else None
                    fuel={'status':'estimated' if avg else 'warming-up','consumptionLPerLap':avg,
                          'lapsRemaining':pilot['fuelL']/avg if avg else None,'completedSamples':len(self.sampler.history),
                          'method':'Server complete-lap sampling; excludes pits, observed incidents and stream gaps'}
                pct=own['lapProgress']
                if discontinuity:self.mapping.previous=None;self.mapping.eligible=False;self.mapping.partial={}
                self.mapping.update(now,lap,pct,pilot['speedMps'],num(values.get('Yaw'),-1000,1000),own['inPit'] or not clean or not own['inWorld'])
                timing=self.sectors.update(now,lap,pct,elapsed if elapsed is not None and elapsed>=0 else None,starts,clean,own['inPit'])
                angle=num(values.get('SteeringWheelAngle'),-100,100);maximum=num(values.get('SteeringWheelAngleMax'),0,100)
                steer=angle/(maximum/2) if angle is not None and maximum else None
                self.traces=(self.traces+[[now,pilot['throttle'],pilot['brake'],pilot['clutch'],steer]])[-200:]
        for car in cars:
            point=self.mapping.at(car['lapProgress']) if car['inWorld'] else None
            car.update(x=point[0] if point else None,z=point[1] if point else None,mapVisible=point is not None)
            # F2Time is the SDK's session-type-aware relative time to the leader.
            car['gapBehindLeader']=num(array('CarIdxF2Time',car['id']),-100000,100000)
            car['relativeGap']=None
            if own and car['lapProgress'] is not None and own['lapProgress'] is not None:
                pace=own['lastLapTime'] if own['lastLapTime'] and own['lastLapTime']>0 else num(values.get('LapBestLapTime'),-1,100000)
                if pace and pace>0:
                    d=(car['lapProgress']-own['lapProgress']+.5)%1-.5
                    car['relativeGap']=d*pace;car['relativeGapSource']='estimated progress difference × player lap pace'
        cars.sort(key=lambda car:car['place'] or 999)
        trackmap=self.mapping.presentation(starts)
        api={}
        def put(key,value,label=None,status='live'):
            api['api.'+key]={'value':value,'label':label or key,'status':status if value is not None else 'unavailable','source':'iRacing SDK / server adapter'}
        for key,name in {'inputs.throttle':'Throttle','inputs.brake':'Brake','inputs.clutch':'Clutch','engine.rpm':'RPM',
            'engine.water_temperature':'WaterTemp','engine.oil_temperature':'OilTemp','switch.tc_level':'dcTractionControl',
            'switch.abs_level':'dcABS','switch.speed_limiter':'dcPitSpeedLimiter','switch.drs_status':'dcDRS',
            'session.ambient_temperature':'AirTemp','session.track_temperature':'TrackTempCrew','session.raininess':'Precipitation',
            'session.remaining':'SessionTimeRemain','session.track_time':'SessionTimeOfDay','timing.current_laptime':'LapCurrentLapTime'}.items():put(key,values.get(name))
        angle=values.get('SteeringWheelAngle');maximum=values.get('SteeringWheelAngleMax')
        put('inputs.steering',angle/(maximum/2) if angle is not None and maximum else None,'Steering (fraction)')
        put('inputs.steering_range_physical',math.degrees(maximum) if maximum else None,'Steering range (degrees)')
        put('engine.rpm_max',meta_number(driver_info.get('DriverCarSLBlinkRPM')))
        put('engine.fuel',pilot['fuelL'] if pilot else None,'Fuel (liters)')
        put('vehicle.speed',values.get('Speed'),'Speed (meters/sec)');put('engine.gear',values.get('Gear'))
        put('timing.elapsed',now,'Session elapsed (seconds)')
        put('timing.best_laptime',values.get('LapBestLapTime'),'Best lap (seconds)')
        put('lap.number',values.get('Lap'));put('lap.progress',values.get('LapDistPct'))
        put('lap.remaining',values.get('SessionLapsRemain'))
        put('vehicle.place',own['place'] if own else None);put('vehicle.total_vehicles',len(cars))
        put('vehicle.class_name',own['class'] if own else None);put('vehicle.in_pits',own['inPit'] if own else None)
        sessions=metadata.get('SessionInfo',{}).get('Sessions',[])
        active_session=next((row for row in sessions if isinstance(row,dict) and meta_number(row.get('SessionNum'))==values.get('SessionNum')),{}) if isinstance(sessions,list) else {}
        put('session.session_type',active_session.get('SessionType'))
        put('session.in_race',active_session.get('SessionType')=='Race' if active_session else None)
        flag_data=flags(values,idx) if snapshot else None
        put('session.blue_flag',flag_data['pilotBlue'] if flag_data else None)
        put('session.yellow_flag',flag_data['session'] in ('yellow','caution') if flag_data else None)
        put('vehicle.repair_time',values.get('PitRepairLeft'),'Repair (seconds)')
        for name in ('throttle','brake','clutch','steering'):
            put('inputs.'+name+'_raw',api['api.inputs.'+name]['value'],name+' (fraction)')
        wheel_data=(pilot or {}).get('wheels',[])
        put('tyre.carcass_temperature',[wheel['temperatureC'] for wheel in wheel_data] or None,'Carcass temperature (Celsius)','pit-snapshot')
        put('tyre.carcass_temperature_ico',[v for wheel in wheel_data for v in wheel['carcassTemperaturesC']] or None,'Carcass left / middle / right (Celsius)','pit-snapshot')
        put('tyre.pressure',[wheel['pressureKpa'] for wheel in wheel_data] or None,'Tyre pressure (kPa)','pit-snapshot')
        modules={'delta':{'lapTimeCurrent':values.get('LapCurrentLapTime'),'lapTimeLast':values.get('LapLastLapTime'),
            'lapTimeBest':values.get('LapBestLapTime'),'lapTimeSession':values.get('LapBestLapTime'),'deltaSession':values.get('LapDeltaToSessionBestLap') if values.get('LapDeltaToSessionBestLap_OK') else None,
            'lapTimeEstimated':None},'force':{'latGForceRaw':values['LatAccel']/9.80665 if values.get('LatAccel') is not None else None,
            'lgtGForceRaw':values['LongAccel']/9.80665 if values.get('LongAccel') is not None else None},'history':{'stintDataSet':[]},
            'fuel':{'amountCurrent':pilot['fuelL'] if pilot else None,'capacity':meta_number(driver_info.get('DriverCarFuelMaxLtr')),
                'estimatedConsumption':fuel['consumptionLPerLap'],'estimatedValidConsumption':fuel['consumptionLPerLap'],
                'estimatedLaps':fuel['lapsRemaining']},
            'wheels':{'currentTreadDepth':[wheel['wear']*100 if wheel['wear'] is not None else None for wheel in wheel_data] or None}}
        for group,fields in modules.items():
            for key,value in fields.items():api['module.'+group+'.'+key]={'value':value,'label':key,'status':'live' if value is not None else 'unavailable'}
        supported=set('flag laps_and_position relative standings track_map pedal instrument gear speedometer engine engine_temperature force friction_circle steering_angle steering_meter steering_wheel trailing timing sectors session track_clock weather fuel deltabest rpm_led tyre_temperature tyre_carcass tyre_pressure tyre_wear'.split())
        capabilities={item['id']:{'status':('pit-only' if item['id'].startswith('tyre_') else 'partial') if item['id'] in supported else 'unsupported',
            'reason':'iRacing does not expose an equivalent channel in this adapter','missing':[]} for item in self.catalog}
        race=[{**car,'index':car['id'],'isPlayer':car['id']==idx,'driverName':car['driver'],
            'positionOverall':car['place'],'vehicleClass':car['class'],'lapTimeHistory':[]} for car in cars]
        overlay={'source':'iracing','catalog':self.catalog,'capabilities':capabilities,'values':api,'race':race,'modules':modules,
            'widgetMath':{'trailing':{'samples':self.traces},'steering_angle':{'degrees':math.degrees(angle) if angle is not None else None},
                'tyre_temperature':{'Carcass (Celsius)':[wheel['temperatureC'] for wheel in wheel_data]}},
            'flags':flag_data,'proximity':{'leftRight':values.get('CarLeftRight'),'source':'CarLeftRight; no metric distances'},'sectorTiming':timing,'trackmap':trackmap,'moduleErrors':{},
            'finish':{'status':'unavailable','fuel':None,'energy':None,'pitStopsFuel':None,'pitStopsEnergy':None,
                      'finishAsLap':None,'timeOffset':None,'lapOffset':None},'pit':{'status':'sdk','repairSeconds':values.get('PitRepairLeft'),
            'optionalRepairSeconds':values.get('PitOptRepairLeft')},'restAvailable':[],'restErrors':{}}
        return {'type':'presentation','protocolVersion':1,'mode':'iracing','game':'iracing','status':frame['status'],
            **{key:frame[key] for key in ('streamId','sessionId','seq','capturedAt','gameTime')},
            'session':{'track':track,'lengthM':length,'scoringTime':now,'phase':values.get('SessionState',0),
                       'maxLaps':0,'game':'iracing','sectorCount':len(starts)},'cars':cars,'pilot':pilot,'fuel':fuel,
            'strategy':{'status':'iracing-basic','fuel':None,'energy':None,'finishPrediction':None},'overlays':overlay,
            'overlayError':None,'trackmap':trackmap,'compute':{'headless':True,'adapter':'iRacing SDK','overlaysReady':True,
                'limitations':['map-projected-by-lap-progress','no-opponent-coordinate-radar','sector-times-estimated','tyres-pit-snapshot','no-LMU-virtual-energy']}}
