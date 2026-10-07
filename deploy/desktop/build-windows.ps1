param([ValidateSet('Both','Pilot','Viewer')][string]$Role='Both',[switch]$SetupOnly)
$ErrorActionPreference='Stop'
$projectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $projectRoot
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Run this script on Windows x64.' }
function Invoke-Checked([string]$Program,[string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$pythonLauncher=Get-Command py -ErrorAction SilentlyContinue
if (-not $pythonLauncher) { throw 'Install Python 3.12 x64 with the Python launcher, then run again.' }
Invoke-Checked 'py' @('-3','-c','import sys,ctypes; assert (3,11)<=sys.version_info[:2]<(3,14) and ctypes.sizeof(ctypes.c_void_p)==8')
$roles=if ($Role -eq 'Both') { @('pilot','viewer') } else { @($Role.ToLowerInvariant()) }
foreach ($appRole in $roles) {
    $environment=Join-Path $projectRoot ('.gui-'+$appRole)
    if (-not (Test-Path (Join-Path $environment 'Scripts\python.exe'))) {
        Invoke-Checked 'py' @('-3','-m','venv',$environment)
    }
    $python=Join-Path $environment 'Scripts\python.exe'
    $requirements=Join-Path $PSScriptRoot ('requirements-'+$appRole+'.txt')
    Invoke-Checked $python @('-m','pip','install','-r',$requirements)
    if ($SetupOnly) { continue }
    Invoke-Checked $python @('-m','pip','install','PyInstaller==6.16.0')
    $name=if ($appRole -eq 'pilot') {'SpotterPilot'} else {'SpotterViewer'}
    $versionInfo=Join-Path $projectRoot ('build\version-info-'+$appRole+'.txt')
    Invoke-Checked $python @('-m','remote.desktop.branding','--role',$appRole,'--output',$versionInfo)
    $entry=Join-Path $projectRoot ('remote\desktop\'+$appRole+'_entry.py')
    $icon=Join-Path $projectRoot 'remote\desktop\assets\remote-spotter.ico'
    $windowIcon=Join-Path $projectRoot 'remote\desktop\assets\remote-spotter.png'
    if (-not (Test-Path -LiteralPath $icon) -or -not (Test-Path -LiteralPath $windowIcon)) {
        throw 'Remote Spotter icon assets are missing. Extract the full client folder.'
    }
    $arguments=@('-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
        '--name',$name,'--paths',$projectRoot,'--icon',$icon,'--version-file',$versionInfo,
        '--distpath',(Join-Path $projectRoot 'dist'),
        '--workpath',(Join-Path $projectRoot ('build\'+$appRole)),
        '--specpath',(Join-Path $projectRoot 'build'),
        '--add-data',((Join-Path $projectRoot 'LICENSE.txt')+';licenses'),
        '--add-data',($windowIcon+';app-assets'),
        '--hidden-import','remote.desktop.session')
    $preset=Join-Path $projectRoot ("remote\desktop\presets\$appRole.json")
    if (Test-Path -LiteralPath $preset) {
        # Bundle one role's credentials only; do not recursively collect presets.
        $arguments+=@('--add-data',($preset+';pair-preset'))
    }
    if ($appRole -eq 'pilot') {
        $arguments+=@('--hidden-import','irsdk','--hidden-import','remote.iracing',
            '--add-data',((Join-Path $PSScriptRoot 'licenses\pyirsdk-LICENSE.txt')+';licenses'))
        # The pilot distribution does not carry a browser or calculation engine.
        $arguments+=@('--exclude-module','remote.desktop.viewer',
            '--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets',
            '--exclude-module','remote.compute','--exclude-module','remote.headless','--exclude-module','tinypedal')
    }
    $arguments+=$entry
    Invoke-Checked $python $arguments
    $clientVersion=Invoke-Checked $python @('-c','from remote.desktop import VERSION; print(VERSION)')
    Set-Content -LiteralPath (Join-Path $projectRoot "dist\$name\CLIENT_VERSION.txt") -Value $clientVersion -Encoding ASCII
    Write-Host "Built: dist\$name\$name.exe"
}
Write-Host 'Ready. Launch START_PILOT.vbs / START_SPOTTER.vbs or the EXE in dist. Keep the entire EXE folder.'
