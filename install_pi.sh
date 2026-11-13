#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ $(uname -m) != aarch64 ]]; then echo '64-bit ARM Raspberry Pi OS (aarch64) required' >&2; exit 1; fi
sudo apt update
sudo apt install -y python3-venv python3-pip python3-dev libgl1 libglib2.0-0 libx11-6 libxtst6 scrot alsa-utils v4l-utils curl
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
if [[ ! -s hand_landmarker.task ]]; then
  curl -fL --retry 3 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -o hand_landmarker.task.tmp
  mv hand_landmarker.task.tmp hand_landmarker.task
fi
.venv/bin/python - <<'PY'
import mediapipe as mp, cv2, pyautogui
print('MediaPipe:', getattr(mp,'__version__','installed'))
print('OpenCV:', cv2.__version__)
print('Dependencies import OK')
PY
printf '\nInstall done. Check X11: echo $XDG_SESSION_TYPE; check camera: v4l2-ctl --list-devices\n'
