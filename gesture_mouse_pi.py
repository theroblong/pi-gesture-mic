"""Gesture Mouse Pi: two-hand ownership + camera-to-TV pointer mapping on X11.

Run from ~/gesture-control with MediaPipe hand_landmarker.task in same folder.
SPACE: disable control, or enable only if exactly one hand is visible.
PINKY pinch: enable using that hand; only the owner can disable.
Owner index: short click / long drag; middle right-click; ring double-click.
Other hand index pinch: scroll; both index pinches: zoom + pan.
Q quit, X reset, S save, R reload, T telemetry; numeric tuning shortcuts.
For kiosk mode set show_preview=false; terminate with Ctrl+C or systemctl --user stop.
"""
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import mediapipe as mp
import pyautogui as pg

from gesture_engine import GestureEngine, clamp, distance

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "gesture_config.json"
LOG_PATH = ROOT / "gesture_events.jsonl"
CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),(0,17)
]
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


def load_config():
    if not CONFIG_PATH.exists():
        alt = ROOT / "gesture_config_v6.json"
        if alt.exists():
            raise FileNotFoundError(f"Missing {CONFIG_PATH.name}. Run: cp {alt.name} gesture_config.json")
        raise FileNotFoundError(f"Missing {CONFIG_PATH}; extract the complete ZIP into ~/gesture-control")
    cfg = json.loads(CONFIG_PATH.read_text())
    if cfg.get("schema_version") != 6:
        raise ValueError("v6 requires gesture_config.json schema_version 6; back up and copy v5 config")
    for key, (lo, hi) in NUMERIC_LIMITS.items():
        if not isinstance(cfg.get(key), (int, float)) or not lo <= cfg[key] <= hi:
            raise ValueError(f"Invalid {key}; expected {lo}–{hi}")
    if cfg["pinch_start_ratio"] >= cfg["pinch_end_ratio"]:
        raise ValueError("pinch_start_ratio must be smaller than pinch_end_ratio")
    if cfg["pinch_prelock_ratio"] <= cfg["pinch_start_ratio"]:
        raise ValueError("pinch_prelock_ratio must be above pinch_start_ratio")
    if cfg.get("pointer_mode") not in ("screen", "relative"):
        raise ValueError("pointer_mode must be screen or relative")
    bounds = cfg.get("camera_active_region")
    if (not isinstance(bounds, list) or len(bounds) != 4 or
        not all(isinstance(v, (int, float)) for v in bounds) or
        not (0 <= bounds[0] < bounds[2] <= 1 and
             0 <= bounds[1] < bounds[3] <= 1)):
        raise ValueError("camera_active_region must be [left, top, right, bottom] within 0..1")
    if cfg.get("pointer_landmark") not in (0, 9, 8):
        raise ValueError("pointer_landmark must be 0 (wrist), 9 (palm base), or 8")
    if not isinstance(cfg.get("show_preview", True), bool):
        raise ValueError("show_preview must be true or false")
    if cfg.get("actions") != {"INDEX":"left_click_drag", "MIDDLE":"right_click",
                              "RING":"double_click", "PINKY":"toggle"}:
        raise ValueError("v5 currently requires the standard four pinch actions")
    for k in ("camera_index", "capture_width", "capture_height"):
        if not isinstance(cfg.get(k), int) or cfg[k] < 0:
            raise ValueError(f"Invalid {k}")
    return cfg


def save_config(config):
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n")
    tmp.replace(CONFIG_PATH)


