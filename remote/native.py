"""Windows-only read-only LMU mapping reader. Never creates a missing mapping.

Only uses the pinned upstream ctypes definitions; no overlays, Qt
or calculations run here. Must be validated against the installed LMU header.
"""
import ctypes
import platform
from pyLMUSharedMemory.lmu_data import LMUObjectOut, LMUConstants
from .snapshot import encode


def decode(value):
    return bytes(value).split(b"\0", 1)[0].decode("utf-8", errors="replace")


class NativeReader:
    game = 'lmu'
    def __init__(self):
        if platform.system() != "Windows":
            raise RuntimeError("LMU capture requires Windows; use --demo on Linux")
        from ctypes import wintypes
        self.dll = ctypes.WinDLL("kernel32", use_last_error=True)
        self.dll.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self.dll.OpenFileMappingW.restype = wintypes.HANDLE
        self.dll.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        self.dll.MapViewOfFile.restype = ctypes.c_void_p
        self.dll.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self.dll.UnmapViewOfFile.restype = wintypes.BOOL
        self.dll.CloseHandle.argtypes = [wintypes.HANDLE]
        self.dll.CloseHandle.restype = wintypes.BOOL
        self.handle = None
        self.view = None

    def close(self):
        if self.view:
            self.dll.UnmapViewOfFile(self.view)
        if self.handle:
            self.dll.CloseHandle(self.handle)
        self.view = self.handle = None

    def read(self):
        size = ctypes.sizeof(LMUObjectOut)
        if not self.view:
            self.handle = self.dll.OpenFileMappingW(4, False, LMUConstants.LMU_SHARED_MEMORY_FILE)
            if not self.handle:
                return None
            self.view = self.dll.MapViewOfFile(self.handle, 4, 0, 0, size)
            if not self.view:
                self.close()
                raise RuntimeError("Mapping is smaller/incompatible with pinned LMU structure")
        # Bounded consistency retries. This is a best-effort copy, not a game-side
        # lock: marker checks cannot prove every byte was written atomically.
        for _ in range(3):
            before = LMUObjectOut.from_buffer_copy(ctypes.string_at(self.view, size))
            after = LMUObjectOut.from_buffer_copy(ctypes.string_at(self.view, size))
            if self.marker(before) == self.marker(after):
                return self.extract(after)
        return None

    @staticmethod
    def marker(data):
        t = data.telemetry
        idx = t.playerVehicleIdx
        et = t.telemInfo[idx].mElapsedTime if idx < LMUConstants.MAX_MAPPED_VEHICLES else -1
        return (data.scoring.scoringInfo.mCurrentET, et,
                data.generic.events.SME_UPDATE_SCORING,
                data.generic.events.SME_UPDATE_TELEMETRY,
                data.scoring.scoringInfo.mNumVehicles, t.activeVehicles)

    @staticmethod
    def extract(data):
        scoring = data.scoring.scoringInfo
        n = scoring.mNumVehicles
        if not 0 <= n <= LMUConstants.MAX_MAPPED_VEHICLES:
            raise RuntimeError("Invalid vehicle count; check game/header compatibility")
        cars = []
        for v in data.scoring.vehScoringInfo[:n]:
            cars.append({"id": v.mID, "driver": decode(v.mDriverName),
                         "class": decode(v.mVehicleClass), "place": int(v.mPlace),
                         "laps": int(v.mTotalLaps), "lapDistM": v.mLapDist,
                         "x": v.mPos.x, "z": v.mPos.z, "inPit": bool(v.mInPits),
                         "localVelocityMps": [v.mLocalVel.x, v.mLocalVel.y, v.mLocalVel.z]})
        telemetry = data.telemetry
        pilot = None
        game_time = scoring.mCurrentET
        idx = telemetry.playerVehicleIdx
        if telemetry.playerHasVehicle and idx < min(telemetry.activeVehicles, LMUConstants.MAX_MAPPED_VEHICLES):
            t = telemetry.telemInfo[idx]
            if any(c["id"] == t.mID for c in cars):
                scored = next(v for v in data.scoring.vehScoringInfo[:n] if v.mID == t.mID)
                game_time = t.mElapsedTime
                pilot = {"id": t.mID, "lap": t.mLapNumber, "fuelL": t.mFuel,
                         "localVelocityMps": [t.mLocalVel.x, t.mLocalVel.y, t.mLocalVel.z],
                         "gear": t.mGear, "rpm": t.mEngineRPM,
                         "throttle": t.mFilteredThrottle, "brake": t.mFilteredBrake,
                         "lapValid": not bool(t.mLapInvalidated),
                         "strategyInputs": {"fuelCapacityL": t.mFuelCapacity,
                                            "virtualEnergyFraction": float(t.mVirtualEnergy),
                                            "lapStartTime": t.mLapStartET,
                                            "lastLapTime": scored.mLastLapTime,
                                            "inGarage": bool(scored.mInGarageStall)},
                         "wheels": [{"surfaceTemperaturesK": list(w.mTemperature),
                                     "pressureKpa": w.mPressure, "wear": w.mWear,
                                     "brakeC": w.mBrakeTemp} for w in t.mWheels]}
        return {"gameTime": game_time, "rawSnapshot": encode(data),
                "status": "live" if scoring.mInRealtime and pilot else "garage",
                "sourceSession": [decode(scoring.mTrackName), scoring.mSession,
                                  data.generic.events.SME_START_SESSION],
                "session": {"track": decode(scoring.mTrackName), "lengthM": scoring.mLapDist,
                            "phase": int(scoring.mGamePhase), "scoringTime": scoring.mCurrentET,
                            "sessionType": int(scoring.mSession), "endTime": scoring.mEndET,
                            "maxLaps": int(scoring.mMaxLaps)},
                "cars": cars, "pilot": pilot}
