"""Validated, atomic per-user profiles; independent of camera/desktop packages."""
import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NUMERIC_LIMITS = {
    "cursor_smoothing": (0.01, 1), "relative_gain": (0.1, 5),
    "pinch_start_ratio": (0.05, 1.5), "pinch_end_ratio": (0.1, 2.5),
    "pinch_prelock_ratio": (0.1, 3), "pinch_confirmation_ms": (0, 500),
    "pinch_release_ms": (0, 1000), "drag_hold_ms": (100, 2000),
    "hand_loss_ms": (100, 2000), "toggle_cooldown_ms": (0, 3000),
    "double_click_interval_ms": (30, 500), "drag_gain": (0.1, 5),
    "drag_smoothing": (0.01, 1), "scroll_step_pixels": (10, 300),
    "zoom_step_ratio": (0.03, 0.5), "two_hand_pan_step_pixels": (10, 300),
    "track_match_max_distance": (0.05, 0.8),
    "telemetry_sample_interval_ms": (100, 10000),
    "screen_transition_rate": (0.01, 1.0),
    "screen_motion_deadband": (0.0001, 0.05)
}



def config_home():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pi-gesture-mic"


def state_home():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "pi-gesture-mic"


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def validate(cfg):
    if not isinstance(cfg, dict) or cfg.get("schema_version") not in (6, 7):
        raise ValueError("Expected a version 6 or 7 configuration")
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("camera_device", None)
    cfg.setdefault("microphone_source", None)
    cfg.setdefault("mirror_camera", True)
    cfg.setdefault("calibration", None)
    cfg["schema_version"] = 7
    for key, (lo, hi) in NUMERIC_LIMITS.items():
        if not finite(cfg.get(key)) or not lo <= cfg[key] <= hi:
            raise ValueError(f"Invalid {key}; expected {lo} to {hi}")
    if not cfg["pinch_start_ratio"] < cfg["pinch_end_ratio"]:
        raise ValueError("Pinch release must exceed pinch activation")
    if cfg["pinch_prelock_ratio"] <= cfg["pinch_start_ratio"]:
        raise ValueError("Pinch prelock must exceed pinch activation")
    if cfg.get("pointer_mode") not in ("screen", "relative"):
        raise ValueError("Pointer mode must be screen or relative")
    bounds = cfg.get("camera_active_region")
    if (not isinstance(bounds, list) or len(bounds) != 4 or
        not all(finite(v) for v in bounds) or
        not (0 <= bounds[0] < bounds[2] <= 1 and 0 <= bounds[1] < bounds[3] <= 1)):
        raise ValueError("Active region must be [left, top, right, bottom] within 0..1")
    if type(cfg.get("pointer_landmark")) is not int or cfg["pointer_landmark"] not in (0, 9, 8):
        raise ValueError("Pointer landmark must be 0, 9 or 8")
    for key in ("show_preview", "show_landmarks", "telemetry_enabled", "two_hand_pan", "mirror_camera"):
        if type(cfg.get(key)) is not bool:
            raise ValueError(f"{key} must be true or false")
    if cfg.get("actions") != {"INDEX": "left_click_drag", "MIDDLE": "right_click", "RING": "double_click", "PINKY": "toggle"}:
        raise ValueError("The standard four pinch actions are required")
    for key, lo, hi in (("camera_index", 0, 255), ("capture_width", 320, 1920), ("capture_height", 240, 1080)):
        if type(cfg.get(key)) is not int or not lo <= cfg[key] <= hi:
            raise ValueError(f"Invalid {key}")
    device = cfg["camera_device"]
    if device is not None and (not isinstance(device, str) or not device.startswith("/dev/")):
        raise ValueError("Camera device must be a /dev/ path")
    for key in ("model_path", "microphone_source"):
        if cfg.get(key) is not None and (not isinstance(cfg[key], str) or not cfg[key] or "\x00" in cfg[key]):
            raise ValueError(f"Invalid {key}")
    if not cfg.get("model_path"):
        raise ValueError("A model path is required")
    cal = cfg["calibration"]
    if cal is not None:
        from calibration import validate_calibration
        validate_calibration(cal)
        if cfg["pointer_landmark"] != 0:
            raise ValueError("Calibrated mapping uses the wrist (landmark 0)")
        if cal["mirror_camera"] != cfg["mirror_camera"]:
            raise ValueError("Camera mirror changed; recalibrate before using this profile")
        if cal["camera_device"] != cfg["camera_device"]:
            raise ValueError("Camera changed; recalibrate before using this profile")
    return cfg


class ProfileStore:
    def __init__(self, root=None, defaults=None):
        self.root = Path(root) if root else config_home()
        self.defaults = Path(defaults) if defaults else ROOT / "gesture_config.json"

    def path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,47}", name):
            raise ValueError("Use 1-48 letters, numbers, spaces, hyphens or underscores for a profile")
        return self.root / "profiles" / (name + ".json")

    def names(self):
        return sorted(p.stem for p in (self.root / "profiles").glob("*.json"))

    def active(self):
        path = self.root / "settings.json"
        name = json.loads(path.read_text())["active_profile"] if path.exists() else "Default"
        self.path(name)
        return name

    def load(self, name=None):
        name = name or self.active()
        path = self.path(name)
        return validate(json.loads((path if path.exists() else self.defaults).read_text()))

    def save(self, name, cfg, activate=True):
        cfg = validate(cfg)
        atomic_json(self.path(name), cfg)
        if activate:
            atomic_json(self.root / "settings.json", {"active_profile": name})
        return cfg
