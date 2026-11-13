#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'First run: bash install_pi.sh' >&2
  exit 1
fi
# Do not inherit plugin paths injected by another Qt application.
unset QT_QPA_PLATFORM_PLUGIN_PATH
# OpenCV's wheel ships the xcb UI plugin; native desktop input still uses uinput.
# This affects only our windows, not Chromium or the desktop session.
if [[ "${XDG_SESSION_TYPE:-}" == wayland || -n "${WAYLAND_DISPLAY:-}" ]]; then
  export QT_QPA_PLATFORM=xcb
fi
exec .venv/bin/python gesture_mouse_pi.py "$@"
