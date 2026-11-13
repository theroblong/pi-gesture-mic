# Gestures and configuration

Edit `gesture_config.json` while the controller is stopped, or use supported keyboard tuning commands with the camera preview in focus. Use `S` to save and `R` to reload while running. Config uses `schema_version: 6`. Do not replace with an old v5 config.

| Setting | What it controls |
|---|---|
| `camera_index` | USB UVC webcam OpenCV index on the Pi |
| `capture_width`, `capture_height` | Processing target frame dimensions |
| `pointer_mode` | `screen` absolute mapping or `relative` movement |
| `pointer_landmark` | `0` wrist, `9` palm base, `8` index fingertip |
| `camera_active_region` | `[left,top,right,bottom]` normalized camera rectangle to entire TV |
| `cursor_smoothing` | Cursor smoothing parameter |
| `relative_gain` | Relative-mode pointer movement gain |
| `screen_transition_rate` | Rate for aligning absolute screen mapping |
| `screen_motion_deadband` | Discards tiny input movements |
| `pinch_start_ratio`, `pinch_end_ratio` | Pinch detection hysteresis thresholds |
| `pinch_prelock_ratio` | Freezes target before fingers touch |
| `pinch_confirmation_ms` | Minimum time before confirmed pinch |
| `pinch_release_ms` | Release debounce |
| `drag_hold_ms` | Index pinch duration before drag |
| `hand_loss_ms` | Lost-hand grace interval |
| `track_match_max_distance` | Hand identity matching threshold |
| `show_preview` | Show/hide debug camera window |
| `telemetry_enabled` | Enable local gesture event logging |

### Screen coverage vs precision

`camera_active_region: [0.14,0.12,0.86,0.88]` maps the central 72% of camera width and 76% of height over the full display. **Smaller rectangle means less wrist travel** (faster, less precise); larger means more travel (slower, more precise). The box reflects a virtual coordinate mapping, **not** physical TV corners.

### Multi-hand ownership

Either hand can use a pinky pinch to claim ownership while control is off. The owner's pinky pinch disables control, allowing the other hand to claim ownership next. The non-owner hand can perform secondary scrolling and two-hand operations. When hands cross or leave frame, hand identity matching may be unreliable.

### Cursor stability

The wrist is the default tracking landmark so finger-pinching should not move the target as much as index-tip tracking. The prelock region freezes the cursor while pinching; continuous dragging follows the hand. Brief tracking loss pauses movement instead of permanently disabling user control.
