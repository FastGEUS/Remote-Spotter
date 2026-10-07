"""Synthetic full LMU structures for deterministic server and UI tests only."""
import math
from pyLMUSharedMemory.lmu_data import LMUObjectOut


def build(frame):
    data = LMUObjectOut()
    session = frame['session']
    scor = data.scoring.scoringInfo
    scor.mTrackName = session['track'].encode()[:63]
    for raw,key in [('mSession','sessionType'),('mCurrentET','scoringTime'),('mGamePhase','phase'),('mLapDist','lengthM'),('mEndET','endTime'),('mMaxLaps','maxLaps')]:
        setattr(scor,raw,session.get(key,0))
    scor.mNumVehicles = len(frame['cars'])
    scor.mInRealtime = True
    scor.mAmbientTemp = 22
    scor.mTrackTemp = 31
    scor.mTimeOfDay = 12*3600+frame['gameTime']
    # Synthetic yellow/blue intervals exercise the UI; never used for LMU.
    flag_sector = int(frame['gameTime']//4)%4
    if flag_sector < 3:
        scor.mSectorFlag[flag_sector] = 1
    data.generic.gameVersion = 122
    data.telemetry.activeVehicles = len(frame['cars'])
    data.telemetry.playerHasVehicle = True
    pilot = frame['pilot']
    for i,car in enumerate(frame['cars']):
        v = data.scoring.vehScoringInfo[i]
        t = data.telemetry.telemInfo[i]
        is_player = car['id']==pilot['id']
        if is_player:
            data.telemetry.playerVehicleIdx = i
        for obj in (v,t):
            obj.mID = car['id']
            obj.mPos.x,obj.mPos.z = car['x'],car['z']
            obj.mLocalVel.z = -car.get('speedMps',62.5)
            obj.mOri[0].x = obj.mOri[1].y = obj.mOri[2].z = 1
            obj.mLapStartET = car['laps']*16
        v.mDriverName = car['driver'].encode()[:31]
        v.mVehicleName = b'Demo LMU car'
        v.mVehicleClass = car['class'].encode()[:31]
        v.mIsPlayer = is_player
        v.mFlag = 6 if is_player and int(frame['gameTime']//6)%2 else 0
        v.mTotalLaps = car['laps']
        v.mLapDist = car['lapDistM']
        v.mSector = (int(v.mLapDist/session['lengthM']*3)+1)%3
        v.mCountLapFlag = 2
        if is_player and not pilot['lapValid']:
            v.mCountLapFlag = 1
        t.mLapInvalidated = is_player and not pilot['lapValid']
        v.mPlace = car['place']
        v.mInPits = car['inPit']
        v.mTimeBehindNext = .24 if i else 0
        v.mTimeBehindLeader = .24*i
        v.mBestLapTime = v.mLastLapTime = 16 if car['laps'] else 0
        if is_player and not pilot['lapValid']:
            v.mLastLapTime = 0
        v.mEstimatedLapTime = 16
        v.mTimeIntoLap = v.mLapDist/session['lengthM']*16
        v.mLastSector1 = v.mBestSector1 = 16/3 if car['laps'] else 0
        v.mLastSector2 = v.mBestSector2 = 32/3 if car['laps'] else 0
        v.mCurSector1 = 16/3 if v.mTimeIntoLap>16/3 else 0
        v.mCurSector2 = 32/3 if v.mTimeIntoLap>32/3 else 0
        t.mElapsedTime = frame['gameTime']
        t.mLapNumber = car['laps']+1
        t.mFuel = pilot['fuelL'] if is_player else 90
        t.mFuelCapacity = 110
        t.mVirtualEnergy = pilot['strategyInputs']['virtualEnergyFraction'] if is_player else .9
        t.mGear = pilot['gear']
        t.mEngineRPM = pilot['rpm']
        t.mEngineMaxRPM = 8500
        t.mEngineOilTemp,t.mEngineWaterTemp = 100,92
        t.mFilteredThrottle = t.mUnfilteredThrottle = pilot['throttle']
        t.mFilteredBrake = t.mUnfilteredBrake = pilot['brake']
        t.mRearBrakeBias = .46
        t.mPhysicalSteeringWheelRange = 540
        t.mFilteredSteering = t.mUnfilteredSteering = .2*math.sin(frame['gameTime'])
        t.mBatteryChargeFraction = .75
        t.mLocalAccel.x = 6*math.sin(frame['gameTime'])
        for j,w in enumerate(t.mWheels):
            sample = pilot['wheels'][j]
            for k in range(3):
                w.mTemperature[k] = sample.get('temperatureK',365)
            w.mPressure,w.mWear,w.mBrakeTemp = sample['pressureKpa'],sample['wear'],sample['brakeC']
            w.mTireCarcassTemperature = 355+j*2
            w.mTireLoad = w.mSuspForce = 3300+j*50
            w.mRideHeight = .07
            w.mSuspensionDeflection = .05
            w.mRotation = -200
            w.mLongitudinalGroundVel = -62.5
    return data
