# Python mapping of The Iron Wolf's rF2 Shared Memory Tools
# Auto-generated from rF2data.cs

from enum import IntEnum
import ctypes
import mmap

# Define the types we need.
# Still doesn't work.


class CtypesEnum(IntEnum):
    """A ctypes-compatible IntEnum superclass."""
    @classmethod
    def from_param(cls, obj):
        return int(obj)


class rFactor2Constants:
    MAX_MAPPED_VEHICLES = 128
    MAX_MAPPED_IDS = 512
    MAX_RULES_INSTRUCTION_MSG_LEN = 96
    MAX_STATUS_MSG_LEN = 128


"""

#untranslated /*
rF2 internal state mapping structures.  Allows access to native C++ structs from C
#untranslated Must be kept in sync with Include\rF2State.h.
#untranslated See: MainForm.MainUpdate for sample on how to marshall from native in memory struct.
#untranslated Author: The Iron Wolf (vleonavicius@hotmail.com)
#untranslated Website: thecrewchief.org
#untranslated */
#untranslated using Newtonsoft.Json;
#untranslated using System;
#untranslated using System.Runtime.InteropServices;
#untranslated using System.Xml.Serialization;
#untranslated namespace CrewChiefV4.rFactor2
class rFactor2Constants
        const string MM_TELEMETRY_FILE_NAME = "$rFactor2SMMP_Telemetry$";
        const string MM_SCORING_FILE_NAME = "$rFactor2SMMP_Scoring$";
        const string MM_RULES_FILE_NAME = "$rFactor2SMMP_Rules$";
        const string MM_EXTENDED_FILE_NAME = "$rFactor2SMMP_Extended$";
        const int MAX_MAPPED_VEHICLES = 128;
        const int MAX_MAPPED_IDS = 512;
        const int MAX_STATUS_MSG_LEN = 128;
        const int MAX_RULES_INSTRUCTION_MSG_LEN = 96;
        const string RFACTOR2_PROCESS_NAME = "rFactor2";
        const byte RowX = 0;
        const byte RowY = 1;
        const byte RowZ = 2;
"""


class rF2GamePhase(CtypesEnum):
    Garage = 0
    WarmUp = 1
    GridWalk = 2
    Formation = 3
    Countdown = 4
    GreenFlag = 5
    FullCourseYellow = 6
    SessionStopped = 7
    SessionOver = 8
    PausedOrHeartbeat = 9


class rF2YellowFlagState(CtypesEnum):
    Invalid = -1
    NoFlag = 0
    Pending = 1
    PitClosed = 2
    PitLeadLap = 3
    PitOpen = 4
    LastLap = 5
    Resume = 6
    RaceHalt = 7


class rF2SurfaceType(CtypesEnum):
    Dry = 0
    Wet = 1
    Grass = 2
    Dirt = 3
    Gravel = 4
    Kerb = 5
    Special = 6


class rF2Sector(CtypesEnum):
    Sector3 = 0
    Sector1 = 1
    Sector2 = 2


class rF2FinishStatus(CtypesEnum):
    _None = 0
    Finished = 1
    Dnf = 2
    Dq = 3


class rF2Control(CtypesEnum):
    Nobody = -1
    Player = 0
    AI = 1
    Remote = 2
    Replay = 3


class rF2WheelIndex(CtypesEnum):
    FrontLeft = 0
    FrontRight = 1
    RearLeft = 2
    RearRight = 3


class rF2PitState(CtypesEnum):
    _None = 0
    Request = 1
    Entering = 2
    Stopped = 3
    Exiting = 4


class rF2PrimaryFlag(CtypesEnum):
    Green = 0
    Blue = 6


class rF2CountLapFlag(CtypesEnum):
    DoNotCountLap = 0
    CountLapButNotTime = 1
    CountLapAndTime = 2


class rF2RearFlapLegalStatus(CtypesEnum):
    Disallowed = 0
    DetectedButNotAllowedYet = 1
    Alllowed = 2


class rF2IgnitionStarterStatus(CtypesEnum):
    Off = 0
    Ignition = 1
    IgnitionAndStarter = 2


# untranslated namespace rFactor2Data
#untranslated [StructLayout(LayoutKind.Sequential, Pack = 4)]
class rF2Vec3(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('x', ctypes.c_double),
        ('y', ctypes.c_double),
        ('z', ctypes.c_double),
    ]

