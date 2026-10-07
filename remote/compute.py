"""Server-only calculations, driven by captured game time, never arrival time."""
import json
import faulthandler
import logging
import math
import statistics
import sys
import time
from .upstream import calculations

CALC = calculations()
MAX_CARS = 104  # pinned LMU structure limit


def number(value, low=-1e9, high=1e9):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("number out of range")
    return value


def integer(value, low=0, high=1000000000):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError("expected bounded integer")
    return value


def text(value, limit=128):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("invalid text")
    return value


def normalize(frame):
    """Compute magnitudes and temperature means only on the server."""
    for vehicle in [*frame.get("cars", []), *([frame["pilot"]] if frame.get("pilot") else [])]:
        if "localVelocityMps" in vehicle:
            vector = vehicle["localVelocityMps"]
            if not isinstance(vector, list) or len(vector) != 3:
                raise ValueError("invalid velocity vector")
            vehicle["speedMps"] = math.sqrt(sum(number(v, -250, 250)**2 for v in vector))
    pilot = frame.get("pilot")
    if pilot:
        for wheel in pilot.get("wheels", []):
            if "surfaceTemperaturesK" in wheel:
                temps = wheel["surfaceTemperaturesK"]
                if not isinstance(temps, list) or len(temps) != 3:
                    raise ValueError("invalid temperature samples")
                wheel["temperatureK"] = CALC.mean([number(t, 0, 2000) for t in temps])


def validate(frame):
    if frame.get("protocolVersion") != 1 or frame.get("type") != "ingest":
        raise ValueError("unsupported protocol")
    for key in ("streamId", "sessionId"):
        text(frame[key])
    integer(frame["seq"])
    number(frame["capturedAt"], 0, 1e14)
    number(frame["gameTime"], 0)
    if frame["status"] not in ("live", "paused", "waitingForGame", "garage"):
        raise ValueError("invalid source status")
    if frame["mode"] not in ("demo", "lmu"):
        raise ValueError("invalid source mode")
    session = frame["session"]
    text(session["track"])
    number(session["lengthM"], 0, 100000)
    number(session["scoringTime"], 0)
    integer(session["phase"], 0, 9)
    for key, low, high in (("sessionType",0,13),("maxLaps",0,2147483647),("endTime",-1,1e9)):
        if key in session:
            number(session[key],low,high)
    cars = frame["cars"]
    if not isinstance(cars, list) or len(cars) > MAX_CARS:
        raise ValueError("too many vehicles")
    ids = set()
    for car in cars:
        integer(car["id"], 0, 100000)
        if car["id"] in ids:
            raise ValueError("duplicate vehicle id")
        ids.add(car["id"])
        text(car["driver"]); text(car["class"])
        for key in ("x", "z", "lapDistM"):
            number(car[key])
        number(car["speedMps"], 0, 250)
        integer(car["place"], 0, MAX_CARS)
        integer(car["laps"], 0, 100000)
        if not isinstance(car["inPit"], bool):
            raise ValueError("invalid pit status")
    pilot = frame.get("pilot")
    if pilot is not None:
        integer(pilot["id"])
        if pilot["id"] not in ids:
            raise ValueError("pilot is not in roster")
        integer(pilot["lap"], 0, 100000)
        integer(pilot["gear"], -1, 9)
        for key, lo, hi in (("fuelL", 0, 1000), ("speedMps", 0, 250),
                            ("rpm", 0, 100000), ("throttle", 0, 1), ("brake", 0, 1)):
            number(pilot[key], lo, hi)
        if not isinstance(pilot["lapValid"], bool):
            raise ValueError("invalid lap validity")
        if "strategyInputs" in pilot:
            inputs = pilot["strategyInputs"]
            for key, low, high in (("fuelCapacityL",0,1000),("virtualEnergyFraction",0,1),
                                   ("lapStartTime",-1e9,1e9),("lastLapTime",-1,100000)):
                number(inputs[key],low,high)
            if not isinstance(inputs["inGarage"],bool):
                raise ValueError("invalid garage state")
            if any(key not in session for key in ("sessionType","maxLaps","endTime")):
                raise ValueError("missing strategy session inputs")
        wheels = pilot["wheels"]
        if not isinstance(wheels, list) or len(wheels) != 4:
            raise ValueError("expected FL FR RL RR wheels")
        for w in wheels:
            for key in ("temperatureK", "pressureKpa", "wear", "brakeC"):
                number(w[key])
    # A map is permitted only on explicit demo frames. Real maps are built from
    # captured coordinates in this slice; SVG/REST import is a later milestone.
    if "demoMap" in frame:
        if frame["mode"] != "demo" or not isinstance(frame["demoMap"], list) or len(frame["demoMap"]) > 2000:
            raise ValueError("invalid demo map")
        for p in frame["demoMap"]:
            if not isinstance(p, list) or len(p) != 2:
                raise ValueError("invalid map point")
            number(p[0]); number(p[1])


