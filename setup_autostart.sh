#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-enable}" in
  enable) python3 tools/desktop_entry.py autostart; echo 'Gesture Control will launch at desktop login.' ;;
  disable) python3 tools/desktop_entry.py disable-autostart; echo 'Desktop autostart disabled. Profiles were preserved.' ;;
  *) echo 'Usage: bash setup_autostart.sh [enable|disable]' >&2; exit 2 ;;
esac
