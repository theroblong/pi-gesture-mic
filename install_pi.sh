#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
RESUME=false
NO_LAUNCH=false
AUTOSTART=false
for arg in "$@"; do
  case "$arg" in
    --resume) RESUME=true ;;
    --no-launch) NO_LAUNCH=true ;;
    --configure-x11) echo 'X11 switching is no longer needed; this version keeps your desktop session unchanged.' ;;
    --autostart) AUTOSTART=true ;;
    --help|-h)
      echo 'Usage: bash install_pi.sh [--no-launch] [--autostart]'
      echo 'Installs prerequisites, validates tracking, opens setup and launches control.'
      echo 'Supports Wayland and X11. Use the Pi desktop; internet and sudo are required.'
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
  sudo apt-get install -y python3-venv python3-pip python3-tk python3-dev build-essential linux-libc-dev \
    libgl1 libglib2.0-0 libx11-6 libxtst6 libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-icccm4 \
    libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libportaudio2 \
    scrot alsa-utils v4l-utils usbutils pulseaudio-utils curl ca-certificates xwayland acl procps
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
# Configure kernel input without changing the compositor or requesting a reboot.
# Install on X11/headless too so a later Wayland login is already provisioned.
if ! $RESUME; then
  echo 'Configuring Wayland virtual input for the active local desktop user…'
  sudo install -m 0644 system/70-pi-gesture-mic-uinput.rules /etc/udev/rules.d/70-pi-gesture-mic-uinput.rules
  sudo install -m 0644 system/pi-gesture-mic-uinput.conf /etc/modules-load.d/pi-gesture-mic-uinput.conf
  sudo modprobe uinput
  sudo udevadm control --reload-rules
  sudo udevadm trigger --action=change --subsystem-match=misc --sysname-match=uinput
  sudo udevadm settle --timeout=10
fi
if [[ -z "${DISPLAY:-}" ]]; then
  python3 tools/desktop_entry.py resume
  if [[ "${XDG_SESSION_TYPE:-}" == wayland || -n "${WAYLAND_DISPLAY:-}" ]]; then
    echo 'XWayland is installed for setup windows. Log out and back into your Wayland desktop; setup will resume.'
  else
    echo 'Installation is ready. Log into the Pi desktop to finish setup. A terminal on the desktop is required.'
  fi
  exit 0
fi
if [[ "${XDG_SESSION_TYPE:-}" == wayland || -n "${WAYLAND_DISPLAY:-}" ]]; then
  echo 'Keeping Wayland. Checking virtual input access…'
  if ! .venv/bin/python tools/check_input.py; then
    fail 'Wayland device access is not ready. Log out and back into the local desktop, then rerun bash install_pi.sh. See docs/WAYLAND.md.'
  fi
fi
python3 tools/desktop_entry.py clear-resume
echo '5/5 Ready. Setup will guide camera alignment, microphone testing and personal calibration.'
if ! $NO_LAUNCH; then bash "$ROOT/run_pi.sh" --setup; fi