class Engine:
    def __init__(self):
        self.key = None
        self.seq = -1
        self.game_time = None
        self.status = None
        self.baseline = None
        self.history = []
        self.map_points = []
        self.map_lap = None
        self.map_complete = False
        self.map_eligible = False
        self.strategy = None
        self.overlays = None
        self.overlay_result = None
        self.overlay_failure = None
        self.iracing = None

    def reset_history(self):
        self.baseline = None
        self.history = []

    def update(self, frame):
        if frame.get('mode')=='iracing':
            from .iracing_compute import IRacingEngine
            if self.iracing is None:self.iracing=IRacingEngine()
            return self.iracing.update(frame)
        normalize(frame)
        validate(frame)
        key = (frame["streamId"], frame["sessionId"],
               frame.get("pilot", {}).get("id") if frame.get("pilot") else None)
        if self.key != key:
            if self.overlays:
                self.overlays.close()
            self.__init__()
            self.key = key
        if frame["seq"] <= self.seq:
            raise ValueError("out-of-order sequence")
        discontinuity = (self.seq >= 0 and frame["seq"] != self.seq + 1)
        if self.game_time is not None:
            dt = frame["gameTime"] - self.game_time
            discontinuity |= dt < 0 or dt > 1
        self.seq = frame["seq"]
        self.game_time = frame["gameTime"]
        left_driving = self.status == 'live' and frame['status'] != 'live'
        self.status = frame['status']
        pilot = frame.get("pilot")
        full_overlays = 'rawSnapshot' in frame or (frame['mode']=='demo' and frame.get('overlayProtocolVersion')==1)
        strategy = {"status":"collector-update-required" if pilot and "strategyInputs" not in pilot else "unavailable",
                    "fuel":None,"energy":None,"finishPrediction":None}
        fuel = {"status": "unavailable", "consumptionLPerLap": None, "lapsRemaining": None}
        if discontinuity or frame["status"] != "live":
            self.strategy = None
            self.reset_history()
            if self.overlays:
                if discontinuity or left_driving:
                    self.overlays.reset()
                self.overlay_result = None
            if not self.map_complete:
                self.map_points = []; self.map_lap = None; self.map_eligible = False
        if pilot and frame["status"] == "live":
            car = next(c for c in frame["cars"] if c["id"] == pilot["id"])
            self.update_fuel(pilot, car, frame["gameTime"])
            avg = statistics.fmean(self.history) if self.history else None
            fuel = {"status": "estimated" if avg else "warming-up",
                    "consumptionLPerLap": avg,
                    "lapsRemaining": CALC.end_stint_laps(pilot["fuelL"], avg) if avg else None,
                    "completedSamples": len(self.history),
                    "method": "Prototype complete-lap sampling + upstream end_stint_laps; not full FuelModule"}
            self.update_map(car, pilot["lap"], frame["session"]["lengthM"])
            if "strategyInputs" in pilot and not full_overlays:
                # This older fuel-only adapter is a fallback. Loading it in
                # parallel with the complete module engine duplicates work,
                # especially after the conservative reset on a delivery gap.
                if self.strategy is None:
                    from .strategy import Strategy
                    self.strategy = Strategy()
                strategy = self.strategy.update(frame,car)
        cars = sorted(frame["cars"], key=lambda c: c["place"] or 999)
        classes = {}
        for car in cars:
            classes[car["class"]] = classes.get(car["class"], 0) + 1
            car["classPlace"] = classes[car["class"]]
        instrument = None
        if pilot:
            instrument = {**pilot, "speedKph": pilot["speedMps"] * 3.6,
                          "wheels": [{**w, "temperatureC": w["temperatureK"] - 273.15}
                                     for w in pilot["wheels"]]}
        demo = frame["mode"] == "demo"
        overlay_error = None
        if pilot and frame['status']=='live' and full_overlays:
            from .overlays import OverlayEngine
            try:
                if self.overlays is None:
                    self.overlays = OverlayEngine()
                self.overlay_result = self.overlays.update(frame)
                self.overlay_failure = None
            except Exception as error:
                # Optional overlays must not terminate valid position/instrument
                # delivery. Expose degradation; never present old overlays as live.
                kind = type(error).__name__
                overlay_error = f'Расчёт дополнительных панелей недоступен ({kind}); базовая телеметрия продолжается.'
                if self.overlay_failure != kind:
                    logging.exception('Overlay calculation failed (%s); basic telemetry continues',kind)
                self.overlay_failure = kind
                self.overlay_result = None
            if self.overlay_result:
                original = self.overlay_result['modules']
                def resource(info):
                    ready = info['estimatedValidConsumption']>0
                    return {'status':'ready' if ready else 'warming-up','amount':info['amountCurrent'],'capacity':info['capacity'],'estimatedConsumption':info['estimatedConsumption'] if ready else None,
                            'lapsRemaining':info['estimatedLaps'] if ready else None,'minutesRemaining':info['estimatedMinutes'] if ready else None}
                strategy = {'status':'active','fuel':resource(original['fuel']),
                            'energy':resource(original['energy']) if original['energy']['available'] else None,
                            'finishPrediction':self.overlay_result['finish'],
                            'paceSeconds':original['delta']['lapTimePace'],
                            'method':'TinyPedal original Delta, Vehicles, Fuel and other modules'}
                resources = [r for r in (strategy['fuel'],strategy['energy']) if r and r['minutesRemaining'] is not None]
                strategy['stintMinutes'] = min((r['minutesRemaining'] for r in resources),default=None)
                strategy['limitingResource'] = 'energy' if strategy['energy'] and strategy['energy'].get('minutesRemaining') is not None and (strategy['fuel']['minutesRemaining'] is None or strategy['energy']['minutesRemaining']<strategy['fuel']['minutesRemaining']) else 'fuel'
                details = {c['id']:c for c in self.overlay_result['race']}
                for car in cars:
                    detail=details.get(car['id'])
                    if detail:
                        car.update({k:detail.get(k) for k in ('relativeGap','gapBehindLeader','gapBehindNext','lastLapTime','bestLapTime','numPitStops')})
        trackmap = self.overlay_result['trackmap'] if self.overlay_result and self.overlay_result['trackmap']['points'] and not demo else {"points": frame.get("demoMap", self.map_points),
                    "status": "demo" if demo else ("recorded" if self.map_complete else "recording"),
                    "source": "synthetic demo" if demo else "prototype server coordinate recorder"}
        if demo:
            from .sectors import geometry
            trackmap['sectorGeometry'] = geometry(trackmap['points'], None, demo=True)
        return {"type": "presentation", "protocolVersion": 1,
                "streamId": frame["streamId"], "sessionId": frame["sessionId"],
                "seq": frame["seq"], "capturedAt": frame["capturedAt"],
                "gameTime": frame["gameTime"], "mode": frame["mode"],
                "status": frame["status"], "session": frame["session"],
                "cars": cars, "pilot": instrument, "fuel": fuel, "strategy":strategy,
                "overlays":self.overlay_result,"overlayError":overlay_error,
                "trackmap": trackmap,
                "compute": {"upstream": "v2.50.0", "headless": True, "overlaysReady":self.overlays is not None,
                            "port": "12 original modules; 76 web data views; desktop option parity tracked separately"}}

    def update_fuel(self, pilot, car, now):
        current = {"lap": pilot["lap"], "fuel": pilot["fuelL"], "time": now,
                   "valid": pilot["lapValid"] and not car["inPit"], "eligible": False}
        prev = self.baseline
        if prev is None:
            self.baseline = current  # partial first lap is excluded
            return
        if pilot["fuelL"] > prev["fuel"] + 0.1 or pilot["lap"] < prev["lap"]:
            self.reset_history(); self.baseline = current
            return
        if pilot["lap"] == prev["lap"]:
            prev["valid"] &= current["valid"]
            return
        if pilot["lap"] == prev["lap"] + 1 and prev["eligible"] and prev["valid"] and current["valid"]:
            used = prev["fuel"] - pilot["fuelL"]
            if used > 0 and now > prev["time"]:
                self.history = (self.history + [used])[-5:]
        current["eligible"] = True
        self.baseline = current

    def update_map(self, car, lap, length):
        if self.map_complete or length <= 0:
            return
        if car["inPit"]:
            self.map_points = []; self.map_lap = None; self.map_eligible = False
            return
        if self.map_lap is None:
            self.map_lap = lap
        elif lap != self.map_lap:
            if lap == self.map_lap + 1 and self.map_eligible and len(self.map_points) > 10:
                self.map_complete = True
                return
            self.map_lap = lap; self.map_points = []; self.map_eligible = True
        point = [car["x"], car["z"]]
        if not self.map_points or math.dist(self.map_points[-1], point) > 3:
            if len(self.map_points) < 5000:
                self.map_points.append(point)


def main():
    engine = Engine()
    faulthandler.enable()
    last_slow_log = -30.0
    try:
        for line in sys.stdin:
            started = time.monotonic()
            # On a genuine hang the journal must identify the module/call,
            # rather than only reporting the relay's generic timeout.
            faulthandler.dump_traceback_later(5, repeat=False)
            try:
                frame = json.loads(line)
                result = engine.update(frame)
            except (ValueError, KeyError, TypeError, StopIteration) as exc:
                result = {"type": "error", "error": str(exc)}
            try:
                print(json.dumps(result, allow_nan=False, separators=(",", ":")), flush=True)
                elapsed = time.monotonic()-started
                if elapsed >= .5 and started-last_slow_log >= 30:
                    logging.warning('Slow calculation: %.3f s, status=%s, cars=%s; receipt ACK is independent',
                                    elapsed, frame.get('status'),len(frame.get('cars',[])))
                    last_slow_log = started
            finally:
                faulthandler.cancel_dump_traceback_later()
    finally:
        if engine.overlays:
            engine.overlays.close()


if __name__ == "__main__":
    main()
