"""Make startup failures visible even in pythonw / a windowed EXE."""
import os
from pathlib import Path


def main(role):
    try:
        from .gui import launch
        return launch(role)
    except Exception as exc:
        # Never include a profile, token, argv or exception text in a dialog.
        # Some third-party exceptions contain authentication request bodies.
        from .config import data_dir
        path=Path(data_dir())/(role+'-startup.log')
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            import traceback
            frames=''.join(traceback.format_list(traceback.extract_tb(exc.__traceback__)))
            path.write_text(f'Startup failed: {type(exc).__name__}\n'+frames,encoding='utf-8')
        except OSError:
            pass
        text=('Не удалось открыть приложение Remote Spotter.\n'
              'Запустите SETUP_WINDOWS.cmd, а для EXE — BUILD_WINDOWS.cmd.\n'
              f'Журнал запуска: {path}')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,text,'Remote Spotter — ошибка запуска',0x10)
        else:
            import sys
            print(text,file=sys.stderr)
        return 1
