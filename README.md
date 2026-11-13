# Gesture Control Pi · v2.1

A Raspberry Pi 5 controller for a TV or desktop, with live USB camera setup, guided personal calibration, two-hand gestures, and USB microphone selection and testing.

**Target:** Raspberry Pi OS **64-bit Desktop, Bookworm or Trixie**, USB UVC camera, HDMI display, optional USB Audio Class microphone. Supports **Wayland (labwc/Wayfire)** through Linux virtual input, and **X11** through PyAutoGUI. The installer keeps your desktop session unchanged. Setup/preview windows use XWayland on a Wayland desktop; gesture input reaches native Wayland applications through `uinput`. Speech recognition is not implemented.

## Unzip once. Run one script.

Download **[dist/pi-gesture-mic-pi5-v2.1.zip](dist/pi-gesture-mic-pi5-v2.1.zip)** onto the Pi and extract it. Open a terminal inside the extracted `pi-gesture-mic` folder:

```bash
bash install_pi.sh
```

Run this as your normal desktop user, not with `sudo`. The installer requests sudo for system prerequisites. Internet is needed for dependencies and the tracking model. No executable-bit repair or manual configuration-file editing is needed.

The installer installs dependencies in `.venv`, verifies the model checksum and a real inference, creates application-menu shortcuts, opens Setup, and launches control after calibration. On Wayland it installs the virtual-input access rule and tests device creation. No X11 switch or reboot is requested. If the desktop needs a fresh login to activate access/XWayland, log out and back in, then rerun the installer if prompted. It never enables automatic login.

## First setup

1. **Choose a profile** or type a new name. Profiles survive upgrades and are separate for each desktop account.
2. **Choose the camera** and check the live mirrored preview. Place it near the display with even lighting, keeping both hands and wrists in view.
3. **Choose a microphone** or keep the system default. **Test microphone** records four seconds, plays it back, reports the signal level, and deletes the recording.
4. **Calibrate:** select the controlling hand with a thumb–pinky pinch, record four comfortable reach corners and center, then three open/index-pinch pairs. Hold still and press Space at each capture.
5. **Practice:** click five targets with short index pinches, then pinch-hold and drag a circle. All practice is contained in the setup window. Enter saves only after these checks pass; Escape cancels without replacing the profile.

The camera maps **wrist movement on a 2D plane** to screen coordinates. It does not infer a 3D pointing ray or turn the TV into a physical touchscreen. Recalibrate after moving the camera or changing your seating/reach.

## Everyday use

Open **Gesture Control** from the application menu, or run:

```bash
bash run_pi.sh
bash run_pi.sh --setup                 # profiles, devices and calibration
bash run_pi.sh --profile "Living room" # use a saved profile
bash run_pi.sh --list-profiles
```

| Gesture | Action |
|---|---|
| Thumb + pinky while control is off | Select that hand as owner |
| Owner thumb + pinky | Turn control off |
| Owner short index pinch | Left click on release |
| Owner index pinch held | Drag; release to drop |
| Owner middle pinch | Right click |
| Owner ring pinch | Double click |
| Other hand index pinch + movement | Scroll vertically/horizontally |
| Both hands index-pinched | Browser/document zoom and pan through scrolling |

Detection order changes do not change the owner. Opposite/unknown labels and ambiguous assignments are withheld instead of guessing. Owner loss releases a held drag immediately and pauses control. A returning hand must reopen its pinch before another action. Simultaneous ownership requests select neither hand. Disable with the current owner before switching hands.

**Stop:** Q/Escape or close the preview window; Ctrl+C in the launching terminal also stops. **Stop Gesture Control** in the applications menu or `bash stop_pi.sh` also stops it. On X11 only, moving the physical pointer into a screen corner triggers PyAutoGUI's emergency stop; Wayland cannot use that global-cursor failsafe. Cleanup releases the held left button and Ctrl modifier. Keep a physical mouse/keyboard available.

With the preview focused: Space toggles, X resets, S saves this profile, R reloads, T toggles local telemetry, M switches screen/relative mode. Existing numeric tuning shortcuts remain; see [configuration](docs/CONFIGURATION.md).

## Kiosk and desktop login

```bash
bash start_kiosk.sh https://your-app.example
bash setup_autostart.sh enable
bash setup_autostart.sh disable
```

Chromium and its microphone permissions remain separate from gesture control. On a Desktop image without Chromium, install it with `sudo apt install chromium`. Set `show_preview` to `false` in the saved profile for kiosk operation; stop from its terminal or by terminating that process. Gesture autostart is opt-in (`--autostart` during installation also enables it).

## Validation and release

```bash
python3 -m unittest discover -s tests -v
shellcheck ./*.sh
python3 tools/build_release.py
```

The release is an **online bootstrap package**, not an offline OS image: Python wheels and the model are downloaded during install. The ZIP includes application source, scripts, docs, tests and a per-file SHA-256 manifest. `dist/SHA256SUMS` covers the ZIP. The original v1/v2 archives are historical material; **use v2.1 for Wayland and new installs**. Existing v2 profiles remain compatible.

Validated on the development Mac with automated tests, script checks, rendered wizard screens, a real MediaPipe blank-frame inference, and ARM64 wheel download checks. **Physical Pi 5 acceptance testing is still required** for camera performance, microphone capture/playback, Wayland device discovery, login permissions and pointer injection. See [validation and device checklist](docs/VALIDATION.md).

- [Wayland setup and limitations](docs/WAYLAND.md)
- [Installation and recovery](docs/INSTALL.md)
- [Profiles, settings and controls](docs/CONFIGURATION.md)
- [Microphone setup](docs/MICROPHONE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Third-party dependencies and privacy](docs/THIRD_PARTY.md)
