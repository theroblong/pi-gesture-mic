#!/usr/bin/env bash
set -euo pipefail
# Matches this application's script name, restricted to the current user's processes.
if pkill -TERM -u "$(id -u)" -f '(^|[ /])gesture_mouse_pi[.]py([[:space:]]|$)'; then
  echo 'Requested Gesture Control shutdown and input release.'
else
  result=$?
  if [[ $result -eq 1 ]]; then echo 'Gesture Control is not running.'
  else exit "$result"; fi
fi
