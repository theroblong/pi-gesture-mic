# pi-gesture-mic

Raspberry Pi 5 **gesture-controlled TV / kiosk prototype**, based on the v6 dual-hand gesture engine. Includes USB microphone setup and diagnostics. The mic integration currently configures/tests capture hardware; **speech recognition is not implemented**.

> **Platform:** Raspberry Pi OS **64-bit Desktop in X11 mode**. The mouse adapter uses PyAutoGUI/X11; native Wayland input is not implemented. Tested by syntax checks and engine unit tests outside the Pi; physical Pi validation remains necessary.

## Quick start on Pi 5

```bash
git clone <YOUR-REPO-URL> pi-gesture-mic
cd pi-gesture-mic
chmod +x *.sh
./install_pi.sh
./run_pi.sh
```

If your repository is already copied to the Pi, skip `git clone`. Before install, switch desktop session to X11 using `sudo raspi-config` → Advanced Options → Wayland → X11; reboot and verify `echo "$XDG_SESSION_TYPE"` prints `x11`.

Connect USB webcam and HDMI TV. `v4l2-ctl --list-devices` lists cameras. Set the correct `camera_index` in `gesture_config.json` (Mac indices do **not** carry over to Pi). During development, keep `show_preview: true` and a keyboard connected.

**USB microphone:** run `./check_microphone.sh`, `arecord -l`, and read [USB microphone setup](docs/MICROPHONE.md).

**Kiosk:** `./start_kiosk.sh https://your-app.example` from the graphical desktop. To start gesture tracking at login after testing, use `./setup_autostart.sh`.

## Gesture controls

| Gesture | Behavior |
|---|---|
| Pinky pinch, control off | That hand becomes the mouse owner |
| Owner pinky pinch | Disables mouse control |
| Owner wrist movement | Position cursor over the calibrated screen region |
| Owner short index pinch | Left-click |
| Owner held index pinch | Drag; release to drop |
| Owner middle pinch | Right-click |
| Owner ring pinch | Double-click |
| Other hand index pinch + movement | Scroll |
| Both hands index pinch | Zoom/pan gestures |

Pointer mapping is an adjustable **virtual camera rectangle**, not physical TV edge detection. When the owning hand briefly leaves the camera frame, input is paused and the system attempts to reacquire it; the camera cannot track a hand outside its field of view.

## Repository layout

```text
pi-gesture-mic/
├── gesture_mouse_pi.py       # Raspberry Pi/X11 runtime
├── gesture_engine.py         # Gesture state machine, dual-hand tracking
├── gesture_config.json       # Pointer and gesture configuration
├── requirements.txt          # Python dependencies
├── install_pi.sh             # Install dependencies and tracking model
├── run_pi.sh                 # Run desktop gesture controller
├── check_microphone.sh       # Discover USB recording devices
├── start_kiosk.sh            # Launch Chromium in TV kiosk mode
├── setup_autostart.sh        # Enable desktop-login startup
├── tests/test_engine.py      # Gesture engine unit tests
├── docs/                      # Setup, configuration, audio, architecture
└── dist/                      # Standalone deployable Pi bundle
```

The MediaPipe `hand_landmarker.task` model is downloaded by the installer, **not included in source control or the release ZIP**.

## Documentation

- [Install and deployment](docs/INSTALL.md)
- [Gestures and tuning](docs/CONFIGURATION.md)
- [USB microphone](docs/MICROPHONE.md)
- [Architecture and portability](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Upstream Pi port reference](docs/ORIGINAL_PI_PORT.md)

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile gesture_engine.py gesture_mouse_pi.py
```

Unit tests cover the gesture engine; they do not prove camera, Pi performance, HDMI positioning, USB mic selection, or X11 injection on your actual hardware.

## Safety / privacy

This controller can inject mouse and keyboard events into the active desktop. Keep a physical keyboard or trackpad handy for safety. Do not expose camera, microphone, or telemetry to public services. `gesture_events.jsonl` contains usage/tuning events and is ignored by git.

## Release archives

`dist/pi-gesture-mic-pi5-v1.zip` is the standalone Pi install package. The outer **repository ZIP** is for extracting into your existing Mac Git worktree. Do not commit `dist/` unless you deliberately want to version binary release archives.
