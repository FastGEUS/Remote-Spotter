"""Per-user profiles. Tokens use Windows DPAPI; SSH keys remain external."""
import base64
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys

from remote.profile import clean_token


def data_dir():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
    return base / 'RemoteSpotter'


@dataclass
class Profile:
    role: str
    token: str
    ssh_key: str
    host: str = '127.0.0.1'
    user: str = 'root'
    ssh_port: int = 22
    server_port: int = 8080
    partner_name: str = ''
    game: str = 'auto'

    def validate(self, check_key=True):
        if self.role not in ('pilot', 'viewer'):
            raise ValueError('Неизвестная роль приложения')
        if self.game not in ('auto','lmu','iracing'):raise ValueError('Неизвестная игра')
        self.token = clean_token(self.token)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', self.host):
            raise ValueError('Введите IP или имя VPS без протокола и порта')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}', self.user):
            raise ValueError('Неверное имя пользователя SSH')
        if not all(type(port) is int and 1 <= port <= 65535 for port in (self.ssh_port, self.server_port)):
            raise ValueError('Порт должен быть числом от 1 до 65535')
        self.ssh_key = str(Path(self.ssh_key).expanduser().resolve())
        if check_key and not Path(self.ssh_key).is_file():
            raise ValueError('Не найден приватный SSH-ключ. Выберите файл без расширения .pub')
        if self.ssh_key.endswith('.pub'):
            raise ValueError('Нужен приватный SSH-ключ, а не публичный .pub')
        # Accept legacy profiles, but never retain a person's display name.
        self.partner_name = ''
        return self


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def dpapi(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Сохранение ключей приложения предназначено для Windows')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    source_buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError('Windows не смогла открыть или сохранить ключ приложения')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def save_profile(profile, directory=None, protect=dpapi):
    profile.validate()
    directory = Path(directory or data_dir())
    directory.mkdir(parents=True, exist_ok=True)
    value = asdict(profile)
    value['tokenProtected'] = base64.b64encode(protect(value.pop('token').encode())).decode()
    value['schemaVersion'] = 1
    path = directory / (profile.role + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return path


def load_profile(role, directory=None, unprotect=None, *, check_key=True):
    path = Path(directory or data_dir()) / (role + '.json')
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.pop('schemaVersion', None) != 1 or value.get('role') != role:
        raise ValueError('Профиль приложения повреждён или имеет другую версию')
    encoded = base64.b64decode(value.pop('tokenProtected'), validate=True)
    value['token'] = (unprotect(encoded) if unprotect else dpapi(encoded, True)).decode()
    return Profile(**value).validate(check_key)


def preset_path(role):
    if role not in ('pilot','viewer'):raise ValueError('Неизвестная роль приложения')
    if getattr(sys,'frozen',False):
        return Path(sys._MEIPASS)/'pair-preset'/(role+'.json')
    return Path(__file__).with_name('presets')/(role+'.json')


def application_dir():
    # PyInstaller's _MEIPASS points inside _internal. The key belongs beside
    # the user's EXE and must keep working when the entire folder is moved.
    if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def load_startup_profile(role, directory=None):
    """A personal build supplies its own role token; SSH stays on the PC.

    The public build still uses the existing one-time setup. Private presets
    live outside generic sources and each frozen EXE carries only its role.
    """
    path=preset_path(role)
    if not path.is_file():return load_profile(role,directory),False
    if path.stat().st_size>8192:raise ValueError('Повреждены встроенные настройки доступа')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value,dict) or value.pop('schemaVersion',None)!=1 or value.get('role')!=role:
        raise ValueError('Неверная роль встроенного доступа')
    profile=Profile(**value).validate(False)
    saved=None
    try:saved=load_profile(role,directory,check_key=False)
    except (ValueError,OSError,RuntimeError,KeyError,TypeError):pass
    same_server=saved and (saved.host,saved.user,saved.ssh_port,saved.server_port)==(profile.host,profile.user,profile.ssh_port,profile.server_port)
    candidates=[application_dir()/'lmu_spotter',application_dir()/'keys/lmu_spotter']
    if same_server:candidates.append(Path(saved.ssh_key))
    candidates.append(Path.home()/'.ssh/lmu_spotter')
    # Prefer the key shipped beside this EXE, then an existing saved path.
    # A missing key leads to one file picker, never the token setup form.
    profile.ssh_key=str(next((key.resolve() for key in candidates if key.is_file()),candidates[0]))
    return profile,True


def imported_pilot_token(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return clean_token(value.get('pilotToken'))
