#!/usr/bin/env bash
set -euo pipefail
printf '\nUSB devices:\n'; lsusb
printf '\nALSA capture cards:\n'; arecord -l || true
printf '\nPipeWire sources (if available):\n'; if command -v wpctl >/dev/null; then wpctl status; fi
printf '\nTo test: arecord -D plughw:CARD,DEVICE -f S16_LE -r 16000 -c 1 -d 5 mic-test.wav\n'
