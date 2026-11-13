#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  echo 'Usage: bash start_alt_kiosk.sh https://your-app.example [--profile "Living room"]'
  echo 'Starts Cage, the saved gesture profile and Chromium. Voice uses your webpage microphone feature.'
  echo 'First calibrate with bash run_pi.sh --setup. Stop any existing gesture controller before starting Cage.'
  exit 0
fi
URL="${1:-}"
if [[ -z "$URL" || "$URL" == 'https://example.com' ]]; then
  echo 'Supply the web application URL, e.g. bash start_alt_kiosk.sh https://your-app.example' >&2
  exit 1
fi
shift
if [[ ! -x .venv/bin/python ]]; then
  echo 'First install and calibrate: bash install_pi.sh' >&2
  exit 1
fi
if ! command -v cage >/dev/null; then
  echo 'Install cage: sudo apt install cage' >&2
  exit 1
fi
if command -v chromium >/dev/null; then BROWSER="$(command -v chromium)"
elif command -v chromium-browser >/dev/null; then BROWSER="$(command -v chromium-browser)"
else echo 'Install Chromium: sudo apt install chromium' >&2; exit 1; fi
# A supervisor, not just Chromium, inherits Cage's Wayland socket and audio session.
exec cage -- "$ROOT/.venv/bin/python" "$ROOT/kiosk_session.py" "$URL" --browser "$BROWSER" "$@"
