"""Local pilot credentials. Never publish this profile to the web client."""
import json
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_URL="ws://127.0.0.1:8080/ws/pilot"
DEFAULT_PATH=Path(__file__).with_name("local-config.json")


def clean_token(value):
    if not isinstance(value,str):
        raise ValueError("Ключ пилота должен быть строкой")
    value=value.strip().strip("\ufeff\u200b").strip()
    if len(value)>=2 and value[0]==value[-1] and value[0] in "\"'":
        value=value[1:-1].strip()
    if not 32<=len(value)<=512 or not value.isascii() or any(c.isspace() or ord(c)<33 or ord(c)==127 for c in value):
        raise ValueError("Ключ пилота: нужны 32–512 символов без пробелов и переносов")
    return value


def validate_url(value):
    if not isinstance(value,str):
        raise ValueError("Адрес сервера должен быть строкой")
    url=value.strip()
    parts=urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment or parts.path!="/ws/pilot":
        raise ValueError("Адрес подключения должен заканчиваться на /ws/pilot")
    local=parts.scheme=="ws" and parts.hostname=="127.0.0.1" and parts.port is not None
    if not local and not (parts.scheme=="wss" and parts.hostname):
        raise ValueError("Используйте WSS или ws://127.0.0.1:порт/ws/pilot через SSH-туннель")
    return url,local


def load_profile(path=DEFAULT_PATH):
    path=Path(path)
    if not path.exists():
        return None
    value=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value,dict):
        raise ValueError("Неверный формат remote/local-config.json")
    url,local=validate_url(value.get("url",DEFAULT_URL))
    return {"url":url,"token":clean_token(value.get("pilotToken")),"allow_insecure_local":local}
