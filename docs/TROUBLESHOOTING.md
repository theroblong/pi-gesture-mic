# Troubleshooting

| Symptom | Recovery |
|---|---|
| Installer rejects machine | Use Raspberry Pi OS 64-bit Desktop Bookworm/Trixie on the Pi; the Mac is only a development host. |
| No desktop / running from SSH | Finish at the Pi's local graphical login; installer adds a temporary resume entry. |
| Wayland detected | Accept X11 setup in the installer, save work and reboot. No input is injected through XWayland. |
| Still Wayland after reboot | Confirm an X11 session in `raspi-config`; inspect `~/.local/state/pi-gesture-mic/install.log`. Custom login/session managers may need manual selection. |
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
| Calibration won't capture | Hold a single controlling wrist steady for at least 0.7 seconds. Press Space after the hand is fully visible. |
| Bad corners / center off | R restarts; use a comfortable clockwise rectangle with enough reach. Avoid steep camera angles. |
| Pinches rejected | Open wider during open samples, make actual thumb/index contact for closed samples, improve lighting and avoid finger occlusion. |
| Targets hard to hit | Keep the wrist still while pinching, return to the calibrated seating position, or redo calibration. |
| Drag too fast/slow | Adjust `drag_hold_ms` in the profile or use runtime keys 1/2, S to save; run practice again. |
| Microphone missing | Refresh devices; run `bash check_microphone.sh`; check the desktop sound session. Gestures do not require a mic. |
| Recording test silent/clipped | Check microphone input gain and selected device. Playback uses the desktop output device. |
| Browser cannot hear mic | Grant site microphone permission and choose the correct input; use HTTPS or localhost. |
| Profile invalid | Error names the setting. Back up the profile JSON before repair. Existing files are not silently discarded. |
| Preview hidden / hotkeys unavailable | Stop from its launching terminal (Ctrl+C), or send SIGTERM to the controller process. |

Emergency stop: move the physical mouse pointer to a corner, press Q/Escape with preview focused, close the preview, or Ctrl+C. Keep physical input available while validating new hardware. A forced kill or power loss bypasses application cleanup.

Performance depends on camera format, USB bandwidth, lighting and cooling. Try 640×480 processing dimensions on a copied profile if tracking is slow; recalibrate afterward. Camera read buffering is limited where the driver supports it. A hung inference call is not isolated in a separate process, so external process termination may be needed for a native-library hang.
