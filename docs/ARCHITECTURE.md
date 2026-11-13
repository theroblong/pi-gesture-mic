# Architecture

```text
Setup: Tk profile/device selector -> live camera preview + explicit audio test
                                 -> OpenCV calibration / contained gesture practice
                                 -> validated atomic per-user profile

USB UVC camera -> threaded OpenCV capture -> MediaPipe VIDEO hand landmarks
               -> HandAssociator -> per-track PinchState -> GestureEngine events
               -> DesktopAdapter -> X11: PyAutoGUI
                                 -> Wayland: uinput absolute/relative mice + keyboard

USB mic -> PipeWire/PulseAudio desktop source -> default input for applications
```

- `gesture_engine.py`: deterministic, dependency-free association, ownership, debounce, click/drag/dual-hand state transitions. Known opposite or unknown handedness cannot inherit known tracks. Global assignment and ambiguity margins replace greedy matching. Label/motion conflicts withhold input. After track expiry only a uniquely visible same-known-handedness hand may reacquire ownership; this is not biometric identification.
- `calibration.py`: projective mapping, geometry rejection, stable sample windows, identity-bound timed gesture holds and personalized pinch thresholds. No camera or numerical-library dependencies.
- `calibration_ui.py`: guided state machine and OpenCV rendering; practice consumes engine events locally, never through the desktop adapter. All state is copied until successful save. Pose-aware dwell captures work before learned pinch thresholds exist; target-motion gates prevent duplicate corners. Long command pinches restart/cancel, and a fresh final pinch confirms saving. Keyboard shortcuts remain available.
- `profiles.py`: version 6 migration, version 7 validation, safe names and atomic writes. Profiles live outside the application directory.
- `devices.py`: bounded inventory commands, persistent device identifiers, capture worker with a three-second stale-frame timeout, and temporary opt-in audio recording/playback.
- `setup_ui.py`: Tk/Pillow device/profile screen with asynchronous discovery/audio tests and live preview.
- `desktop_input.py`: automatic session selection, independent uinput absolute/relative pointer and keyboard devices, normalized screen coordinates, true relative events, held-input cleanup and partial-creation recovery. No PyAutoGUI import occurs on Wayland.
- `gesture_mouse_pi.py`: CLI, singleton lock, desktop compatibility checks, runtime event adapter, bounded telemetry, signal/failsafe cleanup.
- `kiosk_session.py`: Cage child supervisor; waits for camera/model/uinput readiness before starting native Wayland Chromium, selects the saved microphone, persists browser consent and tears down both process groups on exit/failure. `--kiosk` bypasses setup/preview and display-size discovery without editing profiles.
- `tools/desktop_entry.py`: safe desktop entry generation and removal. `tools/verify_runtime.py`: actual no-camera model inference. `tools/build_release.py`: deterministic allowlisted package with manifests.

Track loss immediately cancels held input. Secondary loss cancels two-hand state and pending owner clicks; reappearance requires open fingers before new gestures. Owner target movement is locked before a pinch, and calibrated dragging uses transformed wrist displacement. Right/double clicks are suppressed while the other hand is scrolling. Physical track ambiguity cannot be perfectly eliminated with a monocular camera; conservative pauses are intentional.

Runtime always starts disabled. SIGTERM, Ctrl+C, camera exceptions, preview close and PyAutoGUI failsafe enter cleanup; cleanup temporarily disables failsafe only to release held input. SIGKILL/power loss cannot run cleanup. On Wayland, the kernel virtual devices are created only during runtime (and briefly during the no-input installer check), and closed on exit. Physical input is not read or grabbed. A udev rule grants active local sessions access to `/dev/uinput`; no privileged daemon, network service or remote control port is installed. PyAutoGUI’s corner failsafe is X11-only; the Stop launcher sends SIGTERM on either desktop.
