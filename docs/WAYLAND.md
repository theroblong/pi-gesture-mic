# Wayland support · v2.1

Use **pi-gesture-mic-pi5-v2.1.zip**. Extract it into a new directory on the Pi, open a terminal there on the desktop and run:

```bash
bash install_pi.sh
```

Keep Wayland selected. The old v2.0 ZIP is X11-only. If you already switched to X11 with the old installer, choose Wayland in `sudo raspi-config` (or use `sudo raspi-config nonint do_wayland W2`) and reboot once at a convenient time. The new installer does not switch the session or request a reboot. Existing personal profiles are reused.

## How it works

The runtime detects Wayland and creates virtual pointer/keyboard devices through the Linux kernel's **uinput** interface. Native Wayland applications receive desktop input through the compositor's normal input stack. It does not send X11 mouse events into XWayland and does not import PyAutoGUI on this path.

- An absolute pointer provides calibrated screen mapping and calibrated drag displacement.
- A separate relative pointer provides legacy relative mode without relying on a global cursor-position query.
- Wheel events provide scroll/pan; a virtual keyboard provides Ctrl+= and Ctrl+- zoom shortcuts.
- Held buttons and keys are released on orderly shutdown; every device descriptor is closed, including after partial creation failures.

Tk/OpenCV setup windows use **XWayland for rendering only**. The installer includes XWayland and the launcher selects OpenCV's xcb plugin. Your desktop and browser can remain native Wayland. A minimal compositor session with XWayland disabled needs it enabled for these windows. This release targets the standard Raspberry Pi OS labwc/Wayfire desktop with one display; custom Cage sessions and multi-seat/multi-monitor mappings require device validation.

Sources: [Linux uinput](https://docs.kernel.org/input/uinput.html), [python-evdev input creation](https://python-evdev.readthedocs.io/en/latest/tutorial.html#specifying-uinput-device-options), and [libinput virtual absolute pointing devices](https://wayland.freedesktop.org/libinput/doc/latest/what-is-libinput.html).

## What the installer changes

- Installs the Linux-only evdev dependency and its build prerequisites.
- Loads `uinput` now and adds `/etc/modules-load.d/pi-gesture-mic-uinput.conf` for future boots.
- Installs `/etc/udev/rules.d/70-pi-gesture-mic-uinput.rules`. Its `uaccess` tag grants the active local desktop session read/write access to `/dev/uinput` through logind. It is intentionally ordered before the standard seat ACL rule.
- Reloads/triggers udev and runs a preflight that creates/closes the virtual devices **without moving, clicking or typing**.

The program runs as your ordinary desktop user. There is no root runtime or privileged daemon, and no physical keyboard event stream is read/grabbed by this application. The permission allows other processes running as the active local user to create virtual input too; it is not an application-specific restriction. Device mode is 0660, not world-writable. SSH/headless sessions do not receive local-seat access automatically.

## Stop and pointer behavior

Use **Stop Gesture Control** from the application menu, `bash stop_pi.sh`, Q/Escape with the preview focused, window close or Ctrl+C. The owner's pinky gesture also disables control. The Stop launcher sends SIGTERM only to matching controller processes owned by the current user.

The physical-mouse-corner emergency stop is **X11-only**. Wayland does not expose global physical cursor position here. Absolute gestures track the saved calibration and cached last gesture target; after moving a physical mouse, the next gesture returns to that calibrated target. Relative mode sends actual relative movement and follows compositor acceleration settings. Use one display and recalibrate after changing your camera, seating or display arrangement.

## Diagnostics

```bash
echo "$XDG_SESSION_TYPE"             # should remain wayland
ls -l /dev/uinput
getfacl /dev/uinput                   # active desktop user should have rw access
.venv/bin/python tools/check_input.py # no-input device creation check
```

If access is denied, rerun the installer locally, then log out/back in if needed. If still denied, inspect `~/.local/state/pi-gesture-mic/install.log` and the udev rule; verify a normal active logind desktop session. Do not work around this by running the application as root or granting world access.

If creation succeeds but the compositor ignores input, install `libinput-tools` and use `sudo libinput list-devices` while the controller is running. Look for **Gesture Control Absolute Pointer**, **Gesture Control Relative Pointer**, and **Gesture Control Keyboard**. Verify that the compositor enables them on the intended seat/output. Native-library hangs or compositor-specific device policies cannot be detected by the creation preflight alone.

The code/event contracts and installer flow are tested on the development Mac with simulated devices. **Real Pi uinput permissions, libinput classification and Wayland delivery still require testing on your Pi.** This is not a claim of completed hardware acceptance.
