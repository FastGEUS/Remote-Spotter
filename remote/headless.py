"""Frame-driven execution of pinned TinyPedal data modules, without Qt.

Only two GUI dependencies are excluded: font-weight lookup and preset GUI
validation. Data module event.wait loops yield to the remote frame scheduler.
All calculation bodies and file formats remain the original upstream source.
"""
import ast
import copy
import importlib.abc
import importlib.util
import json
import logging
import os
import sys
import types
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
from .upstream import ROOT


class FrameLoop(ast.NodeTransformer):
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == '_event_wait':
            return ast.copy_location(ast.Yield(ast.Constant(False)), node)
        return self.generic_visit(node)


class SourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, name):
        self.name = name
        self.now = 0

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith(self.name + '.'):
            return None
        local = ROOT / 'tinypedal' / fullname[len(self.name)+1:].replace('.', '/')
        if local.is_dir():
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if local.with_suffix('.py').is_file():
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        relative = module.__name__[len(self.name)+1:]
        path = ROOT / 'tinypedal' / relative.replace('.', '/')
        if path.is_dir():
            module.__path__ = [str(path)]
            return  # Package initialization opens Qt; data imports don't need it.
        path = path.with_suffix('.py')
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        body = []
        for node in tree.body:
            # Font weights are presentation-only; never load or imitate Qt.
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('PySide2'):
                continue
            if relative == 'regex_pattern' and any(isinstance(n, ast.Name) and n.id in ('QFont','FONT_WEIGHT_MAP') for n in ast.walk(node)):
                continue
            if relative == 'userfile.json_setting' and isinstance(node, ast.ImportFrom) and node.module == 'setting_validator':
                continue
            if relative == 'adapter.lmu_reader' and isinstance(node, ast.ImportFrom) and node.module == 'lmu_connector':
                from pyLMUSharedMemory import lmu_enum
                module.LMU_COMPOUND_TYPE = lmu_enum.enum_map(lmu_enum.LMUCompoundType)
                continue
            body.append(node)
        tree.body = body
        if relative == 'userfile.json_setting':
            # This default validates GUI presets, which are not imported remotely.
            # Driver statistics supply their own upstream validator explicitly.
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    node.args.defaults = [ast.Name(id='_reject_gui_preset',ctx=ast.Load()) if isinstance(v,ast.Attribute) and isinstance(v.value,ast.Name) and v.value.id=='PresetValidator' else v for v in node.args.defaults]
            def reject_gui_preset(*args):
                raise ValueError('GUI preset import is not supported by the server')
            module._reject_gui_preset = reject_gui_preset
        if relative.startswith('module.module_'):
            tree = FrameLoop().visit(tree)
        ast.fix_missing_locations(tree)
        module.__file__ = str(path)
        exec(compile(tree, str(path), 'exec'), module.__dict__)
        if relative == 'validator':
            # Upstream timers use monotonic time; replay uses captured game time.
            module.monotonic = lambda: self.now


class Configuration:
    def __init__(self, runtime, state_dir):
        self.directory = Path(state_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        defaults = {}
        for module, key in [('setting_module','MODULE_DEFAULT'),('setting_widget','WIDGET_DEFAULT'),('setting_common','COMMON_DEFAULT')]:
            defaults.update(copy.deepcopy(getattr(runtime.load('template.'+module), key)))
        self.user = NS(setting=defaults)
        for name, module, key in [('tracks','setting_tracks','TRACKS_DEFAULT'),('brakes','setting_brakes','BRAKES_DEFAULT'),('compounds','setting_compounds','COMPOUNDS_DEFAULT'),('heatmap','setting_heatmap','HEATMAP_DEFAULT'),('classes','setting_classes','CLASSES_DEFAULT')]:
            data = copy.deepcopy(getattr(runtime.load('template.'+module), key))
            file = self.directory / (name+'.json')
            if file.exists():
                data.update(json.loads(file.read_text()))
            setattr(self.user, name, data)
        self.user.brands = {}
        self.default = NS(heatmap=self.user.heatmap)
        self.application = {'minimum_update_interval':10}
        self.telemetry = {'enable_auto_backup_car_setup':False}
        self.version_update = 1
        paths = ('delta_best','fuel_delta','energy_delta','sector_best','track_map','pace_notes','track_notes','car_setups','config')
        self.path = NS(**{name:str(self.directory/name)+'/' for name in paths})
        for name in paths:
            Path(getattr(self.path,name)).mkdir(exist_ok=True)

    def save(self, config_type=None):
        # TinyPedal ConfigType is a string key. Bound writes to our state folder.
        key = str(config_type).lower()
        if hasattr(self.user,key):
            target = self.directory / (key+'.json')
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(getattr(self.user,key)))
            temporary.replace(target)


