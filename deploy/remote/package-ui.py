"""Package the embedded viewer UI and relay for an existing VPS installation."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = '0.4.12'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('desktop_packaging', ROOT / 'deploy/desktop/package-desktop.py')
    packaging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packaging)
    binary = ROOT / 'relay/spotter-relay'
    if not binary.is_file():
        raise RuntimeError('Build the Linux relay before packaging')
    destination = Path(args.output).resolve()
    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary) / f'spotter-ui-v{VERSION}'
        server = bundle / 'server'
        # Include the complete corresponding GPL source; omit private presets.
        shutil.copytree(ROOT, server / 'source', ignore=packaging.ignored)
        shutil.copy2(binary, server / 'spotter-relay')
        shutil.copy2(ROOT / 'deploy/remote/update-ui.sh', server / 'update.sh')
        shutil.copy2(ROOT / f'docs/remote/RELEASE_UI_{VERSION}_RU.md', bundle / 'README_RU.md')
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(bundle.parent))
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Archive CRC check failed')
        names = archive.namelist()
        assert sum('/source/tinypedal/widget/' in n and n.endswith('.py') and not Path(n).name.startswith('_') for n in names) == 76
        assert not any('/presets/' in n or '/local-config.json' in n or '/pair-private.json' in n for n in names)
    print(f'Packaged {destination.name}: {destination.stat().st_size} bytes, {len(names)} files; server UI only, no private presets.')


if __name__ == '__main__':
    main()
