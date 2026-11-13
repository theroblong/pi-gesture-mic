#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
RESUME=false
NO_LAUNCH=false
CONFIGURE_X11=false
AUTOSTART=false
for arg in "$@"; do
  case "$arg" in
    --resume) RESUME=true ;;
    --no-launch) NO_LAUNCH=true ;;
    --configure-x11) CONFIGURE_X11=true ;;
    --autostart) AUTOSTART=true ;;
    --help|-h)
      echo 'Usage: bash install_pi.sh [--no-launch] [--configure-x11] [--autostart]'
      echo 'Installs prerequisites, validates tracking, opens setup and launches control.'
      echo 'Use a terminal on Raspberry Pi OS 64-bit Desktop. Internet and sudo are required.'
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
fail() { echo "Setup stopped: $*" >&2; exit 1; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == aarch64 ]] || fail 'Use Raspberry Pi OS 64-bit Desktop on the Pi (aarch64).'
[[ $EUID -ne 0 ]] || fail 'Run as your normal desktop user, without sudo. The script asks for sudo when needed.'
[[ -r /etc/os-release ]] || fail 'Cannot identify the operating system.'
# shellcheck disable=SC1091
. /etc/os-release
[[ "${ID:-}" == debian || "${ID:-}" == raspbian ]] || fail 'This installer supports Raspberry Pi OS (Debian based).'
[[ "${VERSION_CODENAME:-}" == bookworm || "${VERSION_CODENAME:-}" == trixie ]] || fail 'Use Raspberry Pi OS Bookworm or Trixie 64-bit Desktop.'
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/pi-gesture-mic"
mkdir -p "$STATE_DIR"
exec > >(tee -a "$STATE_DIR/install.log") 2>&1
trap 'echo "Setup failed at line $LINENO. Fix the error above and rerun: bash install_pi.sh. Log: $STATE_DIR/install.log"' ERR
if ! $RESUME; then
  command -v sudo >/dev/null || fail 'sudo is required.'
  sudo -v
  echo '1/5 Installing camera, audio and desktop prerequisites…'
  sudo apt-get update
  sudo apt-get install -y python3-venv python3-pip python3-tk python3-dev \
    libgl1 libglib2.0-0 libx11-6 libxtst6 libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-icccm4 \
    libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libportaudio2 \
    scrot alsa-utils v4l-utils usbutils pulseaudio-utils curl ca-certificates
  python3 - <<'PY'
import sys
if not (3,11) <= sys.version_info[:2] <= (3,13):
    raise SystemExit('This release supports system Python 3.11 to 3.13. Use Bookworm or Trixie.')
PY
  echo '2/5 Installing isolated application dependencies…'
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install --only-binary=mediapipe,opencv-contrib-python,numpy,pillow -r requirements.txt
  .venv/bin/python -m pip check
  .venv/bin/python -m pip freeze > "$STATE_DIR/installed-requirements.txt"
  echo '3/5 Verifying the hand tracking model…'
  MODEL_SHA='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
  if ! echo "$MODEL_SHA  hand_landmarker.task" | sha256sum --check --status 2>/dev/null; then
    curl --fail --location --retry 3 --connect-timeout 15 --max-time 300 \
      'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' \
      -o hand_landmarker.task.tmp
    echo "$MODEL_SHA  hand_landmarker.task.tmp" | sha256sum --check --status || fail 'Model checksum mismatch; rerun to download again.'
    mv hand_landmarker.task.tmp hand_landmarker.task
  fi
fi
[[ -x .venv/bin/python ]] || fail 'Application environment is missing. Rerun bash install_pi.sh without --resume.'
echo '4/5 Checking model inference and creating desktop shortcuts…'
.venv/bin/python tools/verify_runtime.py
python3 tools/desktop_entry.py launchers
if $AUTOSTART; then python3 tools/desktop_entry.py autostart; fi
if [[ "${XDG_SESSION_TYPE:-}" == wayland || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo 'Desktop control needs X11. Your current desktop uses Wayland.'
  echo 'The change applies after reboot; this does not enable automatic desktop login.'
  if ! $CONFIGURE_X11 && [[ -t 0 ]]; then
    read -r -p 'Configure X11 and resume setup at your next desktop login? [Y/n] ' answer
    [[ "$answer" == n || "$answer" == N ]] || CONFIGURE_X11=true
  fi
  if ! $CONFIGURE_X11; then
    fail 'Run bash install_pi.sh --configure-x11 to configure the supported desktop, or select X11 in raspi-config.'
  fi
  command -v raspi-config >/dev/null || fail 'raspi-config is missing; select an X11 desktop session and rerun.'
  sudo raspi-config nonint do_wayland W1
  python3 tools/desktop_entry.py resume
  echo 'X11 configured. Save your work and reboot. Setup will resume when you log into the desktop.'
  if [[ -t 0 ]]; then
    read -r -p 'Reboot now? [y/N] ' answer
    if [[ "$answer" == y || "$answer" == Y ]]; then sudo reboot; fi
  fi
  exit 0
fi
if [[ -z "${DISPLAY:-}" ]]; then
  python3 tools/desktop_entry.py resume
  echo 'Installation is ready. Log into the Pi desktop to finish setup. A terminal on the desktop is required.'
  exit 0
fi
python3 tools/desktop_entry.py clear-resume
echo '5/5 Ready. Setup will guide camera alignment, microphone testing and personal calibration.'
if ! $NO_LAUNCH; then bash "$ROOT/run_pi.sh" --setup; fi