class LinuxX11Adapter:
    def __init__(self, cfg):
        self.cfg = cfg
        pg.FAILSAFE = True
        pg.PAUSE = 0
        self.sw, self.sh = pg.size()
        self.mx, self.my = pg.position()
        self.drag_held = False
        self.scroll_pixels = [0.0, 0.0]
        self.pan_pixels = [0.0, 0.0]
        self.last_event = "ready"
        self.engine = None
        self.screen_offset = None
        self.last_mapped_target = None

    def log(self, kind, **fields):
        self.last_event = kind
        if self.cfg.get("telemetry_enabled", True):
            entry = {"timestamp_utc":datetime.now(timezone.utc).isoformat(),
                     "event":kind, "owner_id":self.engine.owner_id if self.engine else None,
                     **fields}
            try:
                with LOG_PATH.open("a") as file:
                    file.write(json.dumps(entry) + "\n")
            except OSError as exc:
                print("Telemetry write error:", exc)
        if kind not in ("pointer_delta", "drag_delta", "pointer_reanchor", "secondary_scroll_delta", "two_hand_pan_delta"):
            print(kind, fields if fields else "")

    def move(self, dx, dy, smoothing):
        # Relative motion from wrist or palm; never snap to an absolute wrist position.
        self.mx, self.my = pg.position()
        self.mx = clamp(self.mx + dx * smoothing, 0, self.sw - 1)
        self.my = clamp(self.my + dy * smoothing, 0, self.sh - 1)
        pg.moveTo(int(self.mx), int(self.my), duration=0)

    def reanchor(self):
        self.mx, self.my = pg.position()
        self.screen_offset = None
        self.last_mapped_target = None

    def screen_move(self, x, y, dx, dy):
        left, top, right, bottom = self.cfg["camera_active_region"]
        # Camera preview has already been mirrored. Clamp the active region
        # to reach all edges without moving a hand outside the camera frame.
        target_x = clamp((x - left) / (right - left), 0, 1) * (self.sw - 1)
        target_y = clamp((y - top) / (bottom - top), 0, 1) * (self.sh - 1)
        current_x, current_y = pg.position()
        if self.screen_offset is None:
            # Preserve trackpad position on first activation. Ease into
            # absolute screen coordinates ONLY as the wrist actually moves.
            self.screen_offset = [current_x - target_x, current_y - target_y]
        if math.hypot(dx, dy) < self.cfg["screen_motion_deadband"]:
            return
        # Ease out the anchor offset so the pointer eventually tracks camera
        # coordinates directly, without a sudden activation jump.
        decay = self.cfg["screen_transition_rate"]
        self.screen_offset[0] *= (1 - decay)
        self.screen_offset[1] *= (1 - decay)
        goal_x = clamp(target_x + self.screen_offset[0], 0, self.sw - 1)
        goal_y = clamp(target_y + self.screen_offset[1], 0, self.sh - 1)
        alpha = self.cfg["cursor_smoothing"]
        next_x = current_x + alpha * (goal_x - current_x)
        next_y = current_y + alpha * (goal_y - current_y)
        pg.moveTo(int(clamp(next_x, 0, self.sw-1)),
                  int(clamp(next_y, 0, self.sh-1)), duration=0)

    def scroll(self, dx, dy, accum, step):
        accum[0] += dx * self.sw
        accum[1] += dy * self.sh
        horizontal = math.trunc(accum[0] / step)
        vertical = math.trunc(accum[1] / step)
        if vertical:
            pg.scroll(-vertical)
            accum[1] -= vertical * step
        if horizontal:
            pg.hscroll(horizontal)
            accum[0] -= horizontal * step

    def perform(self, events):
        for kind, data in events:
            if kind == "pointer_reanchor" or kind == "control_on":
                self.reanchor()
            elif kind == "pointer_screen":
                self.screen_move(data["x"], data["y"], data["dx"], data["dy"])
            elif kind == "pointer_delta":
                self.move(data["dx"]*self.sw*self.cfg["relative_gain"],
                          data["dy"]*self.sh*self.cfg["relative_gain"],
                          self.cfg["cursor_smoothing"])
            elif kind == "drag_delta":
                self.move(data["dx"]*self.sw*self.cfg["drag_gain"],
                          data["dy"]*self.sh*self.cfg["drag_gain"],
                          self.cfg["drag_smoothing"])
            elif kind == "mouse_click":
                pg.click(button=data["button"])
            elif kind == "mouse_double_click":
                pg.doubleClick(interval=data["interval_ms"]/1000)
            elif kind == "mouse_down":
                pg.mouseDown(button="left")
                self.drag_held = True
            elif kind == "mouse_up":
                if self.drag_held:
                    pg.mouseUp(button="left")
                    self.drag_held = False
            elif kind == "secondary_scroll_delta":
                self.scroll(data["dx"], data["dy"], self.scroll_pixels,
                            self.cfg["scroll_step_pixels"])
            elif kind == "two_hand_pan_delta":
                self.scroll(data["dx"], data["dy"], self.pan_pixels,
                            self.cfg["two_hand_pan_step_pixels"])
            elif kind == "zoom_step":
                # macOS browser/document zoom, not arbitrary 3D object scaling.
                pg.hotkey("ctrl", "+" if data["direction"] > 0 else "-")
            if kind not in ("pointer_screen", "pointer_delta", "drag_delta", "pointer_reanchor", "secondary_scroll_delta", "two_hand_pan_delta"):
                self.log(kind, **data)

    def emergency_release(self):
        if self.drag_held:
            pg.mouseUp(button="left")
            self.drag_held = False


def label(result, i):
    try:
        return result.handedness[i][0].category_name
    except (AttributeError, IndexError, TypeError):
        return "Unknown"


