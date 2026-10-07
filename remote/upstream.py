"""Load upstream pure functions without executing TinyPedal's Qt bootstrap.

Files stay unmodified and run in an isolated namespace. This loads real source,
not a replacement or a pretend PySide module. Fuel calculation generators run
with isolated remote adapters; full Delta/Vehicle modules are still pending.
"""
import importlib.util
import ast
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def calculations():
    name = "_tinypedal_remote_core"
    if name + ".calculation" in sys.modules:
        return sys.modules[name + ".calculation"]
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "tinypedal")]
    sys.modules[name] = package
    for module in ("const_common", "calculation"):
        fullname = name + "." + module
        spec = importlib.util.spec_from_file_location(
            fullname, ROOT / "tinypedal" / (module + ".py"))
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = loaded
        try:
            spec.loader.exec_module(loaded)
        except Exception:
            sys.modules.pop(fullname, None)
            raise
    return sys.modules[name + ".calculation"]


def pure_module(module):
    calculations()
    fullname = "_tinypedal_remote_core." + module
    if fullname not in sys.modules:
        spec = importlib.util.spec_from_file_location(fullname, ROOT / "tinypedal" / (module + ".py"))
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = loaded
        try:
            spec.loader.exec_module(loaded)
        except Exception:
            sys.modules.pop(fullname,None)
            raise
    return sys.modules[fullname]


def source_functions(relative_path, bindings, names=None):
    """Execute original function ASTs unchanged; runtime globals are remote adapters.

    Excludes Qt/thread bootstrap class and import statements only. Each engine gets
    an isolated namespace, so injected API and state cannot leak between rooms.
    """
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and (names is None or n.name in names)]
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *functions], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(bindings)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def fuel_functions(bindings):
    return source_functions("tinypedal/module/module_fuel.py", bindings)
