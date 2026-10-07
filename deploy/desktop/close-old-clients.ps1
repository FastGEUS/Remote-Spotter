# Optional recovery for an already hung 0.5.0 client. No name-wide python/SSH kill.
$ErrorActionPreference='Stop'
$profileDirectory=Join-Path $env:LOCALAPPDATA 'RemoteSpotter'
$lockedPids=@()
foreach ($role in @('pilot','viewer')) {
    $lockPath=Join-Path $profileDirectory ($role+'.lock')
    if (Test-Path -LiteralPath $lockPath) {
        $number=0
        if ([int]::TryParse((Get-Content -LiteralPath $lockPath -TotalCount 1),[ref]$number)) {
            $lockedPids+=$number
        }
    }
}
$count=0
foreach ($process in (Get-CimInstance Win32_Process)) {
    $sourceClient=($process.Name -in @('python.exe','pythonw.exe')) -and
        ($process.CommandLine -match '(?:^|\s)-m\s+remote\.desktop\.(?:pilot|viewer)_entry(?:\s|$)')
    $compiledClient=($process.Name -in @('SpotterPilot.exe','SpotterViewer.exe')) -and
        ($lockedPids -contains [int]$process.ProcessId)
    if ($sourceClient -or $compiledClient) {
        & taskkill.exe /PID $process.ProcessId /T /F
        if ($LASTEXITCODE -ne 0) { throw "Unable to stop Remote Spotter PID $($process.ProcessId)." }
        $count++
    }
}
Write-Host "Stopped Remote Spotter instances: $count. Profiles and SSH keys were preserved."
