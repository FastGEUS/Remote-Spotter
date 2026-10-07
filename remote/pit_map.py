"""Persistent pit-lane geometry supplement to TinyPedal's circuit map."""
import json
import math


class PitMap:
    def __init__(self,runtime):
        self.directory=runtime.cfg.directory/'pit_lane'
        self.directory.mkdir(exist_ok=True)
        self.points=[]
        self.recording=[]
        self.was_in_pit=False
        self.track=None

    def update(self,reader):
        track=reader.session.track_name()
        if track!=self.track:
            self.track=track;self.points=[];self.recording=[];self.was_in_pit=False
            target=self.directory/(track+'.json')
            if target.exists() and target.stat().st_size<512000:
                loaded=json.loads(target.read_text())
                if isinstance(loaded,list) and len(loaded)<=5000 and all(isinstance(p,list) and len(p)==2 and all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<1e7 for v in p) for p in loaded):
                    self.points=loaded
        in_pit=reader.vehicle.in_pits() and not reader.vehicle.in_garage()
        point=[reader.vehicle.position_longitudinal(),-reader.vehicle.position_lateral()]
        if in_pit:
            if not self.was_in_pit:self.recording=[]
            if len(self.recording)<5000 and (not self.recording or math.dist(point,self.recording[-1])>3):self.recording.append(point)
        elif self.was_in_pit and len(self.recording)>3:
            self.recording.append(point);self.points=self.recording
            target=self.directory/(track+'.json');temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.points,separators=(',',':')));temporary.replace(target)
            self.recording=[]
        self.was_in_pit=in_pit
        return self.points or self.recording
