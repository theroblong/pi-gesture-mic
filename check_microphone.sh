#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
  --test) exec .venv/bin/python -c 'from devices import microphone_test; print(microphone_test(None))' ;;
  '') ;;
  *) echo 'Usage: bash check_microphone.sh [--test]' >&2; exit 2 ;;
esac
printf '\nUSB devices:\n'
lsusb || true
printf '\nALSA capture cards:\n'
arecord -l || true
printf '\nDesktop capture sources:\n'
pactl list short sources || true
printf '\nPipeWire status:\n'
if command -v wpctl >/dev/null; then wpctl status || true; fi
printf '\nOpen Gesture Control Setup to select a persistent input and test it.\n'
printf 'Explicit recording test: bash check_microphone.sh --test (four seconds; deleted after playback).\n'
