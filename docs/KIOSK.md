# Cage kiosk: gestures and webpage voice

Use v2.3 or later. Your original Cage script starts only Chromium; this package's `start_alt_kiosk.sh` starts both Chromium and the gesture controller in the same Wayland session.

## Install or upgrade once

Extract the new ZIP into a new directory on the Pi. From its `pi-gesture-mic` directory, as your normal local user:

```bash
bash install_pi.sh
```

Choose the camera and microphone, complete calibration and save. Existing calibrated profiles remain available when using the same account. If setup was skipped, open `bash run_pi.sh --setup` on the desktop. Setup still needs the standard desktop/XWayland; runtime inside Cage does not.

## Launch the kiosk

Stop the desktop gesture instance first. If enabled, remove its desktop autostart to prevent another process owning the camera/controller:

```bash
bash stop_pi.sh
bash setup_autostart.sh disable
```

From the local session where you normally launch Cage, inside the new extracted application directory:

```bash
bash start_alt_kiosk.sh "https://your-app.example"
# Or choose a saved gesture profile:
bash start_alt_kiosk.sh "https://your-app.example" --profile "Living room"
```

Run as the same normal user who calibrated. Cage still needs working seat/display access; the controller needs the camera and `/dev/uinput`; audio needs that user's PipeWire/PulseAudio session. This launcher does not configure boot services, automatic login or replace your sound server. Starting Cage nested inside another compositor can have different input/seat behavior; validate using your intended local kiosk session.

The launcher loads your saved profile and microphone, creates virtual input and waits for a successful camera inference before opening Chromium. It hides the preview for this run only. No separate background launch command is necessary.

## Enable gestures and voice

1. Show an open hand, then pinch **thumb + pinky** to select that hand and enable control. Avoid simultaneous requests from both hands.
2. Move your wrist to point. A short thumb–index pinch clicks on release; hold to drag.
3. Click your webpage's voice/microphone button. On its first request, click **Allow** in Chromium. Use HTTPS or localhost.
4. Speak using the webpage's own voice feature. There is no additional Pi speech recognizer or wake word. If the webpage selects a specific input, select your USB mic there too.

Browser settings and permissions are stored in `~/.config/pi-gesture-mic/chromium-kiosk`, separate from your ordinary Chromium profile. The old `/tmp/kiosk-profile` is not migrated, so grant microphone consent in the new profile. Browser policies/site changes can require consent again. No flag grants unrestricted microphone access to all sites.

The gesture profile's microphone becomes the desktop default and is unmuted before the browser starts. If the saved input cannot be selected, a warning is printed; gestures still work, and Chromium may use another current default. Check the input before relying on voice. The webpage determines audio recording/processing and any network requirements.

## Stop and diagnose

Pinch thumb + pinky with the controlling hand to pause gestures while keeping the webpage open. Closing Chromium or stopping the launcher stops the controller; `bash stop_pi.sh` also ends the kiosk. A controller failure closes Chromium. Preview keyboard shortcuts are unavailable in this mode. Keep physical input available during device validation.

Startup/runtime details are in `~/.local/state/pi-gesture-mic/kiosk-gesture.log`; the previous run is retained as `kiosk-gesture.log.1`. Standard XDG configuration/state locations are respected.

| Problem | Check |
|---|---|
| Browser never opens | Read the gesture log. A calibrated profile, live camera/model inference and virtual input are required before launch. |
| Already running | Stop the desktop controller; do not run desktop autostart and Cage gestures simultaneously. |
| No calibrated profile | Use `bash run_pi.sh --setup` on the desktop as the same user, then stop that controller. |
| `/dev/uinput` denied | Use an active local logind session; follow [Wayland permissions](WAYLAND.md). Do not run Chromium/controller as root. |
| Ready, but gestures do nothing | Open hand then thumb+pinky. Check compositor discovery of the virtual pointer/keyboard and the intended seat/output. Readiness proves device creation/inference, not compositor delivery. |
| Webpage cannot hear voice | Check site microphone permission, its chosen device and HTTPS. Run `pactl info` and `bash check_microphone.sh` from the same session used to launch Cage. |
| New profile asks for permission | Grant once for this browser profile and site. The previous temporary Chromium profile was separate. |
| Kiosk exits after camera loss | Restore the selected camera and restart. No other camera is silently substituted. |

Calibrated absolute mapping uses normalized coordinates and a 1920×1080 reference canvas; it is independent of the single output's physical pixel dimensions. Relative-mode sensitivity uses that reference size. Multiple outputs, physical Pi device delivery, audio capture and sustained camera performance still need on-device validation. Native inference hangs can require terminating the launcher externally.

Cage's child application receives its Wayland environment; this package makes the supervisor that child so both programs inherit it. See the [official Cage manual](https://github.com/cage-kiosk/cage/blob/master/cage.1.scd).
