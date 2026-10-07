# Сервер Remote Spotter

Публичная схема использует SSH-туннели, Linux VPS и внутренний 127.0.0.1:8080.
После сборки Linux amd64 бинарника relay/spotter-relay создаются Python venv
и служба из spotter.service. install-local.sh предназначен для первичной
установки в /opt/tinypedal-remote. Требования: remote/requirements.txt.

update-release.sh обновляет существующую установку из папки релиза:
spotter-relay плюс source с соответствующими исходниками. Такие пакеты
создаёт deploy/desktop/package-desktop.py после сборки серверного бинарника.
Не передавайте персональные профили в публичную поставку.