#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2Wheel(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mSuspensionDeflection', ctypes.c_double),  # meters
        ('mRideHeight', ctypes.c_double),            # meters
        ('mSuspForce', ctypes.c_double),             # pushrod load in Newtons
        ('mBrakeTemp', ctypes.c_double),             # Celsius
        #!!! double mBrakePressure;         # currently 0.0-1.0, depending on driver input and brake balance; will convert to true brake pressure (kPa) in future
        ('mRotation', ctypes.c_double),              # radians/sec
        ('mLateralPatchVel', ctypes.c_double),       # lateral velocity at contact patch
        ('mLongitudinalPatchVel', ctypes.c_double),  # longitudinal velocity at contact patch
        ('mLateralGroundVel', ctypes.c_double),      # lateral velocity at contact patch
        ('mLongitudinalGroundVel', ctypes.c_double),  # longitudinal velocity at contact patch
        ('mCamber', ctypes.c_double),                # radians (positive is left for left-side wheels, right for right-side wheels)
        ('mLateralForce', ctypes.c_double),          # Newtons
        ('mLongitudinalForce', ctypes.c_double),     # Newtons
        ('mTireLoad', ctypes.c_double),              # Newtons
        ('mGripFract', ctypes.c_double),             # an approximation of what fraction of the contact patch is sliding
        ('mPressure', ctypes.c_double),              # kPa (tire pressure)
        ('mTemperature', ctypes.c_double * 3),         # Kelvin (subtract 273.15 to get Celsius), left/center/right (not to be confused with inside/center/outside!)
        ('mWear', ctypes.c_double),                  # wear (0.0-1.0, fraction of maximum) ... this is not necessarily proportional with grip loss
        ('mTerrainName', ctypes.c_ubyte * 16),           # the material prefixes from the TDF file
        ('mSurfaceType', ctypes.c_ubyte),             # 0=dry, 1=wet, 2=grass, 3=dirt, 4=gravel, 5=rumblestrip, 6 = special
        ('mFlat', ctypes.c_ubyte),                    # whether tire is flat
        ('mDetached', ctypes.c_ubyte),                # whether wheel is detached
        ('mStaticUndeflectedRadius', ctypes.c_ubyte),  # tire radius in centimeters
        ('mVerticalTireDeflection', ctypes.c_double),  # how much is tire deflected from its (speed-sensitive) radius
        ('mWheelYLocation', ctypes.c_double),        # wheel's y location relative to vehicle y location
        ('mToe', ctypes.c_double),                   # current toe angle w.r.t. the vehicle
        ('mTireCarcassTemperature', ctypes.c_double),       # rough average of temperature samples from carcass (Kelvin)
        ('mTireInnerLayerTemperature', ctypes.c_double * 3),  # rough average of temperature samples from innermost layer of rubber (before carcass) (Kelvin)
        ('mExpansion', ctypes.c_ubyte * 24),                    # for future use
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2VehicleTelemetry(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # slot ID (note that it can be re-used in multiplayer after someone
        # leaves)
        ('mID', ctypes.c_int),
        # time since last update (seconds)
        ('mDeltaTime', ctypes.c_double),
        ('mElapsedTime', ctypes.c_double),           # game session time
        ('mLapNumber', ctypes.c_int),               # current lap number
        # time this lap was started
        ('mLapStartET', ctypes.c_double),
        ('mVehicleName', ctypes.c_ubyte * 64),         # current vehicle name
        ('mTrackName', ctypes.c_ubyte * 64),           # current track name
        ('mPos', rF2Vec3),                  # world position in meters
        # velocity (meters/sec) in local vehicle coordinates
        ('mLocalVel', rF2Vec3),
        # acceleration (meters/sec^2) in local vehicle coordinates
        ('mLocalAccel', rF2Vec3),
        # rows of orientation matrix (use TelemQuat conversions if desired),
        # also converts local
        ('mOri', rF2Vec3 * 3),
        # rotation (radians/sec) in local vehicle coordinates
        ('mLocalRot', rF2Vec3),
        # rotational acceleration (radians/sec^2) in local vehicle coordinates
        ('mLocalRotAccel', rF2Vec3),
        # -1=reverse, 0=neutral, 1+ = forward gears
        ('mGear', ctypes.c_int),
        ('mEngineRPM', ctypes.c_double),             # engine RPM
        ('mEngineWaterTemp', ctypes.c_double),       # Celsius
        ('mEngineOilTemp', ctypes.c_double),         # Celsius
        ('mClutchRPM', ctypes.c_double),             # clutch RPM
        ('mUnfilteredThrottle', ctypes.c_double),    # ranges  0.0-1.0
        ('mUnfilteredBrake', ctypes.c_double),       # ranges  0.0-1.0
        # ranges -1.0-1.0 (left to right)
        ('mUnfilteredSteering', ctypes.c_double),
        ('mUnfilteredClutch', ctypes.c_double),      # ranges  0.0-1.0
        ('mFilteredThrottle', ctypes.c_double),      # ranges  0.0-1.0
        ('mFilteredBrake', ctypes.c_double),         # ranges  0.0-1.0
        # ranges -1.0-1.0 (left to right)
        ('mFilteredSteering', ctypes.c_double),
        ('mFilteredClutch', ctypes.c_double),        # ranges  0.0-1.0
        # torque around steering shaft (used to be mSteeringArmForce, but that
        # is not necessarily accurate for feedback purposes)
        ('mSteeringShaftTorque', ctypes.c_double),
        # deflection at front 3rd spring
        ('mFront3rdDeflection', ctypes.c_double),
        # deflection at rear 3rd spring
        ('mRear3rdDeflection', ctypes.c_double),
        ('mFrontWingHeight', ctypes.c_double),       # front wing height
        ('mFrontRideHeight', ctypes.c_double),       # front ride height
        ('mRearRideHeight', ctypes.c_double),        # rear ride height
        ('mDrag', ctypes.c_double),                  # drag
        ('mFrontDownforce', ctypes.c_double),        # front downforce
        ('mRearDownforce', ctypes.c_double),         # rear downforce
        ('mFuel', ctypes.c_double),                  # amount of fuel (liters)
        ('mEngineMaxRPM', ctypes.c_double),          # rev limit
        ('mScheduledStops', ctypes.c_ubyte),  # number of scheduled pitstops
        # whether overheating icon is shown
        ('mOverheating', ctypes.c_ubyte),
        # whether any parts (besides wheels) have been detached
        ('mDetached', ctypes.c_ubyte),
        # whether headlights are on
        ('mHeadlights', ctypes.c_ubyte),
        # dent severity at 8 locations around the car (0=none, 1=some, 2=more)
        ('mDentSeverity', ctypes.c_ubyte * 8),
        ('mLastImpactET', ctypes.c_double),          # time of last impact
        ('mLastImpactMagnitude', ctypes.c_double),   # magnitude of last impact
        ('mLastImpactPos', rF2Vec3),        # location of last impact
        # current engine torque (including additive torque) (used to be
        # mEngineTq, but there's little reason to abbreviate it)
        ('mEngineTorque', ctypes.c_double),
        # the current sector (zero-based) with the pitlane stored in the sign
        # bit (example: entering pits from third sector gives 0x80000002)
        ('mCurrentSector', ctypes.c_int),
        ('mSpeedLimiter', ctypes.c_ubyte),   # whether speed limiter is on
        ('mMaxGears', ctypes.c_ubyte),       # maximum forward gears
        ('mFrontTireCompoundIndex', ctypes.c_ubyte),   # index within brand
        ('mRearTireCompoundIndex', ctypes.c_ubyte),    # index within brand
        ('mFuelCapacity', ctypes.c_double),          # capacity in liters
        # whether front flap is activated
        ('mFrontFlapActivated', ctypes.c_ubyte),
        # whether rear flap is activated
        ('mRearFlapActivated', ctypes.c_ubyte),
        # 0=disallowed, 1=criteria detected but not allowed quite yet, 2 =
        # allowed
        ('mRearFlapLegalStatus', ctypes.c_ubyte),
        # 0=off 1=ignition 2 = ignition+starter
        ('mIgnitionStarter', ctypes.c_ubyte),
        # name of front tire compound
        ('mFrontTireCompoundName', ctypes.c_ubyte * 18),
        # name of rear tire compound
        ('mRearTireCompoundName', ctypes.c_ubyte * 18),
        # whether speed limiter is available
        ('mSpeedLimiterAvailable', ctypes.c_ubyte),
        # whether (hard) anti-stall is activated
        ('mAntiStallActivated', ctypes.c_ubyte),
        ('mUnused', ctypes.c_ubyte * 2),                #
        # the *visual* steering wheel range
        ('mVisualSteeringWheelRange', ctypes.c_float),
        # fraction of brakes on rear
        ('mRearBrakeBias', ctypes.c_double),
        # current turbo boost pressure if available
        ('mTurboBoostPressure', ctypes.c_double),
        # offset from static CG to graphical center
        ('mPhysicsToGraphicsOffset', ctypes.c_float * 3),
        # the *physical* steering wheel range
        ('mPhysicalSteeringWheelRange', ctypes.c_float),
        # for future use (note that the slot ID has been moved to mID above)
        ('mExpansion', ctypes.c_ubyte * 152),
        # wheel info (front left, front right, rear left, rear right)
        ('mWheels', rF2Wheel * 4),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2ScoringInfo(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mTrackName', ctypes.c_ubyte * 64),           # current track name
        # current session (0=testday 1-4=practice 5-8=qual 9=warmup 10-13 =
        # race)
        ('mSession', ctypes.c_int),
        ('mCurrentET', ctypes.c_double),             # current time
        ('mEndET', ctypes.c_double),                 # ending time
        ('mMaxLaps', ctypes.c_int),                # maximum laps
        ('mLapDist', ctypes.c_double),               # distance around track
        ('pointer1', ctypes.c_ubyte * 8),
        # current number of vehicles
        ('mNumVehicles', ctypes.c_int),
        ('mGamePhase', ctypes.c_ubyte),
        ('mYellowFlagState', ctypes.c_ubyte),
        # whether there are any local yellows at the moment in each sector (not
        # sure if sector 0 is first or last, so test)
        ('mSectorFlag', ctypes.c_ubyte * 3),
        # start light frame (number depends on track)
        ('mStartLight', ctypes.c_ubyte),
        # number of red lights in start sequence
        ('mNumRedLights', ctypes.c_ubyte),
        # in realtime as opposed to at the monitor
        ('mInRealtime', ctypes.c_ubyte),
        # player name (including possible multiplayer override)
        ('mPlayerName', ctypes.c_ubyte * 32),
        # may be encoded to be a legal filename
        ('mPlrFileName', ctypes.c_ubyte * 64),
        # cloud darkness? 0.0-1.0
        ('mDarkCloud', ctypes.c_double),
        # raining severity 0.0-1.0
        ('mRaining', ctypes.c_double),
        ('mAmbientTemp', ctypes.c_double),             # temperature (Celsius)
        ('mTrackTemp', ctypes.c_double),               # temperature (Celsius)
        ('mWind', rF2Vec3),                   # wind speed
        # minimum wetness on main path 0.0-1.0
        ('mMinPathWetness', ctypes.c_double),
        # maximum wetness on main path 0.0-1.0
        ('mMaxPathWetness', ctypes.c_double),
        # 1 = server, 2 = client, 3 = server and client
        ('mGameMode', ctypes.c_ubyte),
        # is the server password protected
        ('mIsPasswordProtected', ctypes.c_ubyte),
        # the port of the server (if on a server)
        ('mServerPort', ctypes.c_short),
        # the public IP address of the server (if on a server)
        ('mServerPublicIP', ctypes.c_int),
        # maximum number of vehicles that can be in the session
        ('mMaxPlayers', ctypes.c_int),
        ('mServerName', ctypes.c_ubyte * 32),            # name of the server
        # start time (seconds since midnight) of the event
        ('mStartET', ctypes.c_float),
        # average wetness on main path 0.0-1.0
        ('mAvgPathWetness', ctypes.c_double),
        ('mExpansion', ctypes.c_ubyte * 200),
        ('pointer2', ctypes.c_ubyte * 8),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2VehicleScoring(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # slot ID (note that it can be re-used in multiplayer after someone
        # leaves)
        ('mID', ctypes.c_int),
        ('mDriverName', ctypes.c_ubyte * 32),          # driver name
        ('mVehicleName', ctypes.c_ubyte * 64),         # vehicle name
        ('mTotalLaps', ctypes.c_short),              # laps completed
        # 0=sector3, 1=sector1, 2 = sector2 (don't ask why)
        ('mSector', ctypes.c_ubyte),
        # 0=none, 1=finished, 2=dnf, 3 = dq
        ('mFinishStatus', ctypes.c_ubyte),
        # current distance around track
        ('mLapDist', ctypes.c_double),
        # lateral position with respect to *very approximate* "center" path
        ('mPathLateral', ctypes.c_double),
        # track edge (w.r.t. "center" path) on same side of track as vehicle
        ('mTrackEdge', ctypes.c_double),
        ('mBestSector1', ctypes.c_double),           # best sector 1
        # best sector 2 (plus sector 1)
        ('mBestSector2', ctypes.c_double),
        ('mBestLapTime', ctypes.c_double),           # best lap time
        ('mLastSector1', ctypes.c_double),           # last sector 1
        # last sector 2 (plus sector 1)
        ('mLastSector2', ctypes.c_double),
        ('mLastLapTime', ctypes.c_double),           # last lap time
        # current sector 1 if valid
        ('mCurSector1', ctypes.c_double),
        # current sector 2 (plus sector 1) if valid
        ('mCurSector2', ctypes.c_double),
        ('mNumPitstops', ctypes.c_short),            # number of pitstops made
        # number of outstanding penalties
        ('mNumPenalties', ctypes.c_short),
        # is this the player's vehicle
        ('mIsPlayer', ctypes.c_ubyte),
        # who's in control: -1=nobody (shouldn't get this), 0=local player,
        # 1=local AI, 2=remote, 3 = replay (shouldn't get this)
        ('mControl', ctypes.c_ubyte),
        # between pit entrance and pit exit (not always accurate for remote
        # vehicles)
        ('mInPits', ctypes.c_ubyte),
        ('mPlace', ctypes.c_ubyte),          # 1-based position
        ('mVehicleClass', ctypes.c_ubyte * 32),        # vehicle class
        # time behind vehicle in next higher place
        ('mTimeBehindNext', ctypes.c_double),
        # laps behind vehicle in next higher place
        ('mLapsBehindNext', ctypes.c_int),
        ('mTimeBehindLeader', ctypes.c_double),      # time behind leader
        ('mLapsBehindLeader', ctypes.c_int),         # laps behind leader
        # time this lap was started
        ('mLapStartET', ctypes.c_double),
        ('mPos', rF2Vec3),                  # world position in meters
        # velocity (meters/sec) in local vehicle coordinates
        ('mLocalVel', rF2Vec3),
        # acceleration (meters/sec^2) in local vehicle coordinates
        ('mLocalAccel', rF2Vec3),
        # rows of orientation matrix (use TelemQuat conversions if desired),
        # also converts local
        ('mOri', rF2Vec3 * 3),
        # rotation (radians/sec) in local vehicle coordinates
        ('mLocalRot', rF2Vec3),
        # rotational acceleration (radians/sec^2) in local vehicle coordinates
        ('mLocalRotAccel', rF2Vec3),
        ('mHeadlights', ctypes.c_ubyte),     # status of headlights
        # 0=none, 1=request, 2=entering, 3=stopped, 4 = exiting
        ('mPitState', ctypes.c_ubyte),
        # whether this vehicle is being scored by server (could be off in
        # qualifying or racing heats)
        ('mServerScored', ctypes.c_ubyte),
        # game phases (described below) plus 9=after formation, 10=under
        # yellow, 11 = under blue (not used)
        ('mIndividualPhase', ctypes.c_ubyte),
        # 1-based, can be -1 when invalid
        ('mQualification', ctypes.c_int),
        ('mTimeIntoLap', ctypes.c_double),           # estimated time into lap
        # estimated laptime used for 'time behind' and 'time into lap' (note:
        # this may changed based on vehicle and setup!?)
        ('mEstimatedLapTime', ctypes.c_double),
        # pit group (same as team name unless pit is shared)
        ('mPitGroup', ctypes.c_ubyte * 24),
        # primary flag being shown to vehicle (currently only 0=green or 6 =
        # blue)
        ('mFlag', ctypes.c_ubyte),
        # whether this car has taken a full-course caution flag at the
        # start/finish line
        ('mUnderYellow', ctypes.c_ubyte),
        # 0 = do not count lap or time, 1 = count lap but not time, 2 = count
        # lap and time
        ('mCountLapFlag', ctypes.c_ubyte),
        # appears to be within the correct garage stall
        ('mInGarageStall', ctypes.c_ubyte),
        ('mUpgradePack', ctypes.c_ubyte * 16),  # Coded upgrades
        # location of pit in terms of lap distance
        ('mPitLapDist', ctypes.c_float),
        # sector 1 time from best lap (not necessarily the best sector 1 time)
        ('mBestLapSector1', ctypes.c_float),
        # sector 2 time from best lap (not necessarily the best sector 2 time)
        ('mBestLapSector2', ctypes.c_float),
        ('mExpansion', ctypes.c_ubyte * 48),  # for future use
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2PhysicsOptions(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mTractionControl', ctypes.c_ubyte),  # 0 (off) - 3 (high)
        ('mAntiLockBrakes', ctypes.c_ubyte),   # 0 (off) - 2 (high)
        ('mStabilityControl', ctypes.c_ubyte),  # 0 (off) - 2 (high)
        # 0 (off), 1 (upshifts), 2 (downshifts), 3 (all)
        ('mAutoShift', ctypes.c_ubyte),
        ('mAutoClutch', ctypes.c_ubyte),       # 0 (off), 1 (on)
        ('mInvulnerable', ctypes.c_ubyte),     # 0 (off), 1 (on)
        ('mOppositeLock', ctypes.c_ubyte),     # 0 (off), 1 (on)
        ('mSteeringHelp', ctypes.c_ubyte),     # 0 (off) - 3 (high)
        ('mBrakingHelp', ctypes.c_ubyte),      # 0 (off) - 2 (high)
        ('mSpinRecovery', ctypes.c_ubyte),     # 0 (off), 1 (on)
        ('mAutoPit', ctypes.c_ubyte),          # 0 (off), 1 (on)
        ('mAutoLift', ctypes.c_ubyte),         # 0 (off), 1 (on)
        ('mAutoBlip', ctypes.c_ubyte),         # 0 (off), 1 (on)
        ('mFuelMult', ctypes.c_ubyte),         # fuel multiplier (0x-7x)
        ('mTireMult', ctypes.c_ubyte),         # tire wear multiplier (0x-7x)
        #!!! byte mMechFail;         # mechanical failure setting; 0 (off), 1 (normal), 2 (timescaled)
        ('mAllowPitcrewPush', ctypes.c_ubyte),  # 0 (off), 1 (on)
        #!!! byte mRepeatShifts;     # accidental repeat shift prevention (0-5; see PLR file)
        ('mHoldClutch', ctypes.c_ubyte),       # for auto-shifters at start of race: 0 (off), 1 (on)
        ('mAutoReverse', ctypes.c_ubyte),      # 0 (off), 1 (on)
        ('mAlternateNeutral', ctypes.c_ubyte),  # Whether shifting up and down simultaneously equals neutral
        ('mAIControl', ctypes.c_ubyte),        # Whether player vehicle is currently under AI control
        ('mUnused1', ctypes.c_ubyte),          #
        ('mUnused2', ctypes.c_ubyte),          #
        ('mManualShiftOverrideTime', ctypes.c_float),  # time before auto-shifting can resume after recent manual shift
        ('mAutoShiftOverrideTime', ctypes.c_float),    # time before manual shifting can resume after recent auto shift
        ('mSpeedSensitiveSteering', ctypes.c_float),   # 0.0 (off) - 1.0
        ('mSteerRatioSpeed', ctypes.c_float),          # speed (m/s) under which lock gets expanded to full
    ]


class rF2TrackRulesCommand(CtypesEnum):
    AddFromTrack = 0
# untranslated AddFromPit,                   // exited pit during full-course yellow
# untranslated AddFromUndq,                  // during a full-course yellow, the admin reversed a disqualification
# untranslated RemoveToPit,                  // entered pit during full-course yellow
# untranslated RemoveToDnf,                  // vehicle DNF'd during full-course yellow
# untranslated RemoveToDq,                   // vehicle DQ'd during full-course yellow
# untranslated RemoveToUnloaded,             // vehicle unloaded (possibly kicked out or banned) during full-course yellow
# untranslated MoveToBack,                   // misbehavior during full-course yellow, resulting in the penalty of being moved to the back of their current line
# untranslated LongestTime,                  // misbehavior during full-course yellow, resulting in the penalty of being moved to the back of the longest line
# untranslated Maximum                       // should be last

#untranslated [StructLayout(LayoutKind.Sequential, Pack = 4)]


class rF2TrackRulesAction(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        #!!!         ('mCommand', ctypes.c_int),        # recommended action
        # slot ID if applicable
        ('mID', ctypes.c_int),
        # elapsed time that event occurred, if applicable
        ('mET', ctypes.c_double),
    ]


class rF2TrackRulesColumn(CtypesEnum):
    LeftLane = 0
# untranslated MidLefLane,                    // mid-left
# untranslated MiddleLane,                    // middle
# untranslated MidrRghtLane,                  // mid-right
# untranslated RightLane,                     // right (outside)
    MaxLanes = 1                     # should be after the valid static lane choices
    Invalid = MaxLanes
# untranslated FreeChoice,                    // free choice (dynamically chosen by driver)
# untranslated Pending,                       // depends on another participant's free choice (dynamically set after another driver chooses)
# untranslated Maximum                        // should be last

#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2TrackRulesParticipant(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mID', ctypes.c_int),                             # slot ID
        # 0-based place when caution came out (not valid for formation laps)
        ('mFrozenOrder', ctypes.c_short),
        # 1-based place (typically used for the initialization of the formation
        # lap track order)
        ('mPlace', ctypes.c_short),
        # a rating of how much this vehicle is contributing to a yellow flag
        # (the sum of all vehicles is compared to
        # TrackRulesV01::mSafetyCarThreshold)
        ('mYellowSeverity', ctypes.c_float),
        # equal to ( ( ScoringInfoV01::mLapDist * this->mRelativeLaps ) +
        # VehicleScoringInfoV01::mLapDist )
        ('mCurrentRelativeDistance', ctypes.c_double),
        #!!! int mRelativeLaps;                    # current formation/caution laps relative to safety car (should generally be zero except when safety car crosses s/f line); this can be decremented to implement 'wave around' or 'beneficiary rule' (a.k.a. 'lucky dog' or 'free pass')
        ('mColumnAssignment', ctypes.c_int),  # which column (line/lane) that participant is supposed to be in
        ('mPositionAssignment', ctypes.c_int),              # 0-based position within column (line/lane) that participant is supposed to be located at (-1 is invalid)
        #!!!         byte mPitsOpen;                       # whether the rules allow this particular vehicle to enter pits right now (input is 2=false or 3=true; if you want to edit it, set to 0=false or 1 = true)
        ('mUpToSpeed', ctypes.c_ubyte),                      # while in the frozen order, this flag indicates whether the vehicle can be followed (this should be false for somebody who has temporarily spun and hasn't gotten back up to speed yet)
        ('mUnused', ctypes.c_ubyte * 2),                       #
        ('mGoalRelativeDistance', ctypes.c_double),         # calculated based on where the leader is, and adjusted by the desired column spacing and the column/position assignments
        #!!!         ('mMessage;                  # a message for this participant to explain what is going on (untranslated', ctypes.c_ubyte*96), it will get run through translator on client machines)
        ('mExpansion', ctypes.c_ubyte * 192),
    ]


class rF2TrackRulesStage(CtypesEnum):
    FormationInit = 0
# untranslated FormationUpdate,             // update of the formation lap
# untranslated Normal,                      // normal (non-yellow) update
# untranslated CautionInit,                 // initialization of a full-course yellow
# untranslated CautionUpdate,               // update of a full-course yellow
# untranslated Maximum                      // should be last

#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2TrackRules(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mCurrentET', ctypes.c_double),                    # current time
        #!!! rF2TrackRulesStage mStage;            # current stage
        # column assignment where pole position seems to be located
        ('mPoleColumn', ctypes.c_int),
        # number of recent actions
        ('mNumActions', ctypes.c_int),
        ('pointer1', ctypes.c_ubyte * 8),
        # number of participants (vehicles)
        ('mNumParticipants', ctypes.c_int),
        # whether yellow flag was requested or sum of participant
        # mYellowSeverity's exceeds mSafetyCarThreshold
        ('mYellowFlagDetected', ctypes.c_ubyte),
        # whether mYellowFlagLaps (below) is an admin request (0=no 1=yes 2 =
        # clear yellow)
        ('mYellowFlagLapsWasOverridden', ctypes.c_ubyte),
        # whether safety car even exists
        ('mSafetyCarExists', ctypes.c_ubyte),
        # whether safety car is active
        ('mSafetyCarActive', ctypes.c_ubyte),
        ('mSafetyCarLaps', ctypes.c_int),                  # number of laps
        # the threshold at which a safety car is called out (compared to the
        # sum of TrackRulesParticipantV01::mYellowSeverity for each vehicle)
        ('mSafetyCarThreshold', ctypes.c_float),
        # safety car lap distance
        ('mSafetyCarLapDist', ctypes.c_double),
        # where the safety car starts from
        ('mSafetyCarLapDistAtStart', ctypes.c_float),
        # where the waypoint branch to the pits breaks off (this may not be
        # perfectly accurate)
        ('mPitLaneStartDist', ctypes.c_float),
        # the front of the teleport locations (a useful first guess as to where
        # to throw the green flag)
        ('mTeleportLapDist', ctypes.c_float),
        ('mInputExpansion', ctypes.c_ubyte * 256),
        # see ScoringInfoV01 for values
        ('mYellowFlagState', ctypes.c_ubyte),
        # suggested number of laps to run under yellow (may be passed in with
        # admin command)
        ('mYellowFlagLaps', ctypes.c_short),
        # 0=no change, 1=go active, 2 = head for pits
        ('mSafetyCarInstruction', ctypes.c_int),
        # maximum speed at which to drive
        ('mSafetyCarSpeed', ctypes.c_float),
        # minimum spacing behind safety car (-1 to indicate no limit)
        ('mSafetyCarMinimumSpacing', ctypes.c_float),
        # maximum spacing behind safety car (-1 to indicate no limit)
        ('mSafetyCarMaximumSpacing', ctypes.c_float),
        # minimum desired spacing between vehicles in a column (-1 to indicate
        # indeterminate/unenforced)
        ('mMinimumColumnSpacing', ctypes.c_float),
        # maximum desired spacing between vehicles in a column (-1 to indicate
        # indeterminate/unenforced)
        ('mMaximumColumnSpacing', ctypes.c_float),
        # minimum speed that anybody should be driving (-1 to indicate no
        # limit)
        ('mMinimumSpeed', ctypes.c_float),
        # maximum speed that anybody should be driving (-1 to indicate no
        # limit)
        ('mMaximumSpeed', ctypes.c_float),
        # a message for everybody to explain what is going on (which will get
        # run through translator on client machines)
        ('mMessage', ctypes.c_ubyte * 96),
        ('pointer2', ctypes.c_ubyte * 8),
        ('mInputOutputExpansion', ctypes.c_ubyte * 256),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2MappedBufferVersionBlock(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2MappedBufferVersionBlockWithSize(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
        # How many bytes of the structure were written during the last update.
        ('mBytesUpdatedHint', ctypes.c_int),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2Telemetry(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
        # How many bytes of the structure were written during the last update.
        ('mBytesUpdatedHint', ctypes.c_int),
        # current number of vehicles
        ('mNumVehicles', ctypes.c_int),
        ('mVehicles', rF2VehicleTelemetry * rFactor2Constants.MAX_MAPPED_VEHICLES),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2Scoring(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
        # How many bytes of the structure were written during the last update.
        ('mBytesUpdatedHint', ctypes.c_int),
        #!!! rF2ScoringInfo mScoringInfo;
        ('mVehicles', rF2VehicleScoring * rFactor2Constants.MAX_MAPPED_VEHICLES),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2Rules(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
        # How many bytes of the structure were written during the last update.
        ('mBytesUpdatedHint', ctypes.c_int),
        ('mTrackRules', rF2TrackRules),
        ('mActions', rF2TrackRulesAction * rFactor2Constants.MAX_MAPPED_VEHICLES),
        ('mParticipants', rF2TrackRulesParticipant * \
         rFactor2Constants.MAX_MAPPED_VEHICLES),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, Pack = 4)]


class rF2TrackedDamage(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Max impact magnitude.  Tracked on every telemetry update, and reset
        # on visit to pits or Session restart.
        ('mMaxImpactMagnitude', ctypes.c_double),
        # Accumulated impact magnitude.  Tracked on every telemetry update, and
        # reset on visit to pits or Session restart.
        ('mAccumulatedImpactMagnitude', ctypes.c_double),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, Pack = 4)]


class rF2VehScoringCapture(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # slot ID (note that it can be re-used in multiplayer after someone
        # leaves)
        ('mID', ctypes.c_int),
        ('mPlace', ctypes.c_ubyte),
        ('mIsPlayer', ctypes.c_ubyte),
        # 0=none, 1=finished, 2=dnf, 3 = dq
        ('mFinishStatus', ctypes.c_ubyte),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, Pack = 4)]


class rF2SessionTransitionCapture(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ('mGamePhase', ctypes.c_ubyte),
        ('mSession', ctypes.c_int),
        ('mNumScoringVehicles', ctypes.c_int),
        ('mScoringVehicles', rF2VehScoringCapture * rFactor2Constants.MAX_MAPPED_VEHICLES),
    ]
#untranslated [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi, Pack = 4)]


class rF2Extended(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        # Incremented right before buffer is written to.
        ('mVersionUpdateBegin', ctypes.c_int),
        # Incremented after buffer write is done.
        ('mVersionUpdateEnd', ctypes.c_int),
        ('mVersion', ctypes.c_ubyte * 12),                            # API version
        # Is 64bit plugin?
        ('is64bit', ctypes.c_ubyte),
        ('mPhysics', rF2PhysicsOptions),
        ('mTrackedDamages', rF2TrackedDamage * rFactor2Constants.MAX_MAPPED_IDS),
        # in realtime as opposed to at the monitor (reported via last
        # EnterRealtime/ExitRealtime calls).
        ('mInRealtimeFC', ctypes.c_ubyte),
        # multimedia thread started (reported via ThreadStarted/ThreadStopped
        # calls).
        ('mMultimediaThreadStarted', ctypes.c_ubyte),
        # simulation thread started (reported via ThreadStarted/ThreadStopped
        # calls).
        ('mSimulationThreadStarted', ctypes.c_ubyte),
        # Set to true on Session Started, set to false on Session Ended.
        ('mSessionStarted', ctypes.c_ubyte),
        # Ticks when session started.
        ('mTicksSessionStarted', ctypes.c_double),
        # Ticks when session ended.
        ('mTicksSessionEnded', ctypes.c_double),
        # Contains partial internals capture at session transition time.
        ('mSessionTransitionCapture', rF2SessionTransitionCapture),
        ('mDisplayedMessageUpdateCapture', ctypes.c_ubyte * 128),
        ('mDirectMemoryAccessEnabled', ctypes.c_ubyte),
        #!!! Int64 mTicksStatusMessageUpdated;             # Ticks when status message was updated;
        ('mStatusMessage', ctypes.c_ubyte * rFactor2Constants.MAX_STATUS_MSG_LEN),
        #!!! Int64 mTicksLastHistoryMessageUpdated;        # Ticks when last message history message was updated;
        ('mLastHistoryMessage', ctypes.c_ubyte * rFactor2Constants.MAX_STATUS_MSG_LEN),
        ('mCurrentPitSpeedLimit', ctypes.c_float),                # speed limit m/s.
        ('mSCRPluginEnabled', ctypes.c_ubyte),                           # Is Stock Car Rules plugin enabled?
        ('mSCRPluginDoubleFileType', ctypes.c_int),                     # Stock Car Rules plugin DoubleFileType value, only meaningful if mSCRPluginEnabled is true.
        ('mTicksLSIPhaseMessageUpdated', ctypes.c_double),               # Ticks when last LSI phase message was updated.
        ('mLSIPhaseMessage', ctypes.c_ubyte * rFactor2Constants.MAX_RULES_INSTRUCTION_MSG_LEN),
        ('mTicksLSIPitStateMessageUpdated', ctypes.c_double),             # Ticks when last LSI pit state message was updated.
        ('mLSIPitStateMessage', ctypes.c_ubyte * rFactor2Constants.MAX_RULES_INSTRUCTION_MSG_LEN),
        ('mTicksLSIOrderInstructionMessageUpdated', ctypes.c_double),     # Ticks when last LSI order instruction message was updated.
        ('mLSIOrderInstructionMessage', ctypes.c_ubyte * rFactor2Constants.MAX_RULES_INSTRUCTION_MSG_LEN),
        ('mTicksLSIRulesInstructionMessageUpdated', ctypes.c_double),     # Ticks when last FCY rules message was updated.  Currently, only SCR plugin sets that.
        ('mLSIRulesInstructionMessage', ctypes.c_ubyte * rFactor2Constants.MAX_RULES_INSTRUCTION_MSG_LEN),
    ]
#
#


class SimInfo:
    def __init__(self):

        self._rf2_tele = mmap.mmap(0, ctypes.sizeof(
            rF2Telemetry), "$rFactor2SMMP_Telemetry$")
        self.Rf2Tele = rF2Telemetry.from_buffer(self._rf2_tele)
        self._rf2_scor = mmap.mmap(0, ctypes.sizeof(
            rF2Scoring), "$rFactor2SMMP_Scoring$")
        self.Rf2Scor = rF2Scoring.from_buffer(self._rf2_scor)
        self._rf2_ext = mmap.mmap(0, ctypes.sizeof(
            rF2Extended), "$rFactor2SMMP_Extended$")
        self.Rf2Ext = rF2Extended.from_buffer(self._rf2_ext)

    def close(self):
        # This didn't help with the errors
        try:
            self._rf2_tele.close()
            self._rf2_scor.close()
            self._rf2_ext.close()
        except BufferError:  # "cannot close exported pointers exist"
            pass

    def __del__(self):
        self.close()


if __name__ == '__main__':
    # Example usage
    info = SimInfo()
    version = info.Rf2Ext.mVersion
    v = ''
    for i in range(8):
        v += str(version[i])
    v = bytes(version).partition(b'\0')[0].decode().rstrip()
    # 1.0 clutch down, 0 clutch up
    clutch = info.Rf2Tele.mVehicles[0].mUnfilteredClutch
    gear = info.Rf2Tele.mVehicles[0].mGear  # -1 to 6
    print('Map version: %s\n'
          'Gear: %d, Clutch position: %d' % (v, gear, clutch))
