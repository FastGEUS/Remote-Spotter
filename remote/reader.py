"""Run the original LMU API reader over a validated remote snapshot."""
import ast
import logging
import math
from types import MappingProxyType, SimpleNamespace as NS
from .upstream import ROOT

logger = logging.getLogger(__name__)


class Shmm:
    def __init__(self,runtime):
        path = ROOT/'tinypedal/adapter/lmu_connector.py'
        tree = ast.parse(path.read_text())
        klass = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LMUResults')
        ns = {'MappingProxyType':MappingProxyType}
        exec(compile(ast.Module(body=[klass],type_ignores=[]),str(path),'exec'),ns)
        self.results = ns['LMUResults']()
        self.isActive = False
        self.isPaused = True
        self.vehicleResets = 0

    def update(self,data,frame):
        self.data = data
        self.lmuScorInfo = data.scoring.scoringInfo
        self.lmuGeneric = data.generic
        self.isActive = frame['status']=='live'
        self.isPaused = not self.isActive
        self.scoring = list(data.scoring.vehScoringInfo[:self.lmuScorInfo.mNumVehicles])
        self.telemetry = {t.mID:t for t in data.telemetry.telemInfo[:data.telemetry.activeVehicles]}
        pilot_id = frame['pilot']['id'] if frame.get('pilot') else -1
        self.playerIndex = next((i for i,v in enumerate(self.scoring) if v.mID==pilot_id),-1)
        if self.playerIndex<0 or pilot_id not in self.telemetry:
            raise ValueError('Player absent from raw scoring or telemetry')
        if set(v.mID for v in self.scoring) - self.telemetry.keys():
            raise ValueError('Scoring/telemetry roster not synchronized')
        self.results.update(data.scoring.scoringStream)

    def lmuScorVeh(self,index=None):
        return self.scoring[self.playerIndex if index is None else index]

    def lmuTeleVeh(self,index=None):
        return self.telemetry[self.lmuScorVeh(index).mID]

    def lmuResults(self,index=None):
        return self.results.data.get(self.lmuScorVeh(index).mDriverName,self.results.DEFAULT)


class Reader:
    def __init__(self,runtime):
        self.runtime = runtime
        self.shmm = Shmm(runtime)
        connector = runtime.load('adapter.lmu_restapi')
        self.rest = connector.RestAPIData()
        self.tasks = connector.lmu_restapi_tasks()
        self.rest_available = set()
        self.rest_errors = {}
        source = runtime.load('adapter.lmu_reader')
        groups = {'state':'State','brake':'Brake','emotor':'ElectricMotor','engine':'Engine','inputs':'Inputs','lap':'Lap','session':'Session','switch':'Switch','timing':'Timing','tyre':'Tyre','vehicle':'Vehicle','wheel':'Wheel'}
        for key,name in groups.items():
            setattr(self,key,getattr(source,name)(self.shmm,self.rest))
        # LMUWheel.mBrakeTemp is Celsius in the pinned S397 header. Upstream
        # lmu_reader subtracts 273.15 here; use the documented raw unit remotely.
        class BrakeC(source.Brake):
            def temperature(self,index=None):
                """Brake temperature (Celsius)"""
                return tuple(float(w.mBrakeTemp) if math.isfinite(w.mBrakeTemp) else 0 for w in self.shmm.lmuTeleVeh(index).mWheels)
        self.brake = BrakeC(self.shmm,self.rest)

    def update(self,data,frame):
        self.shmm.update(data,frame)
        # Upstream garage export reads api.read.vehicle during REST parsing.
        # Runtime.advance binds this too, but runs AFTER this update on frame 1.
        self.runtime.api.read = self
        self.rest_available.clear()
        previous_errors = self.rest_errors
        self.rest_errors = {}
        raw = frame.get('rest',{})
        if not isinstance(raw, dict):
            raw = {}
        for task in self.tasks:
            record = raw.get(task.path,{})
            captured = record.get('capturedAt') if isinstance(record, dict) else None
            fresh = (isinstance(captured, (int, float)) and not isinstance(captured, bool)
                     and 0 <= captured <= 1e14
                     and 0 <= frame['capturedAt']-captured <= 5000
                     and record.get('ok') is True and 'data' in record)
            for output in task.outputs:
                if not fresh:
                    output.reset(self.rest)
                    continue
                try:
                    if output.update(self.rest,record['data']):
                        self.rest_available.add(output.name)
                except Exception as error:
                    # Optional game REST payloads must not kill shared-memory
                    # telemetry, its worker, or the pilot WebSocket. Never retain
                    # an old successful value after this field fails to parse.
                    output.reset(self.rest)
                    kind = type(error).__name__
                    self.rest_errors[output.name] = kind
                    if previous_errors.get(output.name) != kind:
                        # Output names come from the pinned upstream task list;
                        # no REST bodies, credentials or local paths are logged.
                        logger.warning('REST field %s unavailable: %s; telemetry continues',
                                       output.name, kind)
