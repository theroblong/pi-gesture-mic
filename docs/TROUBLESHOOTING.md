# Troubleshooting

| Symptom | Recovery |
|---|---|
| Installer rejects machine | Use Raspberry Pi OS 64-bit Desktop Bookworm/Trixie on the Pi; the Mac is only a development host. |
| No desktop / running from SSH | Finish at the Pi's local graphical login; installer adds a temporary resume entry. |
| Old installer asks for X11 | Install v2.1 from its new ZIP. It keeps Wayland and provisions virtual input. |
| Wayland input access not ready | Rerun v2.1 installer from the local desktop. Log out/in if prompted; inspect `/dev/uinput` ACLs and see WAYLAND.md. Do not use chmod 666 or run the application as root. |
| Wayland setup reports no DISPLAY | XWayland is needed for Tk/OpenCV windows. Installer adds it; log out and back into Wayland to activate it. |
| Virtual input exists but pointer does not move | Check `sudo libinput list-devices` and compositor device settings. A single local display/seat is the supported target; see WAYLAND.md. |
| apt/pip/network failure | Fix connectivity or apt lock/error, then rerun the same installer. Do not run the entire installer as root. |
| Missing/incompatible model | Rerun installer; it checks SHA-256 and actual model inference. |
| Qt platform plugin cannot load | Rerun installer for GUI libraries; use the included launcher, which clears inherited Qt plugin paths. |
| Camera absent | Reconnect a USB UVC webcam, close other camera apps, use Refresh devices. CSI/libcamera-only cameras are not supported by this capture backend. |
| Camera timeout or disconnect | Runtime stops/releases input after the read failure or three-second stale-frame timeout. Reconnect and reopen Setup. No silent camera substitution occurs. |
| Permission denied opening video/audio | Use a local desktop login. Check `/dev/video*` permissions and device ACLs; if needed add your user with `sudo usermod -aG video,audio "$USER"`, then log out and back in. Installer does not make device nodes world-writable. |
| Gesture Control already running | Close its preview or stop its process before opening another instance. A stale lock file alone does not block startup. |
| Control remains off | Show an open hand, then pinch thumb to pinky. Two simultaneous requests select neither hand. |
| Crossed hands pause | Separate hands, show the owner's full wrist/palm, reopen fingers. Uncertain identity is withheld. |
| Reappearance does nothing | Open all pinches first. After a long loss, same-known-handedness reacquisition is required; Space/X can reset before a fresh selection. |
| Calibration won't capture | Hold the requested pose and wrist position for the two-second countdown. Start with one open hand at center; move up-left for the first corner and toward each new target afterward. Movement, loss or the wrong pose resets capture. Space remains optional. |
| Bad corners / center off | Hold thumb–middle pinch for two seconds (or R) to restart; use a comfortable clockwise rectangle with enough reach. Avoid steep camera angles. |
| Calibration keeps asking for Space | Use the v2.2 ZIP; older releases require keyboard capture. |
| Pinches rejected | Open wider during open samples, make actual thumb/index contact for closed samples, improve lighting and avoid finger occlusion. |
| Targets hard to hit | Keep the wrist still while pinching, return to the calibrated seating position, or redo calibration. |
| Drag too fast/slow | Adjust `drag_hold_ms` in the profile or use runtime keys 1/2, S to save; run practice again. |
| Microphone missing | Refresh devices; run `bash check_microphone.sh`; check the desktop sound session. Gestures do not require a mic. |
| Recording test silent/clipped | Check microphone input gain and selected device. Playback uses the desktop output device. |
| Browser cannot hear mic | Grant site microphone permission and choose the correct input; use HTTPS or localhost. |
| Profile invalid | Error names the setting. Back up the profile JSON before repair. Existing files are not silently discarded. |
| Preview hidden / hotkeys unavailable | Stop from its launching terminal (Ctrl+C), or send SIGTERM to the controller process. |

Emergency stop: use **Stop Gesture Control** or `bash stop_pi.sh`, press Q/Escape with preview focused, close the preview, or Ctrl+C. The physical-mouse-corner failsafe works only on X11. Keep physical input available while validating new hardware. A forced kill or power loss bypasses application cleanup.

Performance depends on camera format, USB bandwidth, lighting and cooling. Try 640×480 processing dimensions on a copied profile if tracking is slow; recalibrate afterward. Camera read buffering is limited where the driver supports it. A hung inference call is not isolated in a separate process, so external process termination may be needed for a native-library hang.
