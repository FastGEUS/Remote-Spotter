"""Server presentation model for the complete upstream widget inventory.

Sensor values use the original LMU reader; stateful values use original data
modules. Web views deliberately keep their own layouts. Desktop widget option
parity is recorded separately instead of being inferred from a visible card.
"""
import ast
import inspect
import math
import time
import textwrap
from array import array
from collections import deque
from collections.abc import Mapping
from .headless import Runtime
from .reader import Reader
from .snapshot import decode
from .inventory import chain
from .upstream import ROOT

GROUPS = {
 'Гонка и трафик':'flag laps_and_position relative relative_finish_order rivals standings traffic radar track_map navigation',
 'Круги и темп':'deltabest deltabest_extended lap_time_history sectors timing session',
 'Стратегия':'fuel virtual_energy fuel_energy_saver pit_stop_estimate stint_history lift_and_coast_led battery electric_motor',
 'Машина':'gear speedometer instrument engine engine_temperature brake_bias brake_pressure brake_temperature brake_wear brake_performance damage damage_stats drs push_to_pass onboard_setting rpm_led cruise',
 'Шины':'tyre_temperature tyre_pressure tyre_wear tyre_carcass tyre_inner_layer tyre_deflection tyre_load slip_angle slip_ratio wheel_camber wheel_toe',
 'Шасси и управление':'acceleration differential force friction_circle heading pedal rake_angle ride_height roll_angle steering_angle steering_meter steering_wheel suspension_force suspension_position suspension_travel weight_distribution trailing',
 'Трасса и условия':'elevation weather weather_forecast track_clock pace_notes track_notes system_performance',
}
GROUP_MAP = {key:group for group,keys in GROUPS.items() for key in keys.split()}
MODULE_LABELS = {
 'wheels.currentTreadDepth':'Состояние шин (percent remaining; 100 = new)',
 'wheels.currentLapTreadWear':'Износ за круг (percent)',
 'wheels.estimatedTreadWear':'Оценка износа за круг (percent)',
 'wheels.estimatedValidTreadWear':'Износ за валидный круг (percent)',
 'wheels.lockingTreadWear':'Износ от блокировки (percent)',
 'delta.lapTimePace':'Темп (seconds)',
 'delta.lapTimeCurrent':'Текущий круг (seconds)',
 'delta.lapTimeLast':'Последний круг (seconds)',
 'delta.deltaBest':'Дельта к лучшему (seconds)',
 'delta.deltaLast':'Дельта к предыдущему (seconds)',
 'fuel.estimatedLaps':'Запас топлива (круги)',
 'energy.estimatedLaps':'Запас энергии (круги)',
 'force.latGForceRaw':'Поперечная перегрузка (G)',
 'force.lgtGForceRaw':'Продольная перегрузка (G)',
}


def json_value(value,limit=104,depth=0):
    if depth>8:
        return None
    if value is None or isinstance(value,(bool,str,int)):
        return value
    if isinstance(value,float):
        return value if math.isfinite(value) and abs(value)<1e8 else None
    if isinstance(value,Mapping):
        return {str(k):json_value(v,limit,depth+1) for k,v in value.items()}
    if isinstance(value,tuple) and hasattr(value,'_asdict'):
        return json_value(value._asdict(),limit,depth)
    if isinstance(value,(list,tuple,array,deque)):
        return [json_value(v,limit,depth+1) for v in list(value)[-limit:]]
    if hasattr(value,'__slots__'):
        return {k:json_value(getattr(value,k),limit,depth+1) for k in value.__slots__ if not k.startswith('_') and hasattr(value,k)}
    return None


