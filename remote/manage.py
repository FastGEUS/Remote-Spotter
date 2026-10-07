"""Import existing TinyPedal maps or notes into the server's persistent state."""
import argparse
import csv
import math
import os
from pathlib import Path
from xml.etree import ElementTree as ET
from .headless import Runtime


def import_map(source,track,state_dir):
    raw=Path(source).read_bytes()
    if len(raw)>2*1024*1024 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('SVG must contain bounded geometry without XML entities')
    root=ET.fromstring(raw)
    parsed={}
    sectors=None
    for element in root.iter():
        tag=element.tag.split('}')[-1]
        if tag=='polyline' and element.get('id') in ('map','dist'):
            pairs=element.get('points','').split()
            if not 3<=len(pairs)<=20000:
                raise ValueError('Invalid or oversized coordinate count')
            points=[]
            for pair in pairs:
                values=[float(v) for v in pair.split(',')]
                if len(values)!=2 or any(not math.isfinite(v) or abs(v)>1e7 for v in values):
                    raise ValueError('Invalid coordinate')
                points.append(tuple(values))
            parsed[element.get('id')]=tuple(points)
        elif tag=='desc' and sectors is None:
            sectors=tuple(int(v) for v in (element.text or '').split(','))
    if set(parsed)!= {'map','dist'} or len(parsed['map'])!=len(parsed['dist']) or sectors is None or len(sectors)!=2 or any(not 0<=v<len(parsed['map']) for v in sectors):
        raise ValueError('TinyPedal map requires map/dist polylines and sector indices')
    runtime=Runtime(state_dir)
    try:
        formatter=runtime.load('formatter');safe=formatter.strip_invalid_char(track)
        if safe!=track or runtime.load('validator').invalid_save_name(track):
            raise ValueError('Use the exact sanitized TinyPedal track name')
        maps=runtime.load('userfile.track_map')
        maps.save_track_map_file(filepath=runtime.cfg.path.track_map,filename=track,view_box=root.get('viewBox','0 0 100 100'),raw_coords=parsed['map'],raw_dists=parsed['dist'],sector_index=sectors,decimals=4)
    finally:runtime.close()


def import_notes(source,track,kind,state_dir):
    raw=Path(source).read_bytes()
    if len(raw)>1024*1024:
        raise ValueError('Notes file exceeds limit')
    text=raw.decode('utf-8-sig')
    runtime=Runtime(state_dir)
    try:
        if runtime.load('formatter').strip_invalid_char(track)!=track or runtime.load('validator').invalid_save_name(track):
            raise ValueError('Invalid track name')
        notes=runtime.load('userfile.track_notes')
        header=notes.HEADER_PACE_NOTES if kind=='pace' else notes.HEADER_TRACK_NOTES
        parsed=notes.parse_csv_notes_only(iter(text.splitlines(keepends=True)),header)
        if not parsed or len(parsed)>5000:
            raise ValueError('No valid TinyPedal notes or too many entries')
        directory=runtime.cfg.path.pace_notes if kind=='pace' else runtime.cfg.path.track_notes
        extension='.tppn' if kind=='pace' else '.tptn'
        destination=Path(directory)/(track+extension)
        temporary=destination.with_suffix('.tmp')
        temporary.write_text(text,encoding='utf-8')
        temporary.replace(destination)
    finally:runtime.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['import-map','import-notes'])
    parser.add_argument('file')
    parser.add_argument('--track',required=True)
    parser.add_argument('--kind',choices=['pace','track'],default='track')
    parser.add_argument('--state-dir',default=os.environ.get('SPOTTER_STATE_DIR','/var/lib/spotter'))
    args=parser.parse_args()
    if args.operation=='import-map':import_map(args.file,args.track,args.state_dir)
    else:import_notes(args.file,args.track,args.kind,args.state_dir)
    print('Imported. Reconnect the pilot to reload track data.')


if __name__=='__main__':main()
