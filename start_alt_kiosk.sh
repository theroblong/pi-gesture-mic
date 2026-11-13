#!/usr/bin/env bash
set -euo pipefail

URL="${1:-https://example.com}"
if [[ "$URL" == 'https://example.com' ]]; then
  echo 'Supply the web application URL as argument, e.g. ./start_kiosk.sh https://your-app.example' >&2
  exit 1
fi

if ! command -v cage >/dev/null; then
  echo 'Install cage: sudo apt install cage' >&2
  exit 1
fi

if command -v chromium >/dev/null; then
  BROWSER=chromium
elif command -v chromium-browser >/dev/null; then
  BROWSER=chromium-browser
else
  echo 'Install chromium: sudo apt install chromium' >&2
  exit 1
fi

exec cage -- "$BROWSER" \
  --ozone-platform=wayland \
  --user-data-dir=/tmp/kiosk-profile \
  --kiosk \
  --no-first-run \
  --disable-session-crashed-bubble \
  "$URL"
