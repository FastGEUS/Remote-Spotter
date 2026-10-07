"""Frame-driven execution of TinyPedal's original fuel/energy generators.

DeltaModule and VehiclesModule have not been ported: lap pace uses the last
valid scoring lap, distance uses scoring; race-finish predictions are withheld.
No Qt, background thread, REST call or local pilot-side calculation is needed.
"""
import math
from functools import partial, wraps
from types import SimpleNamespace as NS
from .upstream import calculations, pure_module, fuel_functions, source_functions


class Strategy:
    def __init__(self):
        self.frame = None
        self.car = None
        self.valid_lap = True
        self.lap = None
        self.last_lap_valid = False
        self.energy_seen = False
        self.state = NS(active=True)
        self.fuel = pure_module("module_info").FuelInfo()
        self.energy = pure_module("module_info").FuelInfo()
        self.info = NS(delta=NS(lapTimePace=0, lapDistance=0),
                       vehicles=NS(finishAsLap=True, finishTimeOffset=0))
        p = lambda: self.frame["pilot"]
        inputs = lambda: p()["strategyInputs"]
        session = lambda: self.frame["session"]
        api = NS(name="Le Mans Ultimate", read=NS(
            engine=NS(tank_capacity=lambda: inputs()["fuelCapacityL"],
                      fuel=lambda: p()["fuelL"],
                      virtual_energy=lambda: inputs()["virtualEnergyFraction"]),
            session=NS(combo_name=lambda: session()["track"]+" - "+self.car["class"],
                       remaining=lambda: max(0,session()["endTime"]-session()["scoringTime"]),
                       finish_type=lambda override: int(session()["maxLaps"]<=999999 and session()["endTime"]<1)),
            timing=NS(start=lambda: inputs()["lapStartTime"],
                      elapsed=lambda: self.frame["gameTime"],
                      current_laptime=lambda: max(0,self.frame["gameTime"]-inputs()["lapStartTime"]),
                      last_laptime=lambda: inputs()["lastLapTime"] if self.last_lap_valid else 0),
            vehicle=NS(in_garage=lambda: inputs()["inGarage"],
                       in_pits=lambda: self.car["inPit"], speed=lambda: p()["speedMps"]),
            lap=NS(distance=lambda: self.car["lapDistM"],
                   completed_laps=lambda: self.car["laps"],
                   progress=lambda: calculations().lap_progress_distance(self.car["lapDistM"],session()["lengthM"]),
                   maximum=lambda: session()["maxLaps"])))
        const = pure_module("const_common")
        validator = source_functions("tinypedal/validator.py", {"wraps":wraps}, {"generator_init","valid_delta_raw"})
        self.functions = fuel_functions({
            "calc": calculations(), "ceil": math.ceil, "api": api,
            "realtime_state": self.state, "minfo": self.info,
            "API_RF2_NAME": pure_module("const_api").API_RF2_NAME,
            "DELTA_DEFAULT": const.DELTA_DEFAULT, "DELTA_ZERO": const.DELTA_ZERO,
            "FLOAT_INF": const.FLOAT_INF,
            "generator_init": validator["generator_init"],
            "valid_delta_raw": validator["valid_delta_raw"], "round6": partial(round,ndigits=6),
            "load_fuel_delta_file": lambda **kw: kw["defaults"],
            "save_fuel_delta_file": lambda **kw: None,
        })
        make = self.functions["calc_consumption"]
        self.fuel_gen = make(self.fuel,False,"",".fuel",5.0,0.75)
        self.energy_gen = make(self.energy,True,"",".energy",5.0,0.0)

    def update(self, frame, car):
        self.frame,self.car = frame,car
        p = frame["pilot"]
        values = p["strategyInputs"]
        if self.lap != p["lap"]:
            self.last_lap_valid = self.valid_lap if self.lap is not None else False
            self.valid_lap = True
            self.lap = p["lap"]
        self.valid_lap &= p["lapValid"] and not car["inPit"]
        self.info.delta.lapTimePace = values["lastLapTime"] if self.last_lap_valid else 0
        self.info.delta.lapDistance = car["lapDistM"]
        self.fuel_gen.send(1)
        self.fuel.available = values["fuelCapacityL"]>0
        self.energy_seen |= values["virtualEnergyFraction"]>0
        if self.energy_seen:
            self.energy_gen.send(1)
            self.energy.available = True
        return {"status":"active", "algorithm":"TinyPedal module_fuel.calc_consumption v2.50.0",
                "fuel": self.present(self.fuel, self.fuel.available,self.info.delta.lapTimePace),
                "energy": self.present(self.energy,self.energy_seen,self.info.delta.lapTimePace),
                "paceSource":"last valid scoring lap; DeltaModule pending",
                "finishPrediction":None,
                "limitations":["VehiclesModule finish offsets pending", "DeltaModule pace/distance sync pending", "No saved consumption profile"]}

    @staticmethod
    def present(output, available, pace):
        ready = available and output.estimatedValidConsumption>0
        return {"status":"ready" if ready else "warming-up" if available else "unavailable",
                "amount":output.amountCurrent if available else None,
                "capacity":output.capacity if available else None,
                "usedThisLap":output.amountUsedCurrent if available else None,
                "lastLapConsumption":output.lastLapConsumption if ready else None,
                "estimatedConsumption":output.estimatedValidConsumption if ready else None,
                "lapsRemaining":output.estimatedLaps if ready else None,
                "minutesRemaining":output.estimatedMinutes if ready and pace>0 else None,
                "deltaConsumption":output.deltaConsumption if ready else None,
                "endStintAmount":output.amountEndStint if ready else None}
