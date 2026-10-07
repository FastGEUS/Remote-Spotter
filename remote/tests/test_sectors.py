import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from remote.sectors import SectorTiming, flag_state, geometry, splits


class SectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine=SectorTiming(self.tmp.name)
        self.v=NS(mID=7,mSector=1,mCountLapFlag=2,mInPits=False,mCurSector1=0,mCurSector2=0,
                  mLastSector1=0,mLastSector2=0,mLastLapTime=0,mFlag=0)
        self.t=NS(mElapsedTime=0,mLapStartET=0,mLapNumber=1,mLapInvalidated=False)
        self.scor=NS(mSectorFlag=[0,0,0],mGamePhase=5,mYellowFlagState=0)
        self.reader=NS(shmm=NS(lmuScorVeh=lambda:self.v,lmuTeleVeh=lambda:self.t,lmuScorInfo=self.scor),
                       lap=NS(sector_index=lambda:{1:0,2:1,0:2}[self.v.mSector]))
        self.info=NS(sectors=NS(sessionBest=NS(sectorBestTB=[99999,99999,99999])))
        self.frame={'streamId':'stream','sessionId':'session','session':{'track':'Test track'}}

    def tick(self,now,sector=None,start=None):
        self.t.mElapsedTime=now
        if sector is not None:self.v.mSector=sector
        if start is not None:self.t.mLapStartET=start;self.t.mLapNumber+=1
        return self.engine.update(self.reader,self.frame,self.info)

    def complete(self):
        self.tick(0)
        self.v.mCurSector1=30
        self.tick(31,2)
        self.v.mCurSector2=65
        self.tick(70,0)
        self.v.mCurSector1=self.v.mCurSector2=0
        return self.tick(105,1,105)

    def test_delayed_official_times_and_persistent_journal(self):
        result=self.complete()
        self.assertEqual(result['history'],[])
        self.v.mLastSector1,self.v.mLastSector2,self.v.mLastLapTime=30,65,105
        result=self.tick(105.2)
        self.assertEqual(result['history'][0]['sectors'],[30,35,40])
        self.assertEqual(result['history'][0]['total'],105)
        self.assertEqual(result['best'],[None,None,None])
        self.assertAlmostEqual(result['elapsed'],.2)
        self.assertEqual(len(self.tick(105.4)['history']),1)
        restored=SectorTiming(self.tmp.name).update(self.reader,self.frame,self.info)
        self.assertEqual(restored['history'],result['history'])
        self.assertEqual(len(list(Path(self.tmp.name,'sector_history').glob('*.json'))),1)
        json.dumps(result,allow_nan=False)

    def test_invalid_lap_does_not_reuse_previous_valid_last_time(self):
        self.t.mLapInvalidated=True
        self.complete()
        self.v.mLastSector1,self.v.mLastSector2,self.v.mLastLapTime=30,65,105
        result=self.tick(106.2)
        row=result['history'][0]
        self.assertEqual(row['status'],'invalid')
        self.assertEqual(row['sectors'],[30,35,None])
        self.assertIsNone(row['total'])

    def test_first_partial_lap_skipped_and_unknown_times_stay_empty(self):
        self.tick(20)
        self.tick(105,1,105)
        self.assertFalse(self.tick(107)['history'])
        self.assertEqual(splits(0,0,0),[None,None,None])
        self.assertEqual(splits(30,20,105),[30,None,None])
        self.assertEqual(splits(30,65,105),[30,35,40])

    def test_missing_official_time_and_session_separation(self):
        self.complete()
        result=self.tick(106.2)
        self.assertEqual(result['history'][0]['status'],'missing-official-time')
        self.assertIsNone(result['history'][0]['sectors'][2])
        self.frame['sessionId']='new-session'
        self.assertFalse(self.tick(106.3)['history'])

    def test_flags_keep_unverified_channels_and_pilot_blue_separate(self):
        self.scor.mSectorFlag=[0,1,0];self.v.mFlag=6
        flags=flag_state(self.reader)
        self.assertEqual(flags['session'],'yellow')
        self.assertTrue(flags['pilotBlue'])
        self.assertIsNone(flags['sectorFlags'])
        self.assertEqual(flags['rawChannels'],[0,1,0])
        self.assertEqual(flag_state(self.reader,True)['sectorFlags'],['clear','yellow','clear'])
        self.scor.mGamePhase=7
        self.assertEqual(flag_state(self.reader)['session'],'stopped')
        self.scor.mGamePhase=6
        self.assertEqual(flag_state(self.reader)['session'],'caution')

    def test_geometry_uses_actual_crossings_and_rejects_missing_indices(self):
        points=[[i,i]for i in range(101)]
        self.assertEqual(geometry(points,[17,74])['indices'],[17,74])
        for indices in ([0,0],[0,74],[74,17],[17,100],None):
            self.assertIsNone(geometry(points,indices))
        self.assertEqual(geometry(points,None,True)['indices'],[33,67])

    def test_new_records_compare_to_pre_lap_reference_and_s3_survives_finish(self):
        self.info.sectors.sessionBest.sectorBestTB=[30,35,40]
        self.tick(0)
        self.v.mCurSector1=29
        self.info.sectors.sessionBest.sectorBestTB=[29,35,40]
        first=self.tick(30,2)
        self.assertEqual(first['delta'],[-1,None,None])
        self.assertEqual(first['reference'][0],30)
        self.assertEqual(first['best'][0],29)
        self.v.mCurSector2=63
        self.info.sectors.sessionBest.sectorBestTB=[29,34,40]
        second=self.tick(65,0)
        self.assertEqual(second['delta'],[-1,-1,None])
        self.v.mCurSector1=self.v.mCurSector2=0
        self.v.mLastSector1,self.v.mLastSector2,self.v.mLastLapTime=29,63,100
        self.info.sectors.sessionBest.sectorBestTB=[29,34,37]
        finished=self.tick(100,1,100)
        self.assertEqual(finished['delta'],[-1,-1,-3])
        self.assertEqual(finished['comparisonLap'],[1,1,1])
        self.assertEqual(finished['reference'],[30,35,40])
        self.assertEqual(finished['last'],[29,34,37])

    def test_invalid_or_partial_lap_does_not_publish_a_comparison(self):
        self.info.sectors.sessionBest.sectorBestTB=[30,35,40]
        self.tick(20) # joined mid-lap: no trustworthy pre-lap reference
        self.v.mCurSector1=29
        self.assertEqual(self.tick(30,2)['delta'],[None,None,None])
        self.tick(100,1,100)
        self.t.mLapInvalidated=True
        self.v.mCurSector1=28
        invalid=self.tick(130,2)
        self.assertEqual(invalid['delta'],[None,None,None])

    def test_invalid_next_lap_clears_previous_completed_comparison(self):
        self.info.sectors.sessionBest.sectorBestTB=[31,36,41]
        self.complete()
        self.v.mLastSector1,self.v.mLastSector2,self.v.mLastLapTime=30,65,105
        self.assertEqual(self.tick(105.2)['delta'],[-1,-1,-1])
        self.t.mLapInvalidated=True
        self.v.mCurSector1=30;self.tick(136,2)
        self.v.mCurSector2=65;self.tick(175,0)
        self.v.mCurSector1=self.v.mCurSector2=0
        self.tick(210,1,210)
        self.assertEqual(self.tick(211.2)['delta'],[None,None,None])

    def test_delayed_prior_lap_time_supplies_next_lap_s3_benchmark(self):
        self.complete() # first lap has no prior reference
        self.v.mLastSector1,self.v.mLastSector2,self.v.mLastLapTime=30,65,105
        self.tick(105.2)
        self.assertEqual(self.engine.current['reference'],[30,35,40])
        self.assertEqual(self.engine.last_comparison['reference'],[None,None,None])


if __name__=='__main__':unittest.main()
