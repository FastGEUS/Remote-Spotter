import copy
import json
import math
import subprocess
import sys
import unittest
from remote.compute import Engine, validate, normalize
from remote.collector import demo_frame
from remote.native import NativeReader
from pyLMUSharedMemory.lmu_data import LMUObjectOut


def frame(t=0, seq=0):
    return dict(type="ingest", protocolVersion=1, mode="demo", streamId="stream", sessionId="session",
                seq=seq, capturedAt=1760000000000+t*1000, **demo_frame(t))


class ComputeTests(unittest.TestCase):
    def test_qt_is_not_imported(self):
        result = subprocess.run([sys.executable, "-c", "from remote.compute import Engine; import sys; assert not any(k.startswith('PySide') for k in sys.modules)"], check=True)
        self.assertEqual(result.returncode, 0)

    def test_pipeline_complete_lap_then_actual_upstream_estimate(self):
        e = Engine()
        for seq in range(650):
            p = e.update(frame(seq*0.05, seq))
        self.assertEqual(p["fuel"]["status"], "estimated")
        self.assertAlmostEqual(p["fuel"]["consumptionLPerLap"], 2.5, places=6)
        self.assertAlmostEqual(p["fuel"]["lapsRemaining"], p["pilot"]["fuelL"]/2.5)
        self.assertEqual(p["pilot"]["wheels"][0]["temperatureC"], 91.85000000000002)
        self.assertEqual(p["cars"][4]["classPlace"], 1)

    def test_gap_and_session_reset_predictions(self):
        e = Engine()
        for i in range(650):
            p = e.update(frame(i*.05, i))
        self.assertIsNotNone(p["fuel"]["lapsRemaining"])
        p = e.update(frame(32.6, 652))
        self.assertIsNone(p["fuel"]["lapsRemaining"])
        new = frame(0, 0);new["streamId"] = "reconnected"
        self.assertEqual(e.update(new)["fuel"]["status"], "warming-up")

    def test_invalid_lap_and_pit_exclude_consumption(self):
        for reason in ("pit", "invalid"):
            e = Engine()
            for i in range(650):
                f = frame(i*.05, i)
                if 320 <= i <= 640:
                    if reason == "pit": f["cars"][0]["inPit"] = True
                    else: f["pilot"]["lapValid"] = False
                p = e.update(f)
            self.assertIsNone(p["fuel"]["lapsRemaining"])

    def test_refuel_resets_history(self):
        e = Engine()
        for i in range(650):e.update(frame(i*.05,i))
        f=frame(32.5,650);f["pilot"]["fuelL"]=110
        self.assertIsNone(e.update(f)["fuel"]["lapsRemaining"])

    def test_validation_does_not_poison_sequence(self):
        e=Engine();e.update(frame())
        bad=frame(.05,1);bad["pilot"]["fuelL"]=float("nan")
        with self.assertRaises(ValueError):e.update(bad)
        self.assertEqual(e.update(frame(.05,1))["seq"],1)
        with self.assertRaises(ValueError):e.update(frame(.05,1))

    def test_malformed_and_duplicate_inputs(self):
        for mutate in (lambda f:f["cars"].append(copy.deepcopy(f["cars"][0])),
                       lambda f:f.update(cars="bad"),lambda f:f.update(seq=True),
                       lambda f:f["pilot"].update(gear=100)):
            f=frame();mutate(f)
            with self.assertRaises(ValueError):validate(f)

    def test_native_extract_struct_fixture_joins_by_slot_not_array_index(self):
        data=LMUObjectOut()
        data.scoring.scoringInfo.mNumVehicles=2
        data.scoring.scoringInfo.mLapDist=4563
        data.scoring.scoringInfo.mInRealtime=True
        for i,slot in enumerate((42,7)):
            s=data.scoring.vehScoringInfo[i];s.mID=slot;s.mPlace=i+1;s.mVehicleClass=b"LMGT3"
        data.telemetry.activeVehicles=2
        data.telemetry.playerHasVehicle=True
        data.telemetry.playerVehicleIdx=1
        t=data.telemetry.telemInfo[1];t.mID=42;t.mFuel=88;t.mLapNumber=3
        t.mElapsedTime=10;t.mLocalVel.z=-50
        t.mFuelCapacity=110;t.mVirtualEnergy=.75;t.mLapStartET=5
        data.scoring.vehScoringInfo[0].mLastLapTime=90
        t.mWheels[0].mTemperature[:]=(350,360,370)
        f=NativeReader.extract(data)
        self.assertEqual(f["pilot"]["id"],42)
        self.assertEqual(f["pilot"]["strategyInputs"]["lastLapTime"],90)
        self.assertEqual(f["pilot"]["strategyInputs"]["virtualEnergyFraction"],.75)
        self.assertEqual(f["pilot"]["strategyInputs"]["fuelCapacityL"],110)
        self.assertNotIn("speedMps",f["pilot"])
        self.assertEqual(f["pilot"]["localVelocityMps"],[0,0,-50])
        self.assertEqual(f["pilot"]["wheels"][0]["surfaceTemperaturesK"],[350,360,370])
        normalize(f)
        self.assertEqual(f["pilot"]["speedMps"],50)
        self.assertEqual(f["pilot"]["wheels"][0]["temperatureK"],360)


if __name__=="__main__":unittest.main()
