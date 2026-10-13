# iRacing data sources — client 0.6.11 / server 0.4.12

Pilot capture selects available SDK variables from one frozen buffer. Absent or
non-finite variables remain unavailable. Four raw session-info sections are
compressed on the client and parsed on the VPS. Source: `remote/iracing.py`.
Normalization and estimates: `remote/iracing_compute.py`.

| Dashboard data | SDK source | Server conversion / limitation |
| --- | --- | --- |
| Session identity / time | `SessionUniqueID`, `SessionNum`, `SessionTime` | Changes of SDK generation or session produce a new source session; network retries keep the capture reader. |
| Player slot | `PlayerCarIdx`; fallback `DriverInfo.DriverCarIdx` | Slot is an SDK index, independent of position and car number. |
| Roster / class / number | `DriverInfo.Drivers` | All non-pace-car entries, including cars temporarily outside the world. Preserve leading zeroes in car numbers. |
| Overall / class position | `CarIdxPosition`, `CarIdxClassPosition`; player fallbacks `PlayerCarPosition`, `PlayerCarClassPosition` | Unknown position displays a dash. The map receives the full available roster. The standings table selects up to five cars ahead and five behind the player by overall position. |
| Completed laps / player lap | `CarIdxLapCompleted`, `Lap`; fallback `CarIdxLap`, completed laps + 1 | `Lap=-1` is an unavailable SDK state, not a fatal frame error. |
| Progress | `CarIdxLapDistPct`; player fallback `LapDistPct` | Negative or absent progress means no map projection for that car. |
| World / pits | `CarIdxTrackSurface`, `CarIdxOnPitRoad`, `PlayerTrackSurface`, `PlayerCarTowTime` | Cars outside the world are not plotted. Pit/tow movement is not recorded into the driven map. |
| Race gap to leader | `CarIdxF2Time` | Only `SessionType=Race`. In other sessions the table shows `CarIdxBestLapTime`. |
| Player-relative interval | Lap-progress difference and player lap pace | Estimate, not an official timing loop gap. |
| Map geometry | `Speed` with `YawNorth` or `Yaw`; optional `Lat`/`Lon` | Integration or local GPS projection on VPS. Approximate driven line; full-lap cache persists on VPS. |
| Track length / identity | `WeekendInfo.TrackLength`, `TrackID`, `TrackConfigName`, track display name | km, m or mi converted to metres; distinct layouts have separate caches. |
| Sector boundaries / times | `SplitTimeInfo.Sectors.SectorStartPct`, `LapCurrentLapTime`, SDK session time / progress | Interpolated crossing times, nominal capture 20 Hz. No invented equal thirds when metadata is absent. |
| Speed / RPM / gear | `Speed`, `RPM`, `Gear` | m/s → km/h in display; SDK reverse and neutral preserved. |
| Pedals | `Throttle`, `Brake`, `Clutch`; optional `*Raw` | Clutch displayed as `1 - SDK value`, meaning 0 released and 1 pressed. |
| Steering | `SteeringWheelAngle`, `SteeringWheelAngleMax` | Radians → degrees; normalized input uses half the full range. |
| G force | `LatAccel`, `LongAccel` | m/s² divided by 9.80665. |
| Fuel / range | `FuelLevel`, `DriverCarFuelMaxLtr` | Complete observed laps estimate consumption. Pits, incidents and sustained time discontinuities exclude samples. |
| Tyre carcass | `LF/RF/LR/RRtempCL`, `tempCM`, `tempCR` | °C, left/middle/right SDK samples; average per wheel. ICO overlay reverses left tyres to inner/centre/outer order. Last valid sample retained within the same source session/car. Not a continuous surface-temperature sensor. |
| Tyre condition | `LF/RF/LR/RRwearL`, `wearM`, `wearR` | Mean of the three remaining-tread fractions → percent; 100% means new. Missing values are not replaced by zeroes. |
| Tyre pressure | Optional `LF/RF/LR/RRpressure`; fallback `*coldPressure` | kPa. Distinguish pit measurement from cold garage setting. |
| Air / track temperature | `AirTemp`, `TrackTempCrew`; track fallback `TrackTemp` | °C. |
| Rain / wetness | `Precipitation`, `TrackWetness`, `WeatherDeclaredWet` | Wetness remains a categorical SDK value; it is not silently converted to a rain percentage. |
| Engine temperatures | `WaterTemp`, `OilTemp` | Display only available values. |
| Brake bias / TC / ABS | `dcBrakeBias`, `dcTractionControl`, `dcABS` | Bias percent → normalized fraction; controls depend on the car. |
| Flag display | `SessionFlags`, player `CarIdxSessionFlags` | Whole-session and personal flags. No verified sector-local flag channel. |
| Side proximity | `CarLeftRight`; optional `CarDistAhead`, `CarDistBehind` | Proximity indication, not a coordinate radar. |
| Session limit | `SessionTimeRemain`, `SessionLapsRemainEx`; fallback `SessionLapsRemain`; `SessionLapsTotal` / session-info limit | SDK unlimited-lap sentinel is not a real lap limit. |

The API capability catalog distinguishes partial support, pit samples and
unsupported overlays. Diagnostics report missing selected channels and map
inputs. Authentication tokens and private SSH keys are not included in these
diagnostics.

References:

- [SDK reader implementation](https://github.com/kutu/pyirsdk/blob/master/irsdk.py)
- [SDK variable descriptions](https://github.com/kutu/pyirsdk/blob/master/vars.txt)
- [iRacing garage measurement descriptions](https://ir-core-sites.iracing.com/members/pdfs/iRacing_Setup_Guide.pdf)

SDK capture selects 129 variable names and four metadata sections; this is not a full SDK dump. The client requests capture at 20 Hz. IBT replay, reading a growing IBT file, and Web Data API access are not implemented. Continuous surface tyre temperature and a validated wear forecast are not provided.
