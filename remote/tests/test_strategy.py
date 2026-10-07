import copy
import json
import subprocess
import sys
import unittest
from remote.compute import Engine
from remote.tests.test_compute import frame


class StrategyTests(unittest.TestCase):
    def replay(self, change=lambda f: None, count=660):
        engine=Engine()
        for seq in range(count):
            f=frame(seq*.05,seq)
            change(f)
            result=engine.update(f)
            json.dumps(result,allow_nan=False)
        return engine,result

    def test_original_generator_fuel_energy_known_consumption(self):
        engine,result=self.replay()
        strategy=result['strategy']
        self.assertEqual(strategy['fuel']['status'],'ready')
        self.assertAlmostEqual(strategy['fuel']['estimatedConsumption'],2.5,places=5)
        self.assertAlmostEqual(strategy['energy']['estimatedConsumption'],2.0,places=5)
        self.assertAlmostEqual(strategy['fuel']['minutesRemaining'],strategy['fuel']['lapsRemaining']*16/60)
        self.assertIn('module_fuel.py',engine.strategy.fuel_gen.gi_code.co_filename)
        self.assertIsNone(strategy['finishPrediction'])

    def test_invalid_and_pit_laps_do_not_train_generator(self):
        for reason in ('invalid','pit'):
            def change(f):
                if reason=='invalid':f['pilot']['lapValid']=False
                else:f['cars'][0]['inPit']=True
            _,result=self.replay(change,count=1000)
            self.assertIsNone(result['strategy']['fuel']['lapsRemaining'])

    def test_old_collector_remains_compatible(self):
        f=frame();del f['pilot']['strategyInputs']
        result=Engine().update(f)
        self.assertEqual(result['strategy']['status'],'collector-update-required')
        self.assertEqual(result['fuel']['status'],'warming-up')

    def test_unavailable_energy_is_not_zero_prediction(self):
        def change(f):f['pilot']['strategyInputs']['virtualEnergyFraction']=0
        _,result=self.replay(change)
        self.assertEqual(result['strategy']['energy']['status'],'unavailable')
        self.assertIsNone(result['strategy']['energy']['amount'])

    def test_energy_zero_after_observation_is_empty_not_missing(self):
        engine,result=self.replay()
        f=frame(33,660);f['pilot']['strategyInputs']['virtualEnergyFraction']=0
        result=engine.update(f)
        self.assertEqual(result['strategy']['energy']['amount'],0)
        self.assertEqual(result['strategy']['energy']['lapsRemaining'],0)
        self.assertEqual(result['strategy']['energy']['minutesRemaining'],0)

    def test_gap_session_and_pause_clear_generator(self):
        for reason in ('gap','session','pause'):
            engine,_=self.replay()
            f=frame(33,660)
            if reason=='gap':f['seq']=661
            elif reason=='session':f['sessionId']='new-session'
            else:f['status']='paused'
            result=engine.update(f)
            self.assertIsNone((result['strategy'].get('fuel') or {}).get('lapsRemaining'))

    def test_generator_runtime_does_not_import_qt(self):
        subprocess.run([sys.executable,'-c',"from remote.compute import Engine; from remote.tests.test_compute import frame; import sys; Engine().update(frame()); assert not any(k.startswith('PySide') for k in sys.modules)"],check=True)

    def test_malformed_strategy_inputs_rejected_before_sequence(self):
        engine=Engine();engine.update(frame())
        f=frame(.05,1);f['pilot']['strategyInputs']['virtualEnergyFraction']=float('nan')
        with self.assertRaises(ValueError):engine.update(f)
        self.assertEqual(engine.update(frame(.05,1))['seq'],1)

    def test_timed_race_accepts_signed_int_max_lap_marker(self):
        f=frame();f['session']['maxLaps']=2147483647;f['session']['endTime']=3600
        result=Engine().update(f)
        self.assertEqual(result['strategy']['status'],'active')
        self.assertIsNone(result['strategy']['finishPrediction'])


if __name__=='__main__':unittest.main()
