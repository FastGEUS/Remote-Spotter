"""Reviewable source + VPS update + Windows setup/build, without credentials."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from remote.desktop import VERSION
from remote.desktop.config import Profile
from remote.profile import clean_token

def ignored(directory,names):
    blocked={'.git','.venv','__pycache__','node_modules','dist','build',
             'local-config.json','spotter-relay','spotter-relay.previous','spotter-relay.next',
             'previous-gui.html','presets','pair-private.json'}
    return [n for n in names if n in blocked or n.startswith(('.gui-','pilot.log','viewer.log')) or n.endswith(('.pyc','.zip'))]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--client-only',action='store_true')
    parser.add_argument('--pair-profile',help='Private pair JSON, never copied into shared sources')
    args=parser.parse_args()
    pair=None
    if args.pair_profile:
        pair=json.loads(Path(args.pair_profile).read_text(encoding='utf-8-sig'))
        if not isinstance(pair,dict) or pair.get('schemaVersion')!=1:raise ValueError('Invalid pair preset')
        pilot=clean_token(pair['pilotToken']);viewer=clean_token(pair['viewerToken'])
        if pilot==viewer:raise ValueError('Pilot and viewer must have separate role tokens')
    binary=ROOT/'relay/spotter-relay'
    if not args.client_only and not binary.is_file():raise RuntimeError('Build the Linux relay first')
    with tempfile.TemporaryDirectory() as temporary:
        bundle=Path(temporary)/('remote-spotter-v'+VERSION);client=bundle/'client';server=bundle/'server'
        source=bundle/'source' if args.client_only else server/'source'
        shutil.copytree(ROOT,source,ignore=ignored)
        if not args.client_only:
            shutil.copy2(binary,server/'spotter-relay')
            shutil.copy2(ROOT/'deploy/remote/update-release.sh',server/'update.sh')
        # Full source is in server/source. Client includes capture and GUI only.
        (client/'remote').mkdir(parents=True)
        for name in ('__init__.py','collector.py','native.py','snapshot.py','profile.py','rest_capture.py','recovery.py','iracing.py'):
            shutil.copy2(ROOT/'remote'/name,client/'remote'/name)
        shutil.copytree(ROOT/'remote/desktop',client/'remote/desktop',ignore=ignored)
        if pair:
            presets=client/'remote/desktop/presets';presets.mkdir()
            for role,token in [('pilot',pilot),('viewer',viewer)]:
                value={'schemaVersion':1,'role':role,'token':token,'host':pair.get('host','127.0.0.1'),
                    'user':pair.get('user','root'),'ssh_port':pair.get('sshPort',22),'server_port':pair.get('serverPort',8080),
                    'ssh_key':'~/.ssh/lmu_spotter','game':pair.get('game','auto'),
                    'partner_name':''}
                Profile(**{k:v for k,v in value.items() if k!='schemaVersion'}).validate(False)
                (presets/(role+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        shutil.copytree(ROOT/'pyLMUSharedMemory',client/'pyLMUSharedMemory',ignore=ignored)
        shutil.copytree(ROOT/'deploy/desktop',client/'deploy/desktop',ignore=ignored)
        shutil.copy2(ROOT/'LICENSE.txt',client/'LICENSE.txt')
        for role,label in [('pilot','PILOT'),('viewer','SPOTTER')]:
            launcher=f'CreateObject("WScript.Shell").Run "wscript.exe " & Chr(34) & CreateObject("Scripting.FileSystemObject").BuildPath(CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName), "deploy\\desktop\\start.vbs") & Chr(34) & " {role}", 1, False\r\n'
            (client/f'START_{label}.vbs').write_text(launcher,encoding='ascii')
        for name,extra in [('SETUP_WINDOWS',' -SetupOnly'),('BUILD_WINDOWS','')]:
            command=f'@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\\desktop\\build-windows.ps1"{extra}\r\nif errorlevel 1 (pause & exit /b 1)\r\npause\r\n'
            (client/f'{name}.cmd').write_bytes(command.encode('ascii'))
        recovery='@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\\desktop\\close-old-clients.ps1"\r\nif errorlevel 1 (pause & exit /b 1)\r\npause\r\n'
        (client/'CLOSE_OLD_CLIENTS.cmd').write_bytes(recovery.encode('ascii'))
        shutil.copy2(ROOT/('docs/remote/RELEASE_DESKTOP_'+VERSION+'_RU.md'),bundle/'README_RU.md')
        with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():archive.write(path,path.relative_to(bundle.parent))
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        names=archive.namelist()
        assert not any('local-config.json' in n or n.endswith(('.log','.key','.pem')) for n in names)
        assert not any('/client/tinypedal/' in n or '/client/remote/compute.py' in n for n in names)
        assert not any('/source/' in n and '/presets/' in n for n in names)
        if pair:
            assert sum('/presets/' in n for n in names)==2
            for name in names:
                if '/presets/' not in name:
                    contents=archive.read(name)
                    assert pilot.encode() not in contents and viewer.encode() not in contents
        assert sum('/source/tinypedal/widget/' in n and n.endswith('.py') and not Path(n).name.startswith('_') for n in names)==76
        privacy='personal role presets included; SSH private keys excluded' if pair else 'no private profiles or keys'
        print(f'Packaged {Path(args.output).name}: {Path(args.output).stat().st_size} bytes, {len(names)} files, {privacy}.')

if __name__=='__main__':main()
