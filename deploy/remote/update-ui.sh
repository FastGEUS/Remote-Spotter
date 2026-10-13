#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root on the VPS.' >&2
  exit 1
fi
bundle_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=/opt/tinypedal-remote
test -f "$bundle_dir/spotter-relay"
test -d "$bundle_dir/source/relay/web"
test -f "$project_dir/relay/spotter-relay"
test -f /etc/spotter/credentials.env
cp -p "$project_dir/relay/spotter-relay" "$project_dir/relay/spotter-relay.previous"
tar -czf "$project_dir/relay/web.previous.tar.gz" -C "$project_dir/relay" web
install -o root -g spotter -m 755 "$bundle_dir/spotter-relay" "$project_dir/relay/spotter-relay.next"
mv -f "$project_dir/relay/spotter-relay.next" "$project_dir/relay/spotter-relay"
cp -R "$bundle_dir/source/relay/web/." "$project_dir/relay/web/"
chown -R root:spotter "$project_dir/relay/web"
chmod -R g+rX "$project_dir/relay/web"
systemctl restart spotter.service
if ! curl --fail --silent --show-error --retry 10 --retry-delay 1 --retry-connrefused http://127.0.0.1:8080/healthz; then
  echo 'Health check failed. Restoring previous version.' >&2
  install -o root -g spotter -m 755 "$project_dir/relay/spotter-relay.previous" "$project_dir/relay/spotter-relay.next"
  mv -f "$project_dir/relay/spotter-relay.next" "$project_dir/relay/spotter-relay"
  tar -xzf "$project_dir/relay/web.previous.tar.gz" -C "$project_dir/relay"
  systemctl restart spotter.service
  exit 1
fi
echo
echo 'UI v0.4.12 installed: panels follow their content height, with no reserved note space. Existing 0.6.9 clients are compatible; restart the viewer or refresh with Ctrl+F5.'
systemctl status spotter.service --no-pager
