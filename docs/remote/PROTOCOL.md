# Remote protocol v1 — server 0.4.3

Ingest: type=ingest, protocolVersion=1, mode=lmu|demo, streamId, sessionId, seq,
capturedAt (Unix milliseconds), gameTime (seconds), status, session, cars, pilot.
Session includes track, lengthM, scoringTime and phase. Cars use persistent slot
IDs within a session; scalar coordinates are metres. Native LMU capture sends
localVelocityMps (x,y,z vector), whose magnitude is calculated on the VPS; demo
fixtures may send scalar speedMps. Pilot includes
fuel in litres, gear, rpm, inputs, lap/lapValid, wheels in FL FR RL RR order.
Native surfaceTemperaturesK contains three original Kelvin readings; the VPS
computes their mean and Celsius display. Tyre pressure is kPa, brake temperature Celsius;
mWear is displayed as tyre condition: mWear × 100 percent, with 100% meaning new.

Sample extraction and type validation live in remote/native.py and compute.py.
With overlayProtocolVersion=1, the collector also supplies a packed rawSnapshot
for the original LMU reader and captured optional REST records. The VPS runs
12 original data modules and produces values for 76 web views. The collector
does not perform driving calculations. High-frequency sample batches are not carried.

Go schedules received frames for a server-only Python worker. Worker responses are
presentation snapshots, or an error. Invalid ingest closes the source connection.
A reconnect starts a new compute worker and warm-up, not restored history.
Out-of-order seq and numerical NaN/Infinity are rejected. A seq gap or game-time
gap >1 second invalidates the prototype fuel prediction; refuel and pit/invalid
laps also exclude samples. Original full modules run on the server; their loaded
code is reused across delivery gaps, while calculated sample history is reset.

Viewer receives {type:update,serverTime,sourceAgeMs,ingestAgeMs,sourceConnected,computeMs,state}.
SourceAgeMs measures time since relay reception, NOT end-to-end network latency.
State retains capturedAt for a future clock-synchronisation implementation.
The UI declares old/disconnected data instead of promising current state.
Viewer sends no game-control messages. /healthz checks relay only.

Auth: SPOTTER_PILOT_TOKEN in Authorization Bearer for /ws/pilot. Viewer login via
same-origin POST /api/session {token}; the server sets a signed 12-hour HttpOnly
SameSite=Strict cookie. /ws/view requires that cookie and same Origin. TLS is
terminated by Caddy; the Go server must stay bound to loopback.

## Delivery scheduling (0.4.3)

`X-Spotter-Ack: 1` negotiates JSON `{type: "ack", seq: N}` after relay receipt,
independent of calculation completion. The collector keeps at most two
unacknowledged frames. There is one pending calculation slot: a newer frame
replaces an older pending frame while the current calculation runs. Therefore
receipt does not guarantee presentation of every sequence number. Calculation
sequence gaps invalidate accumulated samples conservatively, while loaded
modules are reused. Stateful predictions require usable samples after gaps.

`sourceAgeMs` is the age since relay receipt of the sample used for the last
presentation, including queue and calculation time. `ingestAgeMs` is the age
of the newest received frame; it is diagnostic only and never makes an old
presentation fresh. The viewer marks results older than one second as stale.
A calculation timeout restarts the worker without closing pilot transport;
invalid core protocol frames are still rejected. No secrets are added to frames.
