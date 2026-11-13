"""No-display dependency/model smoke check used before setup."""
from pathlib import Path
import cv2
import mediapipe as mp
import numpy as np
import tkinter
from PIL import Image

root = Path(__file__).resolve().parents[1]
options = mp.tasks.vision.HandLandmarkerOptions(
    base_options=mp.tasks.BaseOptions(model_asset_path=str(root/'hand_landmarker.task')),
    running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2)
with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
    result = tracker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                      data=np.zeros((240,320,3),dtype=np.uint8)), 0)
    assert result.hand_landmarks == []
assert Image.new('RGB',(1,1)).size == (1,1)
print(f'Model inference passed | MediaPipe {mp.__version__} | OpenCV {cv2.__version__} | Tk {tkinter.TkVersion}')