def draw(frame, text, y, color=(255,255,255), scale=0.53):
    cv2.putText(frame, text, (15,y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def handle_key(key, engine, adapter, cfg, now):
    if key == ord("q"):
        return False
    if key == 32:
        adapter.perform(engine.keyboard_toggle(now))
    elif key == ord("x"):
        adapter.perform(engine.reset())
    elif key == ord("s"):
        save_config(cfg)
        adapter.log("config_saved")
    elif key == ord("r"):
        new = load_config()
        if any(new[k] != cfg[k] for k in ("camera_index", "capture_width", "capture_height", "model_path")):
            print("Camera/model edits require restart")
        for k in ("camera_index", "capture_width", "capture_height", "model_path"):
            new[k] = cfg[k]
        adapter.perform(engine.reset())
        cfg.clear()
        cfg.update(new)
        engine.cfg = cfg
        engine.associator.timeout = cfg["hand_loss_ms"] / 1000
        engine.associator.max_distance = cfg["track_match_max_distance"]
        adapter.log("config_reloaded")
    elif key == ord("m"):
        cfg["pointer_mode"] = "relative" if cfg["pointer_mode"] == "screen" else "screen"
        adapter.reanchor()
        adapter.log("pointer_mode_changed", mode=cfg["pointer_mode"])
    elif key == ord("-"):
        # Smaller active region -> greater hand-to-screen sensitivity.
        region = cfg["camera_active_region"]
        cx, cy = (region[0]+region[2])/2, (region[1]+region[3])/2
        half_w = max(0.15, (region[2]-region[0])/2 - 0.025)
        half_h = max(0.15, (region[3]-region[1])/2 - 0.015)
        cfg["camera_active_region"] = [round(clamp(cx-half_w,0,1),3), round(clamp(cy-half_h,0,1),3), round(clamp(cx+half_w,0,1),3), round(clamp(cy+half_h,0,1),3)]
        adapter.reanchor()
        adapter.log("active_region_changed", bounds=cfg["camera_active_region"])
    elif key == ord("="):
        # Larger active region -> less sensitive hand movement.
        region = cfg["camera_active_region"]
        cx, cy = (region[0]+region[2])/2, (region[1]+region[3])/2
        half_w = min(0.5, (region[2]-region[0])/2 + 0.025)
        half_h = min(0.5, (region[3]-region[1])/2 + 0.015)
        cfg["camera_active_region"] = [round(clamp(cx-half_w,0,1),3), round(clamp(cy-half_h,0,1),3), round(clamp(cx+half_w,0,1),3), round(clamp(cy+half_h,0,1),3)]
        adapter.reanchor()
        adapter.log("active_region_changed", bounds=cfg["camera_active_region"])
    elif key == ord("t"):
        cfg["telemetry_enabled"] = not cfg.get("telemetry_enabled", True)
        adapter.log("telemetry_toggled", enabled=cfg["telemetry_enabled"])
    else:
        adjustments = {
            ord("1"):("drag_hold_ms", -50), ord("2"):("drag_hold_ms", 50),
            ord("3"):("pinch_release_ms", -20), ord("4"):("pinch_release_ms", 20),
            ord("5"):("pinch_confirmation_ms", -10), ord("6"):("pinch_confirmation_ms", 10),
            ord("7"):("pinch_start_ratio", -0.02), ord("8"):("pinch_start_ratio", 0.02),
            ord("9"):("cursor_smoothing", -0.05), ord("0"):("cursor_smoothing", 0.05),
            ord("["):("pinch_end_ratio", -0.02), ord("]"):("pinch_end_ratio", 0.02),
        }
        if key in adjustments:
            name, delta = adjustments[key]
            old = cfg[name]
            low, high = NUMERIC_LIMITS[name]
            new_value = clamp(round(old + delta, 3), low, high)
            if name == "pinch_start_ratio":
                new_value = min(new_value, cfg["pinch_end_ratio"] - 0.03,
                                cfg["pinch_prelock_ratio"] - 0.03)
            if name == "pinch_end_ratio":
                new_value = max(new_value, cfg["pinch_start_ratio"] + 0.03)
            cfg[name] = round(new_value, 3)
            adapter.log("parameter_changed", parameter=name, old=old, new=cfg[name])
    return True


def main():
    cfg = load_config()
    import os
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        raise RuntimeError("This Pi package uses X11 mouse injection. Select an X11 session via sudo raspi-config first.")
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("No X11 DISPLAY set: launch from the Pi desktop, not a headless SSH session.")
    model = ROOT / cfg["model_path"]
    if not model.is_file():
        raise FileNotFoundError(f"Missing model: {model}\nDownload the model using README instructions")
    engine = GestureEngine(cfg)
    adapter = LinuxX11Adapter(cfg)
    adapter.engine = engine
    backend = cv2.CAP_V4L2
    cap = cv2.VideoCapture(cfg["camera_index"], backend)
    if not cap.isOpened():
        raise RuntimeError(f"Camera index {cfg['camera_index']} failed to open")
    ok, first_frame = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("Camera opened but could not read a frame")
    print(f"Camera ready: {first_frame.shape}; pinky pinch to select owner")
    print("Q quit | SPACE toggle | X reset | S save | R reload | T telemetry")
    print("M screen/relative mode | - faster / = slower screen mapping")
    opts = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2)
    started = time.monotonic()
    prev_ts = -1
    last_sample = -1e6
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(opts) as tracker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Camera frame failed")
                    break
                frame = cv2.resize(frame, (cfg["capture_width"], cfg["capture_height"]))
                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = max(prev_ts + 1, int((time.monotonic() - started) * 1000))
                prev_ts = ts
                result = tracker.detect_for_video(image, ts)
                now = time.monotonic()
                observations = [([(lm.x, lm.y) for lm in hand], label(result, i))
                                for i, hand in enumerate(result.hand_landmarks)]
                events, visible = engine.update(observations, now)
                adapter.perform(events)
                if (cfg.get("telemetry_enabled", True) and
                    (now - last_sample) * 1000 >= cfg["telemetry_sample_interval_ms"]):
                    last_sample = now
                    # No images or full coordinates. Normalized pinch distances
                    # allow AI-assisted tuning without storing the video feed.
                    for id_, track in visible.items():
                        state = engine.states[id_]
                        adapter.log("hand_sample", track_id=id_,
                                    handedness=track.handedness,
                                    is_owner=(id_ == engine.owner_id),
                                    active=state.active,
                                    ratios={k:round(v,3) for k,v in state.ratios.items()})
                # Show the portion of the camera frame mapped to the screen.
                # Moving the wrist across this rectangle covers the entire TV.
                left, top, right, bottom = cfg["camera_active_region"]
                cv2.rectangle(frame, (int(left*w), int(top*h)),
                              (int(right*w), int(bottom*h)), (235, 165, 70), 2)
                for tx, ty in ((left, top), (right, top), (left, bottom), (right, bottom)):
                    cv2.circle(frame, (int(tx*w), int(ty*h)), 6, (235, 165, 70), -1)
                for track in visible.values():
                    if cfg.get("show_landmarks", True):
                        pts = [(int(x*w), int(y*h)) for x,y in track.hand]
                        linecolor = (0,255,0) if track.id == engine.owner_id else (200,150,65)
                        for a,b in CONNECTIONS:
                            cv2.line(frame, pts[a], pts[b], linecolor, 2)
                        for pt in pts:
                            cv2.circle(frame, pt, 3, (255,0,0), -1)
                        cv2.circle(frame, pts[cfg["pointer_landmark"]], 10,
                                   (0,0,255) if track.id == engine.owner_id else (255,200,0), 2)
                        cv2.putText(frame, f"ID {track.id} {track.handedness}" +
                                    (" OWNER" if track.id == engine.owner_id else ""),
                                    (max(10, pts[0][0]-40), max(18, pts[0][1]-20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, linecolor, 2)
                draw(frame, f"CONTROL {'ON' if engine.enabled else 'OFF'}  OWNER: {engine.owner_id or '-'}  Hands: {len(visible)}", 28,
                     (0,230,0) if engine.enabled else (0,0,230), 0.7)
                y = 56
                for id_, track in sorted(visible.items()):
                    state = engine.states[id_]
                    ratios = " ".join(f"{name[0]}:{value:.2f}" for name,value in state.ratios.items())
                    draw(frame, f"#{id_} {track.handedness} PINCH {state.active or state.candidate or 'NONE'}  {ratios}", y,
                         (0,240,200) if id_ == engine.owner_id else (190,190,190), 0.44)
                    y += 24
                draw(frame, f"Pointer {cfg['pointer_mode'].upper()}  | - faster / = slower | M mode | {'PAUSED - return hand' if engine.owner_paused else 'TRACKING'}", h-96, (240,240,240), 0.47)
                draw(frame, "Dual: other index pinch scrolls | both index pinches zoom/pan", h-72, (240,240,240), 0.47)
                draw(frame, f"Drag {cfg['drag_hold_ms']}ms | Release {cfg['pinch_release_ms']}ms | Confirm {cfg['pinch_confirmation_ms']}ms", h-48,
                     (240,240,240), 0.46)
                draw(frame, "Pinky: select owner / disable | Q quit | S save | R reload | X reset", h-20,
                     (240,240,240), 0.46)
                if cfg.get("show_preview", True):
                    cv2.imshow("Gesture Mouse Pi - Touchscreen Mapping", frame)
                    key = cv2.waitKey(1) & 0xFF
                else:
                    key = 255
                if key != 255 and not handle_key(key, engine, adapter, cfg, now):
                    break
    except pg.FailSafeException:
        print("PyAutoGUI failsafe triggered (top-left corner)")
    finally:
        try:
            adapter.perform(engine.reset())
        finally:
            adapter.emergency_release()
            cap.release()
            cv2.destroyAllWindows()
        print("Stopped. Config:", CONFIG_PATH)
        print("Telemetry:", LOG_PATH)


if __name__ == "__main__":
    main()
