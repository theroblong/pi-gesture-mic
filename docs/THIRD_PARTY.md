# Dependencies and data handling

Direct pins are in `requirements.txt`: MediaPipe 1.2.3, OpenCV contrib 4.12.0.88, NumPy 2.2.6, Pillow 12.0.0 PyAutoGUI 0.9.54, and Linux-only [python-evdev 1.9.2](https://pypi.org/project/evdev/1.9.2/) (BSD license). The installer uses **only one OpenCV wheel distribution** to avoid competing `cv2` installations. Compiled vision packages must have binary wheels. The small Linux evdev extension builds against system input headers; the installer supplies the compiler, Python headers and linux-libc-dev. Transitive dependencies are resolved by pip and recorded after installation; this is not a complete transitive hash lock.

ARM64 wheel availability was checked against [MediaPipe's PyPI release](https://pypi.org/project/mediapipe/1.2.3/), [OpenCV](https://pypi.org/project/opencv-contrib-python/4.12.0.88/), [NumPy](https://pypi.org/project/numpy/2.2.6/) and [Pillow](https://pypi.org/project/Pillow/12.0.0/). Package downloads use HTTPS and pip's distribution checks. The source ZIP does not bundle these dependencies or their binaries; their respective licenses apply when installed (MediaPipe Apache-2.0, OpenCV Apache-2.0 and bundled third-party notices, NumPy BSD, Pillow HPND, PyAutoGUI BSD).

Hand model: [Google's versioned hand landmarker model](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task), SHA-256:

```text
fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1
```

The model is downloaded separately, not bundled in the release. See [MediaPipe hand landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) for model details and applicable terms.

Camera frames are processed locally and are not recorded by this application. Local telemetry contains gesture events and normalized pinch ratios, not video; T disables it and rotation limits it to about 4 MB total. Profiles store calibration coordinates and settings locally. Audio is captured only after an explicit test action, with temporary files removed after playback or error cleanup.

**MediaPipe 1.2.3 separately documents performance/utilization metrics sent to Google**, even though input images/audio are processed on-device. See its [privacy notice](https://pypi.org/project/mediapipe/1.2.3/#description). Application telemetry settings do not control third-party SDK metrics. Review that behavior before deployment; this package does not claim fully offline/private SDK operation.
