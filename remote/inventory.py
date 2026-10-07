"""Generate a static parity register from the pinned upstream, without Qt."""
import ast
import csv
import json
import subprocess
from pathlib import Path
from .upstream import ROOT


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def chain(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = chain(node.value)
        return parent + "." + node.attr if parent else ""
    return ""


def main():
    dest = ROOT / "docs" / "remote"
    dest.mkdir(parents=True, exist_ok=True)
    default = ast.parse((ROOT / "tinypedal/template/setting_widget.py").read_text())
    keys = []
    for node in default.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "WIDGET_DEFAULT" for t in node.targets):
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    with (dest / "widget-parity.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["widget", "source", "module_inputs_static", "api_inputs_static", "status", "limitations"])
        for key in sorted(keys):
            path = ROOT / "tinypedal/widget" / (key + ".py")
            tree = ast.parse(path.read_text())
            paths = {chain(n) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            modules = sorted(x for x in paths if x.startswith("minfo.") and x.count(".") >= 2)
            apis = sorted(x for x in paths if x.startswith("api.read."))
            writer.writerow([key, str(path.relative_to(ROOT)), ";".join(modules), ";".join(apis),
                             "web-data-port",
                             "Original API/module data connected; web layout and some widget-specific timers/options differ; live LMU parity not verified"])
    lock = {"repository": "https://github.com/TinyPedal/TinyPedal", "tag": "v2.50.0",
            "commit": git("rev-parse", "v2.50.0^{commit}"),
            "submodules": git("submodule", "status", "--recursive").splitlines(),
            "widgets": len(keys)}
    (ROOT / "remote/upstream-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
    print(f"Registered {len(keys)} web data views; desktop option parity tracked separately.")


if __name__ == "__main__":
    main()
