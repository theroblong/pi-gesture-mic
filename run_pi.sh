#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'First run: bash install_pi.sh' >&2
  exit 1
fi
# Do not inherit plugin paths injected by another Qt application.
unset QT_QPA_PLATFORM_PLUGIN_PATH
exec .venv/bin/python gesture_mouse_pi.py "$@"
