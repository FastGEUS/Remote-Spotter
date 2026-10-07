"""Widget-only calculations, kept on the VPS alongside the data modules."""
import ast
import math
import types
from collections import deque
from types import SimpleNamespace as NS
from .upstream import ROOT


class WidgetMath:
    def __init__(self,runtime):
        self.runtime = runtime
        self.calc = runtime.load('calculation')
        self.const = runtime.load('const_common')
        path = ROOT/'tinypedal/widget/acceleration.py'
        tree = ast.parse(path.read_text())
        timer = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AccelTimer')
        ns = {'MAX_SECONDS':self.const.MAX_SECONDS}
        exec(compile(ast.Module(body=[timer],type_ignores=[]),str(path),'exec'),ns)
        options = runtime.cfg.user.setting['acceleration']
        self.timers = [ns['AccelTimer'](options[f'speed_range_{i}_start'],options[f'speed_range_{i}_end'],max(options['speed_drop_threshold'],0)) for i in range(1,11) if options[f'speed_range_{i}_end']>0]
        # The traffic computation precedes all GUI updates in timerEvent. Reuse
        # that complete prefix unchanged, returning its output variables.
        path = ROOT/'tinypedal/widget/traffic.py'
        tree = ast.parse(path.read_text())
        widget = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Realtime')
        method = next(n for n in widget.body if isinstance(n,ast.FunctionDef) and n.name=='timerEvent')
        body = []
        for node in method.body:
            if any(isinstance(n,ast.Name) and n.id=='self' for n in ast.walk(node)):
                break
            body.append(node)
        keys = [f'{kind}_overtake_{metric}' for kind in ('ahead','behind','leader') for metric in ('laps','timegap','index')]
        body.append(ast.Return(ast.Dict(keys=[ast.Constant(k) for k in keys],values=[ast.Name(id=k,ctx=ast.Load()) for k in keys])))
        function = ast.FunctionDef(name='traffic',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=body,decorator_list=[])
        module = ast.Module(body=[function],type_ignores=[]);ast.fix_missing_locations(module)
        ns={'api':runtime.api,'minfo':runtime.info,'MAX_SECONDS':self.const.MAX_SECONDS}
        exec(compile(module,str(path),'exec'),ns)
        self.traffic = ns['traffic']
        self.finish_widget = self.make_finish_widget()
        self.traces = deque(maxlen=300)

    def methods(self,widget,names):
        path = ROOT/'tinypedal/widget'/f'{widget}.py'
        tree = ast.parse(path.read_text())
        klass = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Realtime')
        methods = [n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in names]
        ns={'api':self.runtime.api,'minfo':self.runtime.info,'MAX_SECONDS':self.const.MAX_SECONDS,'calc':self.calc,'ceil':math.ceil}
        exec(compile(ast.Module(body=methods,type_ignores=[]),str(path),'exec'),ns)
        return ns

    @staticmethod
    def numeric_target():
        return NS(last=-1,value=None)

    @staticmethod
    def capture(target,value,*args):
        target.last = value
        target.value = value

    def make_finish_widget(self):
        methods = self.methods('relative_finish_order',('timerEvent','create_pit_time_set','set_highlight_range'))
        wcfg = self.runtime.cfg.user.setting['relative_finish_order']
        widget = NS(wcfg=wcfg,range_start=max(wcfg['near_start_range'],0),range_finish=max(wcfg['near_finish_range'],0),total_slot=min(max(wcfg['number_of_prediction'],0),10)+3,extra_laps=max(wcfg['number_of_extra_laps'],1),relative_lap_offset=-self.const.MAX_SECONDS)
        for name in ('timerEvent','create_pit_time_set','set_highlight_range'):
            setattr(widget,name,types.MethodType(methods[name],widget))
        for name in ('update_pit_time','update_lap_player','update_lap_leader','update_energy_type','update_race_type','update_refill','update_lap_int'):
            setattr(widget,name,self.capture)
        widget.leader_pit_time_set=list(widget.create_pit_time_set(widget.total_slot,'leader'))
        widget.player_pit_time_set=list(widget.create_pit_time_set(widget.total_slot,'player'))
        for name in ('bars_pit_leader','bars_pit_player','bars_lap_player','bars_lap_leader','bars_refill','bars_refill_extra'):
            setattr(widget,name,[self.numeric_target() for _ in range(widget.total_slot)])
        return widget

    def update(self,reader):
        calc = self.calc
        info = self.runtime.info
        cfg = self.runtime.cfg.user.setting
        output = {}
        speed,time = reader.vehicle.speed(),reader.timing.elapsed()
        if not self.traces or self.traces[-1][0]!=time:
            self.traces.append([time,reader.inputs.throttle(),reader.inputs.brake(),reader.inputs.clutch(),reader.inputs.steering(),min(abs(min(info.wheels.slipRatio)),1),min(max(info.wheels.slipRatio),1)])
        for timer in self.timers:
            if reader.engine.gear()<0:
                timer.reset()
            timer.update(speed,time)
        output['acceleration'] = [{'rangeMps':[t.speed_start,t.speed_end],'elapsedSeconds':t.timer if t.start_time else t.valid if t.valid<self.const.MAX_SECONDS else None,'bestSeconds':t.best if t.best<self.const.MAX_SECONDS else None,'deltaSeconds':t.delta} for t in self.timers]
        height_fl,height_fr,height_rl,height_rr = reader.wheel.ride_height()
        output['rake_angle'] = {'angleDegrees':calc.slope_angle(calc.rake(height_fl,height_fr,height_rl,height_rr),cfg['rake_angle']['wheelbase']),'differenceMm':calc.rake(height_fl,height_fr,height_rl,height_rr)}
        output['roll_angle'] = {'frontDegrees':calc.slope_angle(height_fr-height_fl,cfg['roll_angle']['wheel_track_front']),'rearDegrees':calc.slope_angle(height_rr-height_rl,cfg['roll_angle']['wheel_track_rear'])}
        output['steering_angle'] = {'degrees':reader.inputs.steering()*reader.inputs.steering_range_physical()/2,'fraction':reader.inputs.steering()}
        output['traffic'] = self.traffic()
        output['rivals'] = {'aheadIndex':info.vehicles.dataSet[info.vehicles.playerIndex].classAheadIndex,'behindIndex':info.vehicles.dataSet[info.vehicles.playerIndex].classBehindIndex}
        output['lap_time_history'] = {'bestSeconds':info.vehicles.dataSet[info.vehicles.playerIndex].lapTimeHistory.best,'averageSeconds':info.vehicles.dataSet[info.vehicles.playerIndex].lapTimeHistory.average}
        output['trailing'] = {'columns':['timeSeconds','throttle','brake','clutch','steering','wheelLock','wheelSlip'],'samples':list(self.traces)}
        phase=reader.shmm.lmuScorInfo.mGamePhase
        output['flag'] = {'flag':'ФИНИШ' if phase==8 else 'СЕССИЯ ОСТАНОВЛЕНА' if phase==7 else 'FCY / SC' if phase==6 else 'ЖЁЛТЫЙ' if reader.session.yellow_flag() else 'СИНИЙ' if reader.session.blue_flag() else 'СТАРТ' if reader.session.pre_race() else 'ЗЕЛЁНЫЙ'}
        view_range=cfg['navigation']['view_radius']*2.5
        x,y=reader.vehicle.position_longitudinal(),reader.vehicle.position_lateral()
        yaw=reader.vehicle.orientation_yaw_radians()-math.pi
        segments=[];segment=[]
        for point in info.mapping.coordinates or ():
            if calc.distance(point,(x,y))<view_range:
                segment.append(calc.rotate_coordinate(yaw,point[0]-x,point[1]-y))
            elif segment:
                segments.append(segment);segment=[]
        if segment:segments.append(segment)
        output['navigation']={'rangeMeters':view_range,'roadSegments':segments}
        pace = info.delta.lapTimePace
        progress = reader.lap.progress()
        consumption = info.energy if info.energy.available else info.fuel
        scenarios = []
        widget = self.finish_widget
        widget.timerEvent(None)
        if pace>0 and consumption.estimatedValidConsumption>0:
            for index in range(1,widget.total_slot):
                def valid(value):
                    return value if value is not None and -self.const.MAX_SECONDS<value<self.const.MAX_SECONDS else None
                scenarios.append({'playerPitSeconds':widget.player_pit_time_set[index],'leaderPitSeconds':widget.leader_pit_time_set[index],
                                  'playerFinishLapFraction':valid(widget.bars_lap_player[index].value),'leaderFinishLapFraction':valid(widget.bars_lap_leader[index].value),
                                  'refillNeeded':valid(widget.bars_refill[index].value),'refillExtra':valid(widget.bars_refill_extra[index].value)})
        output['relative_finish_order'] = {'resource':'energy-percent' if info.energy.available else 'fuel-liters','scenarios':scenarios,'status':'estimated' if scenarios else 'warming-up'}
        return output
