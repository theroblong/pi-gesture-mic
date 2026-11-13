# Profiles and configuration

`gesture_config.json` is a default/legacy seed. Runtime settings are saved per desktop account under `~/.config/pi-gesture-mic/profiles/NAME.json`; `settings.json` records the active profile. XDG_CONFIG_HOME overrides the base directory. Valid profile names contain 1–48 letters, numbers, spaces, hyphens or underscores, beginning with a letter/number.

Use **Gesture Control Setup** to create/select a profile and change devices. Saving uses a temporary file plus atomic replacement; failed validation cannot replace an existing profile. A version 6 configuration is migrated in memory to version 7, keeping its tuning values. The original seed file is never rewritten by runtime. Malformed profiles fail with an error rather than silently resetting personal calibration.

```bash
bash run_pi.sh --setup
bash run_pi.sh --profile "Alice"
bash run_pi.sh --check-config --profile "Alice"
```

The UI selects a stable camera device path where available and a persistent desktop microphone source name. Changing the camera or mirroring invalidates calibration. Moving the same physical camera cannot be detected automatically: recalibrate after any camera/seating change. A camera without stable identifiers may fall back to `/dev/videoN`; verify it after reconnecting.

## Calibration

Four camera-plane wrist points (top-left, top-right, bottom-right, bottom-left) map to 10%/90% inset display targets via a projective transform. Samples require at least 0.7 seconds, eight observations, and limited wrist jitter. Non-convex, tiny, crossed or excessively distorted calibration areas are rejected. Center reach must agree within 15% normalized Euclidean error. The center is stored as a comfort/accuracy check, not a fifth fitted correspondence.

Three open/pinch sample pairs estimate separated activation/release thresholds using conservative quantiles. Practice requires five short index clicks within 9% normalized Euclidean screen distance and a successful hold-drag-release. Accuracy metrics and the drag result are saved. Drag hold duration uses the existing tunable setting (350 ms by default); practice validates it rather than deriving a physiological optimum. All tests remain inside the setup canvas.

Calibrated screen pointing uses the wrist directly; finger closure locks the target. Drag uses displacement under the same mapping, preserving the click location. Calibration is 2D movement mapping, not 3D ray pointing. The adapter keeps generated movements one pixel away from failsafe corners. Normalized calibration survives resolution changes, but changing display placement, aspect ratio or working distance may require recalibration.

## Key settings

| Setting | Meaning |
|---|---|
| `camera_device`, `camera_index` | Stable device path, or legacy numeric fallback |
| `microphone_source` | Persistent PulseAudio/PipeWire source name; null keeps system default |
| `mirror_camera` | Mirror before tracking and preview; defaults true |
| `capture_width`, `capture_height` | Requested capture and processing dimensions, default 960×540 |
| `calibration` | Validated matrix/corners, center, camera orientation, hand and practice metrics |
| `pointer_mode` | `screen` or legacy `relative` |
| `pointer_landmark` | Legacy wrist 0, palm base 9 or fingertip 8; calibration requires wrist 0 |
| `camera_active_region` | Legacy uncalibrated rectangle `[left,top,right,bottom]` |
| `cursor_smoothing` | Screen interpolation/relative movement factor |
| `relative_gain`, `drag_gain`, `drag_smoothing` | Legacy relative movement/drag tuning |
| `pinch_start_ratio`, `pinch_end_ratio` | Pinch activation/release hysteresis normalized by palm width |
| `pinch_prelock_ratio` | Freeze target before confirmed finger contact |
| `pinch_confirmation_ms`, `pinch_release_ms` | Activation/release debounce |
| `drag_hold_ms` | Hold before mouse down; default 350 ms |
| `hand_loss_ms` | Track retention window; a drag releases on first missing owner frame |
| `track_match_max_distance` | Maximum spatial association distance |
| `scroll_step_pixels`, `two_hand_pan_step_pixels` | Movement accumulated per scroll notch |
| `zoom_step_ratio` | Relative separation change per browser zoom step |
| `show_preview`, `show_landmarks` | Runtime preview and tracking overlay |
| `telemetry_enabled` | Local event/ratio logging, with a 2 MB rotation plus one backup |

## Preview controls

| Keys | Action |
|---|---|
| Q, Escape or window close | Stop and release held input |
| Space | Disable, or enable when exactly one hand is visible |
| X | Reset ownership and interactions |
| S / R | Save/reload the active profile (device/model changes require restart) |
| T | Toggle local telemetry |
| M | Screen / relative mode |
| - / = | Shrink/grow legacy active region; calibrated profiles use Setup instead |
| 1 / 2 | Decrease/increase drag hold by 50 ms |
| 3 / 4 | Release debounce by 20 ms |
| 5 / 6 | Confirmation debounce by 10 ms |
| 7 / 8 | Pinch activation ratio by 0.02 |
| 9 / 0 | Smoothing by 0.05 |
| [ / ] | Pinch release ratio by 0.02 |

With preview disabled, these keys do not receive events; use the terminal or stop the process. Setup and runtime share a per-user process lock so two instances cannot compete for the camera and pointer.