def catalog(runtime=None):
    keys = runtime.load('template.setting_widget').WIDGET_DEFAULT if runtime else GROUP_MAP
    output = []
    for name in sorted(keys):
        tree = ast.parse((ROOT/'tinypedal/widget'/f'{name}.py').read_text())
        calls = {chain(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)}
        apis = sorted(c[9:] for c in calls if c.startswith('api.read.'))
        paths = {chain(n) for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        modules = sorted(p[6:] for p in paths if p.startswith('minfo.') and p.count('.')>=2)
        modules = [p for p in modules if not any(other.startswith(p+'.') for other in modules)]
        output.append({'id':name,'name':name.replace('_',' ').title(),'group':GROUP_MAP[name],
                       'api':apis,'modules':modules,'source':f'tinypedal/widget/{name}.py',
                       'parity':'web-data-port; desktop presentation/options not identical'})
    return output


class OverlayEngine:
    def __init__(self,state_dir=None):
        self.runtime = Runtime(state_dir)
        self.reader = Reader(self.runtime)
        from .widget_math import WidgetMath
        self.widget_math = WidgetMath(self.runtime)
        from .pit_map import PitMap
        self.pit_map = PitMap(self.runtime)
        from .sectors import SectorTiming
        self.sector_timing = SectorTiming(self.runtime.cfg.directory)
        self.catalog = catalog(self.runtime)
        self.api_keys = sorted({k for widget in self.catalog for k in widget['api']})
        self.functions = {}
        for key in self.api_keys:
            group,method = key.split('.',1)
            func = getattr(getattr(self.reader,group),method)
            if any(p.default is inspect.Parameter.empty for p in inspect.signature(func).parameters.values()):
                continue
            tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
            required = {n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Attribute) and n.value.attr=='rest'}
            self.functions[key] = (func,(inspect.getdoc(func) or key).split('\n')[0],required)
        self.module_keys = sorted({k for widget in self.catalog for k in widget['modules']})
        self.started = time.monotonic()

    def close(self):
        self.runtime.close()

    def reset(self):
        # A delivery gap invalidates samples, not compiled upstream modules.
        # Reimporting all modules on every missed frame causes a feedback loop:
        # slow initialization -> another gap -> another slow initialization.
        self.runtime.state.resets += 1
        self.runtime.last.clear()
        self.sector_timing.current = self.sector_timing.pending = None
        self.sector_timing.last_comparison = None

    def update(self,frame):
        if frame['mode']=='demo':
            from .demo_snapshot import build
            data = build(frame)
        else:
            data = decode(frame['rawSnapshot'])
        self.reader.update(data,frame)
        info = self.runtime.advance(self.reader,frame['gameTime'],frame['status']=='live')
        values = {}
        for key,(func,label,required_rest) in self.functions.items():
            try:
                raw = func()
                doc = label
                status = 'live'
                if required_rest-self.reader.rest_available:
                    status = 'rest-unavailable'
                    raw = None
                if key in ('lap.safety_car_distance','lap.safety_car_active','switch.auto_clutch'):
                    status = 'not-provided-by-lmu'
                    raw = None
                if key=='tyre.wear':
                    raw = [w*100 for w in raw]
                    doc = 'Tyre condition (percent remaining; 100 = new)'
                values['api.'+key] = {'value':json_value(raw),'label':doc.split('\n')[0], 'status':status}
            except Exception as error:
                values['api.'+key] = {'value':None,'label':key,'status':'unavailable','reason':type(error).__name__}
        for key in self.module_keys:
            obj = info
            try:
                for attr in key.split('.'):
                    obj = getattr(obj,attr)
                if callable(obj):
                    continue
                value = json_value(obj)
                status = 'live'
                if key.startswith(('fuel.estimated','fuel.needed','energy.estimated','energy.needed')):
                    resource = info.fuel if key.startswith('fuel.') else info.energy
                    if resource.estimatedValidConsumption<=0:
                        value,status = None,'warming-up'
                values['module.'+key] = {'value':value,'label':MODULE_LABELS.get(key,key),'status':status}
            except AttributeError:
                pass  # Index-dependent attributes come from structured race data.
        race = []
        # Relative is (gap,index); invert explicitly, including negative behind.
        relative = {index:gap for gap,index in info.relative.relativeAhead+info.relative.relativeBehind if index>=0}
        for index in range(info.vehicles.totalVehicles):
            v = info.vehicles.dataSet[index]
            item = json_value(v,30)
            item['id'] = self.reader.shmm.lmuScorVeh(index).mID
            item['index'] = index
            item['relativeGap'] = relative.get(index)
            race.append(item)
        for key in ('vehicles.dataSet','relative.relativeDeltaAhead','relative.relativeDeltaBehind'):
            values.pop('module.'+key,None)
        ready = info.delta.lapTimePace>0 and info.fuel.estimatedValidConsumption>0
        fuel = json_value(info.fuel)
        energy = json_value(info.energy)
        finish = {'status':'estimated' if ready else 'warming-up','fuel':fuel if ready else None,'energy':energy if ready and info.energy.available else None,
                  'finishAsLap':info.vehicles.finishAsLap,'timeOffset':info.vehicles.finishTimeOffset,'lapOffset':info.vehicles.finishLapOffset}
        finish['pitStopsFuel'] = math.ceil(info.fuel.estimatedNumPitStopsEnd) if ready else None
        finish['pitStopsEnergy'] = math.ceil(info.energy.estimatedNumPitStopsEnd) if ready and info.energy.available else None
        pit = {'stopSeconds':self.reader.rest.pitStopTime if 'pitStopTime' in self.reader.rest_available else None,
               'repairSeconds':self.reader.rest.repairTime if 'repairTime' in self.reader.rest_available else None,
               'passSeconds':info.mapping.pitPassTime or None,'entryM':info.mapping.pitEntryPosition or None,'exitM':info.mapping.pitExitPosition or None,
               'status':'estimated' if info.mapping.pitPassTime>0 and 'pitStopTime' in self.reader.rest_available else 'needs-pit-calibration-or-rest'}
        pit['totalSeconds'] = pit['stopSeconds']+pit['passSeconds'] if pit['stopSeconds'] is not None and pit['passSeconds'] else None
        pit['exitTraffic'] = sorted([{'id':v['id'],'driver':v['driverName'],'gapAfterStop':v['relativeGap']+pit['totalSeconds']} for v in race if v['relativeGap'] is not None and not v['inPit']],key=lambda v:abs(v['gapAfterStop']))[:5] if pit['totalSeconds'] else []
        available = frame['status']=='live'
        capabilities = {}
        for widget in self.catalog:
            inputs = [values.get('api.'+k) for k in widget['api']]+[values.get('module.'+k) for k in widget['modules']]
            present = [v for v in inputs if v and v['value'] is not None and v['status']=='live']
            capabilities[widget['id']] = {'status':'live' if present and available else 'waiting','missing':[k for k in widget['api'] if values.get('api.'+k,{}).get('value') is None]}
        mapping = info.mapping
        trackmap = {'points':[[x,-y] for x,y in mapping.coordinates] if mapping.coordinates else [],'status':'recorded' if mapping.coordinates else 'recording',
                    'pitLanePoints':self.pit_map.update(self.reader),
                    'elevations':mapping.elevations or [],
                    'source':'TinyPedal MappingModule; persistent original SVG format','sectors':mapping.sectors,'pitEntryM':mapping.pitEntryPosition,'pitExitM':mapping.pitExitPosition}
        from .sectors import flag_state, geometry
        trackmap['sectorGeometry'] = geometry(trackmap['points'], mapping.sectors)
        return {'catalog':self.catalog,'values':values,'capabilities':capabilities,'race':race,
                'flags':flag_state(self.reader, frame['mode']=='demo'),
                'sectorTiming':self.sector_timing.update(self.reader, frame, info),
                'widgetMath':json_value(self.widget_math.update(self.reader)),
                'modules':{key:json_value(getattr(info,key),200) for key in ('delta','fuel','energy','force','wheels','hybrid','sectors','history')},
                'finish':finish,'pit':pit,'trackmap':trackmap,'moduleErrors':dict(self.runtime.errors),
                'restAvailable':sorted(self.reader.rest_available),'restErrors':dict(self.reader.rest_errors)}
