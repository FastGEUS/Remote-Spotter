"""Raw LMU blocks, compressed for transport. No derived data on the pilot PC."""
import base64
import ctypes
import zlib
from types import SimpleNamespace as NS
from pyLMUSharedMemory import lmu_data as D

BLOCKS = (('generic',D.LMUGeneric),('scoring',D.LMUScoringData),('telemetry',D.LMUTelemetryData))
SIZE = sum(ctypes.sizeof(kind) for _,kind in BLOCKS)
LAYOUT = 'pyLMU-v2.50.0-le-pack4'


def encode(data):
    raw = b''.join(bytes(getattr(data,name)) for name,_ in BLOCKS)
    return {'layout':LAYOUT,'data':base64.b64encode(zlib.compress(raw,1)).decode('ascii')}


def decode(value):
    if not isinstance(value,dict) or value.get('layout') != LAYOUT:
        raise ValueError('Incompatible LMU snapshot layout; update both collector and server')
    encoded = value.get('data')
    if not isinstance(encoded,str) or len(encoded)>SIZE*2:
        raise ValueError('Snapshot exceeds bounded layout size')
    try:
        compressed = base64.b64decode(encoded,validate=True)
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed,SIZE+1)
        if len(raw)!=SIZE or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError('Invalid compressed snapshot size')
    except (zlib.error,ValueError) as error:
        raise ValueError('Invalid LMU snapshot') from error
    data = NS()
    offset = 0
    for name,kind in BLOCKS:
        length = ctypes.sizeof(kind)
        setattr(data,name,kind.from_buffer_copy(raw[offset:offset+length]))
        offset += length
    n = data.scoring.scoringInfo.mNumVehicles
    active = data.telemetry.activeVehicles
    idx = data.telemetry.playerVehicleIdx
    if not 0<=n<=104 or active>104 or (data.telemetry.playerHasVehicle and idx>=active):
        raise ValueError('Invalid snapshot vehicle counts')
    ids = [v.mID for v in data.scoring.vehScoringInfo[:n]]
    tele_ids = [v.mID for v in data.telemetry.telemInfo[:active]]
    if len(set(ids))!=len(ids) or len(set(tele_ids))!=len(tele_ids):
        raise ValueError('Duplicate snapshot vehicle IDs')
    return data
