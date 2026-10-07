"""Use a private local pilot profile, or prompt without echoing credentials."""
import asyncio
import getpass
import logging
import os
from types import SimpleNamespace
from .collector import run, configure_logging
from .profile import load_profile, clean_token, validate_url, DEFAULT_URL


def main():
    print("Remote Spotter — LMU collector (development build)")
    try:
        profile=load_profile()
        if profile:
            print("Используется сохранённый профиль пилота. Ввод ключа не требуется.")
            url,token,local=profile["url"],profile["token"],profile["allow_insecure_local"]
        else:
            url,local=validate_url(input("Pilot endpoint [ws://127.0.0.1:8080/ws/pilot via SSH tunnel]: ").strip() or DEFAULT_URL)
            token=clean_token(os.environ.get("SPOTTER_PILOT_TOKEN") or getpass.getpass("Pilot token (hidden): "))
        os.environ["SPOTTER_PILOT_TOKEN"]=token
        configure_logging()
        asyncio.run(run(SimpleNamespace(url=url,demo=False,allow_insecure_local=local,hz=20)))
    except KeyboardInterrupt:pass
    except (RuntimeError,ValueError,OSError) as exc:print("Ошибка запуска:",str(exc))


if __name__=="__main__":main()
