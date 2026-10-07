"""Desktop icon paths and distinct Windows taskbar identities."""
import ctypes
import os
from pathlib import Path
import sys

AUTHOR = 'Svet'
CREDIT = 'by '+AUTHOR


def version_info(role):
    """PyInstaller PE resource; descriptive metadata, not Authenticode signing."""
    from . import VERSION
    if role not in ('pilot','viewer'):raise ValueError('Unknown desktop role')
    version=tuple(int(part) for part in VERSION.split('.'))+(0,)
    if len(version)!=4 or not all(0<=part<=65535 for part in version):
        raise ValueError('Invalid Windows application version')
    name='SpotterPilot' if role=='pilot' else 'SpotterViewer'
    fields={
        'CompanyName':AUTHOR,
        'FileDescription':'Remote Spotter '+('Pilot' if role=='pilot' else 'Viewer')+' — '+CREDIT,
        'FileVersion':VERSION,
        'InternalName':name,
        'LegalCopyright':'Remote Spotter additions © 2026 '+AUTHOR,
        'OriginalFilename':name+'.exe',
        'ProductName':'Remote Spotter',
        'ProductVersion':VERSION,
    }
    strings=',\n'.join('        StringStruct('+repr(key)+', '+repr(value)+')' for key,value in fields.items())
    return f'''# UTF-8. Display metadata only; a trusted certificate must sign the final EXE.
VSVersionInfo(
  ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
{strings}
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
'''


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Generate EXE version resources')
    parser.add_argument('--role',choices=('pilot','viewer'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(version_info(args.role),encoding='utf-8')


def icon_path():
    if getattr(sys,'frozen',False):
        return Path(sys._MEIPASS)/'app-assets/remote-spotter.png'
    return Path(__file__).with_name('assets')/'remote-spotter.png'


def windows_identity(role):
    if os.name!='nt':return
    if role not in ('pilot','viewer'):raise ValueError('Unknown desktop role')
    # Two roles can run together without being grouped as generic pythonw.
    shell=ctypes.WinDLL('shell32')
    function=shell.SetCurrentProcessExplicitAppUserModelID
    function.argtypes=[ctypes.c_wchar_p];function.restype=ctypes.c_long
    function('RemoteSpotter.'+('Pilot' if role=='pilot' else 'Viewer'))


if __name__=='__main__':main()
