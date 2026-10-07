#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root on the VPS.' >&2
  exit 1
fi
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=/opt/tinypedal-remote
test -f "$bundle_dir/spotter-relay"
test -f "$bundle_dir/source/remote/strategy.py"
test -x "$project_dir/.venv/bin/python"
test -f "$project_dir/relay/spotter-relay"
test -f /etc/spotter/credentials.env
id spotter >/dev/null
"$project_dir/.venv/bin/python" -m pip install 'PyYAML==6.0.3'
(
  cd "$bundle_dir/source"
  PYTHONDONTWRITEBYTECODE=1 "$project_dir/.venv/bin/python" -m unittest discover -s remote/tests -q
)
cp -p "$project_dir/relay/spotter-relay" "$project_dir/relay/spotter-relay.previous"
cp -p /etc/systemd/system/spotter.service "$project_dir/spotter.service.previous"
tar -czf "$project_dir/release.previous.tar.gz" -C "$project_dir" remote relay/web
rollback() {
  trap - ERR
  echo 'Update failed. Restoring previous code.' >&2
  install -o root -g spotter -m 755 "$project_dir/relay/spotter-relay.previous" "$project_dir/relay/spotter-relay.next"
  mv -f "$project_dir/relay/spotter-relay.next" "$project_dir/relay/spotter-relay"
  tar -xzf "$project_dir/release.previous.tar.gz" -C "$project_dir"
  cp -p "$project_dir/spotter.service.previous" /etc/systemd/system/spotter.service
  systemctl daemon-reload
  systemctl restart spotter.service
  exit 1
}
trap rollback ERR
systemctl stop spotter.service
install -o root -g spotter -m 755 "$bundle_dir/spotter-relay" "$project_dir/relay/spotter-relay.next"
mv -f "$project_dir/relay/spotter-relay.next" "$project_dir/relay/spotter-relay"
cp -R "$bundle_dir/source/remote/." "$project_dir/remote/"
cp -R "$bundle_dir/source/relay/web/." "$project_dir/relay/web/"
chown -R root:spotter "$project_dir/remote" "$project_dir/relay/web"
chmod -R g+rX "$project_dir/remote" "$project_dir/relay/web"
install -o root -g root -m 644 "$bundle_dir/source/deploy/remote/spotter.service" /etc/systemd/system/spotter.service
systemctl daemon-reload
systemctl start spotter.service
curl --fail --silent --show-error --retry 10 --retry-delay 1 --retry-connrefused http://127.0.0.1:8080/healthz
trap - ERR
echo
echo 'v0.4.7 installed: iRacing SDK server adapter plus LMU support. Use client 0.6.0 for iRacing. Refresh browser Ctrl+F5.'
systemctl status spotter.service --no-pager
