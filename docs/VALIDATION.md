# Validation record and Pi acceptance checklist

Release candidate: 2.1.0, 2026-11-12. Development host: Apple Silicon Mac, not a Raspberry Pi.

## Completed

- **65 automated tests pass**, including the original eight gesture tests. Coverage includes ownership order/crossings/label flips, unknown/opposite hand rejection, simultaneous claims, owner/secondary loss, stale pinch rearming, dual-mode click suppression, calibrated pointer/drag equivalence and emergency release.
- Calibration geometry, stability/time/identity sampling, pinch hysteresis, complete guided state sequence, five target clicks, drag/drop, missed targets and cancellation isolation pass synthetic tests.
- Profile migration, isolation, persistence, invalid field/name/geometry rejection and preservation of corrupt or previously saved profiles are tested.
- Installer control flow is executed with fake OS commands: initial install/rerun, headless resume into Wayland, virtual-input provisioning/preflight, input-access failure, legacy X11 flag as a no-op, failed prerequisites, opt-in autostart, no-launch and invalid options. The harness substitutes OS identity/root checks and omits host-blocked `/dev/fd` tee redirection; it does **not** exercise real apt, sudo, udev/logind ACL assignment or kernel device creation.
- Wayland backend event tests cover independent device capabilities, normalized/clamped absolute axes, relative-event fractional accumulation, click/drag release, scroll axes, zoom modifier ordering, interrupted key writes, held-input cleanup and partial-creation failure. Session selection prefers Wayland even with an XWayland DISPLAY; the Wayland factory never imports PyAutoGUI. These use event-recording fakes, not a running compositor.
- Microphone source selection excludes monitor inputs; missing sources cannot change defaults. Cancellation stops the recorder and removes temporary audio. Capture stale/error paths refuse old frames; duplicate frames are not reprocessed.
- Python source compiles, all shell scripts pass `bash -n` and ShellCheck, and Git diff whitespace checks pass.
- Actual **MediaPipe 1.2.3 blank-frame hand-model inference** passed on the Mac using the pinned core dependencies and downloaded checksum-verified model. This is a library/API/model smoke test, not a measured camera accuracy test.
- ARM64 core wheels for the selected MediaPipe/OpenCV/NumPy/Pillow versions downloaded successfully for Python 3.13. Python 3.11 ARM64 runtime dependency resolution/download was also checked. Foreign-platform binaries were not executed on the Mac.
- Wizard positioning, corner, pinch, target, drag and completion screens were rendered; representative layouts were visually inspected. The Tk device selector cannot be run on this host's Python because `_tkinter` is absent; the installer installs `python3-tk` on the Pi.
- Package tests verify deterministic bytes, archive CRCs, SHA-256 manifests, executable shell permissions and exclusion of `.git`, `.venv`, models, profiles, recordings and logs. The generated archive is extracted and its tests are run again before delivery.

## Required on the actual Pi 5

1. Start from supported 64-bit Desktop with camera/mic unplugged. Extract the ZIP into a path containing spaces and run the single installer. Confirm actionable empty-device states, then plug devices in and Refresh.
2. On a default Wayland desktop, run v2.1 installation and confirm no X11 switch/reboot request. Check /dev/uinput ACLs, no-input preflight, virtual device discovery and actual pointer/key delivery in native Wayland Chromium. Repeat after reboot and login. Verify headless-install setup resume. Check both Bookworm/Wayfire and Trixie/labwc as available.
3. Confirm dependency/model inference, Tk window sizing, OpenCV fullscreen presentation and device permissions on the installed OS. Validate Qt library behavior on the actual image.
4. Position the real camera and complete every calibration step with each intended user. Measure actual frame rate, latency, pinch false positives, accuracy, reach comfort and sustained thermal behavior at the target resolution/distance/lighting.
5. Validate pointer motion, short/right/double click, hold-drag-release, secondary scroll, both-hand zoom/pan and emergency stop in the intended browser/application. Mouse-corner failsafe is X11-only; test Stop Gesture Control and stop_pi.sh on Wayland. Browser shortcuts are application-dependent; pan is scrolling, not native multitouch.
6. Cross/occlude hands, swap detector order, leave frame during drag, reconnect camera, press Q/Escape, close the window, Ctrl+C and SIGTERM. Confirm no stuck button/modifier and no unintended click. A native inference hang or SIGKILL cannot guarantee application cleanup.
7. Save two profiles, reboot, reconnect USB devices in a different order, switch profiles and rerun installer. Confirm stable identities/settings and that the camera selected is still the intended one. Test cameras lacking USB serial numbers separately.
8. Test microphone capture/playback and signal reporting; cancel mid-recording and confirm the child process exits. Check quiet/clipped input, missing mic, muted output, browser HTTPS permissions and default-source persistence after reboot.
9. Enable/disable login autostart and kiosk preview mode. Check only one controller starts and that applications menu errors are visible.

## Known boundaries

No physical Pi, USB camera, microphone or HDMI display was exercised during this development run. Wayland input is implemented through uinput but remains unverified against a physical Pi/compositor. Speech recognition, CSI-only camera capture, multi-monitor calibration, offline installation and biometric hand identity are not implemented. Global physical-cursor querying/corner failsafe is not available on Wayland. Installer dependencies require internet/sudo. Third-party SDK metrics are described in THIRD_PARTY.md. Successful automated tests do not establish hardware reliability or production acceptance.
