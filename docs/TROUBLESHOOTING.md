# Troubleshooting

**`No module named mediapipe`** — Run `./install_pi.sh` on Pi OS 64-bit (`uname -m` should be `aarch64`). Check that your OS Python version has compatible published wheels.

**`hand_landmarker.task` not found** — Run `./install_pi.sh`; it downloads the model into the project directory. Avoid running without model or from an unexpected directory.

**Camera opens but no frames** — Run `v4l2-ctl --list-devices`; inspect `/dev/video*`, close applications using webcam, and adjust `camera_index`. If needed lower capture dimensions. The Mac camera index is unrelated.

**PyAutoGUI display error** — Confirm local X11 session with `echo $XDG_SESSION_TYPE`; the X11 adapter will not work on Wayland-only sessions or without a desktop display.

**Pointer mapping feels too fast or hits edges** — Increase camera active region for precision; decrease it to cover screen with less hand travel. Adjust landmark and smoothing.

**Pinky pinch does not change hands** — Disable with current owner's pinky pinch first, release, then pinch with other hand. Hands crossing or being occluded can confuse identity matching.

**Mic not detected** — Try a different USB port, `lsusb`, `arecord -l` and `wpctl status`. USB audio hardware and video are distinct devices; `wpctl` source ID is not the ALSA card index.

**Audio works in terminal, not browser** — Grant mic permission to the web app and confirm browser's selected input; HTTPS usually required for remote websites.

**No keyboard shortcuts** — Set `show_preview: true` and focus the OpenCV window, or edit JSON and restart. For an unattended kiosk, keep `show_preview: false`.