class Runtime:
    ORDER = ('delta','mapping','force','wheels','sectors','vehicles','relative','fuel','hybrid','stint','notes','stats')

    def __init__(self, state_dir=None):
        self.name = '_spotter_' + uuid.uuid4().hex
        self.finder = SourceLoader(self.name)
        sys.meta_path.insert(0,self.finder)
        root = types.ModuleType(self.name)
        root.__path__ = [str(ROOT/'tinypedal')]
        self.state = root.realtime_state = NS(active=False,paused=True,resets=0,hidden=False,overriding=False,spectating=False,singleton=False)
        sys.modules[self.name] = root
        self.api = NS(read=None,name='Le Mans Ultimate')
        self.seed('api_control', api=self.api)
        self.seed('setting', Setting=Configuration, cfg=None)
        self.cfg = Configuration(self,state_dir or os.environ.get('SPOTTER_STATE_DIR','/tmp/spotter-state'))
        sys.modules[self.name+'.setting'].cfg = self.cfg
        self.info = self.load('module_info').minfo
        self.modules = {}
        self.errors = {}
        self.last = {}
        self.energy_seen = False
        self.roster = None
        for name in self.ORDER:
            module = self.load('module.module_'+name)
            generator = module.Realtime(self.cfg,'module_'+name).update_data()
            next(generator)
            self.modules[name] = generator

    def seed(self, relative, **bindings):
        module = types.ModuleType(self.name+'.'+relative)
        module.__dict__.update(bindings)
        sys.modules[module.__name__] = module
        return module

    def load(self, relative):
        return __import__(self.name+'.'+relative,fromlist=['*'])

    def advance(self, reader, time, live=True):
        self.api.read = reader
        self.finder.now = time
        self.state.active = live
        self.state.paused = not live
        roster = tuple(v.mID for v in reader.shmm.scoring)
        if roster != self.roster:
            # LMU can change scoring slots even while game time is frozen.
            # Update index-dependent modules before serializing the new roster.
            self.last.pop('vehicles', None)
            self.last.pop('relative', None)
            self.roster = roster
        for name,generator in self.modules.items():
            interval = self.cfg.user.setting['module_'+name]['update_interval']/1000
            if time < self.last.get(name,-1) + interval - 1e-6:
                continue
            self.last[name] = time
            if name in self.errors:
                continue
            try:
                generator.send(False)
                if name=='fuel':
                    self.energy_seen |= reader.engine.virtual_energy()>0
                    if self.energy_seen and reader.engine.virtual_energy()==0:
                        # Upstream's availability flag treats zero as absent.
                        # After observing energy, zero is an empty tank. Run the
                        # unchanged generator for that sample and retain presence.
                        generator.gi_frame.f_locals['gen_energy_usage'].send(self.state.resets)
                        self.info.energy.available = True
            except Exception as error:
                self.errors[name] = f'{type(error).__name__}: {error}'
                logging.exception('Server module %s failed',name)
        return self.info

    def close(self):
        if self.api.read and self.state.active:
            mapping = self.info.mapping
            if mapping.pitEntryPosition>0 and mapping.pitExitPosition>0:
                self.load('userfile.track_info').save_track_info(track_name=self.api.read.session.track_name(),pit_entry=mapping.pitEntryPosition,pit_exit=mapping.pitExitPosition,pit_speed=mapping.pitSpeedLimit)
        # Flush upstream delayed writes at session exit. Upstream generators
        # save on reset and defer reinitialization until driving resumes.
        self.state.active = False
        self.state.resets += 1
        for name,generator in self.modules.items():
            if self.api.read is None or name in self.errors or not generator.gi_frame:
                continue
            for key,child in list(generator.gi_frame.f_locals.items()):
                if key.startswith('gen_') and isinstance(child,types.GeneratorType):
                    if 'last_reset' in (child.gi_frame.f_locals if child.gi_frame else {}):
                        try:
                            child.send(self.state.resets)
                        except (StopIteration,GeneratorExit):
                            pass
        for generator in self.modules.values():
            generator.close()
        sys.meta_path.remove(self.finder)
        for key in list(sys.modules):
            if key == self.name or key.startswith(self.name+'.'):
                del sys.modules[key]
