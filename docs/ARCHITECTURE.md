# Architecture

```text
USB UVC camera --> OpenCV --> MediaPipe 21 hand landmarks
                                |
                                v
                         GestureEngine
                   owner hand / other hand
                       pinch state machine
                          |        |
                      cursor      scroll/zoom
                          |        |
                          v        v
                    LinuxX11Adapter (PyAutoGUI)
                                  |
                      X11 desktop on HDMI TV
                                  |
                          Chromium kiosk UI

USB microphone --> ALSA --> PipeWire --> browser audio input (permission required)
```

This release ports the v6 engine to a Pi 5 desktop running X11. Gesture recognition and Linux desktop injection are separate layers. Mic diagnostics are independent of gesture processing.

## Future production direction

For native Wayland and better integration with Aevah's React UI, a local WebSocket gesture event service would avoid desktop mouse emulation and support semantic actions (select, zoom, rotate, grab) directly. A four-point or richer calibration routine would better align hand-to-display mapping. Neither is implemented in this release.

## Scope and validation

Unit tests focus on gesture-engine behavior. The package has not undergone Pi 5 hardware, camera throughput, desktop input, browser permissions, or microphone testing.
