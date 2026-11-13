> Historical v1 documentation. For current Wayland support use README.md and docs/WAYLAND.md.

# Gesture Control Pi 5 — v6 Pi port

Two-hand ownership / pinky pinch, index click and drag, middle right-click, ring double-click, secondary-hand scroll, and two-hand zoom/pan. Preserves camera-to-TV mapping and normalized wrist positioning from v6. Runs on **Raspberry Pi OS 64-bit Desktop with an X11 desktop session**. This is an X11 proof-of-concept bridge; the recommended default Pi OS Wayland session is not supported by this version's PyAutoGUI output adapter.

## Hardware
- Pi 5, HDMI TV, Raspberry Pi OS 64-bit Desktop, USB UVC camera, optional USB mic.
- USB camera must be connected to Pi; macOS camera index `1` does not carry over to Pi.

## 1. Choose X11 for first prototype

Raspberry Pi OS uses Wayland/labwc by default. In a Pi terminal run `sudo raspi-config` → Advanced Options → Wayland → **W1 X11**, finish and reboot. The Pi's developers recommend Wayland in general; switch only for this initial PyAutoGUI-based prototype. Confirm with `echo $XDG_SESSION_TYPE` (should report `x11`). The session must be a local graphical desktop, not a bare SSH shell.

## 2. Install

Copy this entire folder to the Pi, e.g. `~/gesture-control-pi/` via `scp` or USB drive.

```bash
cd ~/gesture-control-pi
chmod +x *.sh
./install_pi.sh
v4l2-ctl --list-devices
ls /dev/video*
```

On Raspberry Pi OS, camera index often begins at `0`, but check if multiple `/dev/video*` entries exist. Change `camera_index` in `gesture_config.json` to the right integer for your UVC camera. Prefer a stable `/dev/v4l/by-id/...-video-index0` in deployments with multiple cameras (the current config accepts an integer only; symlink support would be a follow-up).

Run:

```bash
./run_pi.sh
```

Pinky pinch to enable using that hand. Owner pinky pinch to disable; either hand can next re-enable. The tracking window overlays the browser during testing. If it is distracting, edit `"show_preview": false` in `gesture_config.json`, then relaunch (exit via Ctrl+C). When disabling preview, tuning keyboard shortcuts don't work because there is no OpenCV window receiving focus. Config file edits and restart still work.

## 3. TV web app kiosk

Install Chromium if missing: `sudo apt install chromium`.

```bash
./start_kiosk.sh https://YOUR-APP-URL
```

Use a real URL. Launch gesture controller separately (`./run_pi.sh`), or autostart controller after desktop login using `./setup_autostart.sh`. This installs a desktop autostart launcher, not a background service. Configure desktop auto-login if you want unattended startup. A kiosk itself is separate from the controller. HTTPS is recommended, especially if your web app requests microphone permissions.

## 4. USB microphone — discovery and test

Plug in a class-compliant USB microphone, then:

```bash
sudo apt install -y alsa-utils
./check_microphone.sh
arecord -l
```

Example: if the mic shows `card 2`, `device 0`:

```bash
arecord -D plughw:2,0 -f S16_LE -r 16000 -c 1 -d 5 ~/mic-test.wav
aplay ~/mic-test.wav
```

If the USB microphone supports only a different sample rate or number of channels, adjust the test format. The `plughw` interface handles common sample conversions. For Pi desktop PipeWire, run:

```bash
wpctl status
wpctl set-default SOURCE_ID
wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.8
wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0
```

Replace `SOURCE_ID` with the actual USB source ID printed by `wpctl status` (not the ALSA card number). To test PipeWire as selected default:

```bash
pw-record ~/pipewire-mic-test.wav
# Speak for several seconds and press Ctrl+C, then:
pw-play ~/pipewire-mic-test.wav
```

Or choose the input device in the desktop sound UI. Chromium may separately request microphone permission; allow it for your trusted HTTPS app and select the microphone in the app's audio settings when offered. This package only sets up and tests input hardware; it does not add speech recognition or wake words to your UI.

## 5. Useful config keys

- `camera_active_region`: `[left,top,right,bottom]`, maps inner portion of camera to whole TV. Smaller rectangle = faster pointer movement.
- `pointer_landmark`: `0` wrist (default), `9` palm, `8` fingertip.
- `pointer_mode`: `screen` absolute camera-to-TV mapping (default), or `relative`.
- `cursor_smoothing`, `screen_transition_rate`, `screen_motion_deadband`: smoothing and alignment.
- `pinch_confirmation_ms`, `pinch_release_ms`, `drag_hold_ms`: timing.
- `show_preview`: true / false.

This is a working **port package**, with syntax and gesture state tests performed outside the Pi. USB capture, performance, microphone, local desktop input and HDMI output must be validated on your actual Pi. Expect Pi 5 inference frame rate to be lower than your Mac; reduce `capture_width` and `capture_height` if needed.

## Verify installation

```bash
uname -m                        # aarch64
printf 'Session: %s\n' "$XDG_SESSION_TYPE" # x11
v4l2-ctl --list-devices
arecord -l
.venv/bin/python -c 'import mediapipe,cv2,pyautogui; print("imports OK")'
.venv/bin/python -m unittest discover -s tests -v
```

## Security

The program sends mouse/keyboard events to the active desktop and may interact with other apps. Keep a keyboard nearby while calibrating. Ctrl+C stops it; PyAutoGUI fail-safe is on. Do not expose webcam/mic audio or telemetry to the internet. Telemetry events may contain gesture usage and tuning information but no camera frames.
