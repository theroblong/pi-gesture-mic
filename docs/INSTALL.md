# Installation and recovery

## Supported deployment

Use Raspberry Pi 5 with Raspberry Pi OS 64-bit Desktop, Bookworm (system Python 3.11) or Trixie (3.13), HDMI display, USB UVC camera and optionally a USB Audio Class microphone. This release supports Python 3.11–3.13. Lite/headless images, CSI/libcamera-only cameras and other distributions are outside the supported path.

Extract `dist/pi-gesture-mic-pi5-v2.3.zip`, enter its `pi-gesture-mic` directory on the Pi desktop, and run `bash install_pi.sh`. Use your regular account. The script elevates only system setup commands.

## What the script handles

- Architecture/OS/Python checks, apt prerequisites for camera, ALSA/desktop audio, Tk, XWayland/Qt libraries, Linux input build headers, Cage and Chromium.
- A local `.venv`, explicit direct dependency pins, pip consistency checks, and a record of all resolved versions in `~/.local/state/pi-gesture-mic/installed-requirements.txt`.
- A versioned MediaPipe hand model download with a fixed SHA-256 check. A corrupt or partial file is replaced only after a valid download completes.
- A real blank-frame model inference before opening setup. This checks library/model compatibility on the target Pi without requiring a camera or desktop connection.
- Application menu entries for **Gesture Control** and **Gesture Control Setup**, correctly quoting paths with spaces.
- Wayland detection, Linux `uinput` module loading and an active-local-session udev access rule. A no-input preflight creates and closes the virtual devices before setup. The desktop session remains unchanged; no reboot is requested. Headless installation uses a temporary desktop autostart to resume setup after login.
- Camera discovery, stable `/dev/v4l/by-id` (or by-path) selection, microphone discovery by persistent source name, live preview and guided calibration.
- Launch after successful calibration. No mouse actions are sent during setup; runtime starts with control off.

See [Wayland support](WAYLAND.md) for permissions, input architecture and troubleshooting. The application runs as your normal user; sudo is used only for installing dependencies, the module configuration and udev rule.

## Options

```bash
bash install_pi.sh --no-launch       # install/check; open setup later
bash install_pi.sh --autostart       # also launch controller at future desktop logins
```

`--resume` is used by the temporary desktop entry. It skips installation and repeats the model smoke check. If dependencies are missing, run the installer normally. If installing through SSH, the script arranges setup at the next graphical login. It cannot log in on your behalf. On Wayland the resumed setup checks virtual-input access before launching. The old `--configure-x11` flag is accepted as a compatibility no-op and cannot switch your desktop.

The installer is safe to rerun after a failed download or apt operation. It reuses the environment, verifies the model, and preserves profiles. It does not silently repair malformed profiles or replace custom source files. Stop a running controller before installing/upgrading; only one controller/setup instance can own the desktop at a time.

## Upgrade and rollback

Extract v2.3 into a **new directory** to preserve any source customizations and avoid stale virtual environments. Run its installer to recreate shortcuts. Profiles remain under the desktop account's configuration directory. Keep the prior directory until the new version works. To roll back application code, recreate shortcuts from the prior directory. A v1 runtime does not understand v2 calibration profiles; its original configuration remains alongside its source.

## Remove login behavior or desktop changes

- `bash setup_autostart.sh disable` removes controller autostart without deleting profiles.
- `python3 tools/desktop_entry.py clear-resume` removes an unfinished setup resume entry.
- To return to Wayland: `sudo raspi-config nonint do_wayland W2`, then reboot when ready. v2.1 gesture control supports that Wayland session; v2.0 does not.
- To remove the virtual-input permission, stop the controller, remove `/etc/udev/rules.d/70-pi-gesture-mic-uinput.rules` and `/etc/modules-load.d/pi-gesture-mic-uinput.conf` with sudo, reload udev rules and reboot when convenient. Do not remove other applications’ uinput rules.
- To uninstall, disable autostart and clear resume first, remove `pi-gesture-mic*.desktop` from `~/.local/share/applications`, then remove the extracted application directory. Keep or separately remove `~/.config/pi-gesture-mic` and `~/.local/state/pi-gesture-mic`. Shared apt packages are intentionally left installed.

XDG_CONFIG_HOME, XDG_DATA_HOME and XDG_STATE_HOME are respected throughout. Logs are in `~/.local/state/pi-gesture-mic/install.log`; model downloads and dependencies require working internet and sufficient disk space (allow roughly 1 GB for environment/downloads).

For Cage, finish desktop calibration, stop the desktop controller, then use `bash start_alt_kiosk.sh URL`. See [kiosk setup](KIOSK.md).
