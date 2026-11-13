# Install on Raspberry Pi 5

Requires a Pi 5, 64-bit Raspberry Pi OS Desktop, HDMI TV, a USB UVC webcam, and optionally a USB Audio Class microphone. For this prototype, switch to an **X11** desktop session in `sudo raspi-config` → Advanced Options → Wayland → X11; reboot and verify `echo $XDG_SESSION_TYPE`.

Transfer or clone the files onto the Pi, then:

```bash
cd ~/pi-gesture-mic
chmod +x *.sh
./install_pi.sh
v4l2-ctl --list-devices
ls /dev/video*
./run_pi.sh
```

The installer creates `.venv`, installs Python dependencies, and downloads `hand_landmarker.task`. It needs internet access. Set `camera_index` appropriately in `gesture_config.json` before running. If the camera is not index 0, try 1, 2, etc. and verify capture. Camera indices can change on reboot.

The application requires a graphical desktop. Running from SSH without a valid X11 display usually fails. For an X11 desktop, use a local terminal for the first run.

## Kiosk display

```bash
./start_kiosk.sh https://YOUR-APP-URL
```

The kiosk launcher opens Chromium; the gesture controller runs independently. Once tested, set `show_preview` to `false` and launch `./run_pi.sh` separately or install desktop auto-start using `./setup_autostart.sh`. When preview is off, hotkeys in the camera window do not work; stop the process from a terminal.

## Validate

```bash
uname -m
echo "$XDG_SESSION_TYPE"
v4l2-ctl --list-devices
arecord -l
.venv/bin/python -m unittest discover -s tests -v
```

A `aarch64` CPU and `x11` session are expected for this release. See [Troubleshooting](TROUBLESHOOTING.md).
