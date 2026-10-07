"""Protect the selected SSH private key before connecting on Windows.

Uses the same FileSecurity operation as the confirmed manual repair, hidden
in an owned subprocess. Paths are data in the environment, never PS source.
"""
import asyncio
import base64
import contextlib
import logging
import os
from pathlib import Path
import re
import subprocess

from .lifecycle import own, release

IS_WINDOWS = os.name == 'nt'
KEY_PATH_ENV = 'REMOTE_SPOTTER_KEY_ACL_PATH'
REPAIR_TIMEOUT = 15


class KeyPermissionError(RuntimeError):
    pass


REPAIR_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $keyPath = $env:REMOTE_SPOTTER_KEY_ACL_PATH
    $file = Get-Item -LiteralPath $keyPath -Force -ErrorAction Stop
    if ($file.PSIsContainer -or (($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw 'Expected a regular private key file'
    }
    $keyUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    function Test-KeyAcl($acl) {
        $rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
        return ($acl.AreAccessRulesProtected -and
            $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -eq $keyUser.Value -and
            $rules.Count -eq 1 -and
            $rules[0].IdentityReference.Value -eq $keyUser.Value -and
            $rules[0].AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
            -not $rules[0].IsInherited -and
            ($rules[0].FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Read) -eq
                [System.Security.AccessControl.FileSystemRights]::Read)
    }
    $current = Get-Acl -LiteralPath $keyPath -ErrorAction Stop
    if (Test-KeyAcl $current) {
        [Console]::Out.Write('KEY_ACL_OK')
        exit 0
    }
    $keyAcl = [System.Security.AccessControl.FileSecurity]::new()
    $keyAcl.SetOwner($keyUser)
    $keyAcl.SetAccessRuleProtection($true, $false)
    $keyRule = [System.Security.AccessControl.FileSystemAccessRule]::new($keyUser, 'FullControl', 'Allow')
    $keyAcl.AddAccessRule($keyRule)
    Set-Acl -LiteralPath $keyPath -AclObject $keyAcl -ErrorAction Stop
    if (-not (Test-KeyAcl (Get-Acl -LiteralPath $keyPath -ErrorAction Stop))) {
        throw 'Key ACL verification failed'
    }
    [Console]::Out.Write('KEY_ACL_FIXED')
    exit 0
} catch {
    [Console]::Error.Write('KEY_ACL_FAILED HRESULT=' + $_.Exception.HResult)
    exit 1
}
'''


def powershell_program():
    root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    for folder in ('Sysnative', 'System32'):
        program = root/folder/'WindowsPowerShell/v1.0/powershell.exe'
        if program.is_file():return str(program)
    raise KeyPermissionError('Не найден Windows PowerShell для автоматической подготовки SSH-ключа.')


def repair_command(program):
    encoded = base64.b64encode(REPAIR_SCRIPT.encode('utf-16-le')).decode('ascii')
    return [program, '-NoLogo', '-NoProfile', '-NonInteractive',
            '-WindowStyle', 'Hidden', '-EncodedCommand', encoded]


async def prepare_private_key(path):
    """Repair only this file, once per connection session; no elevation/prompt."""
    if not IS_WINDOWS:return False
    key = Path(path).expanduser()
    try:
        # Never adjust an arbitrary file accidentally selected as an SSH key.
        if key.is_symlink() or getattr(key, 'is_junction', lambda:False)() or not key.is_file():
            raise KeyPermissionError('Выберите обычный файл приватного SSH-ключа рядом с приложением.')
        key = key.resolve()
        with key.open('rb') as file:header = file.readline(128).strip()
        if header not in (b'-----BEGIN OPENSSH PRIVATE KEY-----', b'-----BEGIN RSA PRIVATE KEY-----',
                          b'-----BEGIN EC PRIVATE KEY-----', b'-----BEGIN DSA PRIVATE KEY-----',
                          b'-----BEGIN PRIVATE KEY-----', b'-----BEGIN ENCRYPTED PRIVATE KEY-----'):
            raise KeyPermissionError('Выбранный файл не является приватным SSH-ключом OpenSSH. Выберите lmu_spotter, а не .pub.')
    except OSError as exc:
        raise KeyPermissionError('Windows не позволяет прочитать SSH-ключ. Поместите ключ рядом с EXE в доступной вам папке.') from exc
    environment = dict(os.environ)
    environment[KEY_PATH_ENV] = str(key)
    try:
        process = await asyncio.create_subprocess_exec(*repair_command(powershell_program()),
            env=environment, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
    except OSError as exc:
        raise KeyPermissionError('Windows заблокировала автоматическую подготовку SSH-ключа. Проверьте ограничения запуска приложения.') from exc
    own(process)
    try:
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), REPAIR_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise KeyPermissionError('Windows не завершила подготовку SSH-ключа. Повторите подключение.') from exc
    finally:
        try:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError):process.kill()
                await asyncio.wait_for(process.wait(), 2)
        finally:release(process)
    result = stdout.strip()
    if process.returncode != 0 or result not in (b'KEY_ACL_OK', b'KEY_ACL_FIXED'):
        # The PS script emits a numeric error, never key contents or PS source.
        detail = stderr.decode(errors='replace').strip()
        logging.warning('SSH key ACL preparation failed (exit=%s, marker=%s)',
                        process.returncode, detail if re.fullmatch(r'KEY_ACL_FAILED HRESULT=-?\d+', detail) else 'blocked or invalid result')
        raise KeyPermissionError('Windows не позволила настроить права SSH-ключа. Перенесите папку приложения в свою папку «Загрузки» и повторите подключение.')
    logging.info('SSH private key permissions %s', 'repaired' if result == b'KEY_ACL_FIXED' else 'already protected')
    return result == b'KEY_ACL_FIXED'
