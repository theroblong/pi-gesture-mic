# Changelog

## 2.0.0 — 2026-11-12

- Live device/profile setup with camera preview, persistent source names and explicit microphone capture/playback diagnostics.
- Guided camera positioning, controlling-hand selection, four-corner/center mapping, three pinch calibration pairs, five click targets and drag practice; cancel preserves previous profiles.
- Atomic per-user profiles outside the application directory, version 6 migration and strict validation.
- Conservative global hand association, ambiguous-claim handling, safer reacquisition, secondary-loss cancellation and click suppression during dual-hand transitions.
- Consistent calibrated wrist pointing/dragging; original relative control, click/right/double click, scroll, zoom/pan and tuning retained.
- Camera timeout handling, single-instance guard, SIGTERM/window-close cleanup and failsafe-safe button release.
- One-script installer with pinned direct runtime dependencies, model checksum/inference, X11 transition/resume, desktop shortcuts, repeatable recovery and optional autostart.
- Automated logic/installer/package tests and reproducible v2 ZIP with SHA-256 manifests. Physical Pi acceptance remains pending.

## 1.0.0

Initial Raspberry Pi X11 adaptation of the v6 dual-hand engine, basic preview/manual tuning, microphone diagnostics, kiosk/autostart scripts and eight engine tests. The v1 ZIP remains in dist as historical material.
