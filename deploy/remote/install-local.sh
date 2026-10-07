#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root on the VPS.' >&2
  exit 1
fi
cd /opt/tinypedal-remote
test -x .venv/bin/python
test -f relay/spotter-relay
test -f deploy/remote/spotter.service
if ! id spotter >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin spotter
fi
install -d -m 700 /etc/spotter
if [[ ! -e /etc/spotter/credentials.env ]]; then
  .venv/bin/python - <<'PY'
import os
import secrets
path = '/etc/spotter/credentials.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('SPOTTER_PILOT_TOKEN=' + secrets.token_hex(32) + '\n')
    f.write('SPOTTER_VIEW_TOKEN=' + secrets.token_hex(32) + '\n')
PY
fi
chown root:root /etc/spotter/credentials.env
chmod 600 /etc/spotter/credentials.env
chown -R root:spotter /opt/tinypedal-remote
chmod -R g+rX /opt/tinypedal-remote
chmod 755 relay/spotter-relay
install -m 644 deploy/remote/spotter.service /etc/systemd/system/spotter.service
systemctl daemon-reload
systemctl enable --now spotter.service
curl --fail --silent --show-error --retry 10 --retry-delay 1 --retry-connrefused http://127.0.0.1:8080/healthz
echo
echo 'Server installed. Listening on 127.0.0.1:8080. Use an SSH tunnel.'
