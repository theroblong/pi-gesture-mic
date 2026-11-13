"""Gesture Mouse Pi: two-hand ownership + camera-to-TV pointer mapping on Wayland or X11.

Run from ~/gesture-control with MediaPipe hand_landmarker.task in same folder.
SPACE: disable control, or enable only if exactly one hand is visible.
PINKY pinch: enable using that hand; only the owner can disable.
Owner index: short click / long drag; middle right-click; ring double-click.
Other hand index pinch: scroll; both index pinches: zoom + pan.
Q quit, X reset, S save, R reload, T telemetry; numeric tuning shortcuts.
For kiosk mode set show_preview=false; terminate with Ctrl+C or systemctl --user stop.
"""
import argparse
import os
import signal
import subprocess
import sys
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

cv2 = mp = pg = None  # Loaded only after CLI and desktop checks.

from gesture_engine import GestureEngine, clamp
from profiles import ProfileStore, NUMERIC_LIMITS, state_home
from calibration import transform
from devices import Camera, select_microphone
from desktop_input import session_backend, require_desktop, create_driver

ROOT = Path(__file__).resolve().parent
LOG_PATH = state_home() / "gesture_events.jsonl"
CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),(0,17)
]
STORE = ProfileStore()
PROFILE = None


def load_config():
    return STORE.load(PROFILE)


def save_config(config):
    STORE.save(PROFILE or STORE.active(), config)


class DesktopAdapter:
    def __init__(self, cfg, driver=None):
        self.cfg = cfg
        self.io = driver if driver is not None else pg
        self.native_relative = bool(getattr(type(driver), 'native_relative', False))
        self.io.FAILSAFE = not self.native_relative
        self.io.PAUSE = 0
        self.sw, self.sh = self.io.size()
        self.mx, self.my = self.io.position()
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
                LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                if LOG_PATH.exists() and LOG_PATH.stat().st_size > 2_000_000:
                    LOG_PATH.replace(LOG_PATH.with_suffix(".jsonl.1"))
                with LOG_PATH.open("a") as file:
                    file.write(json.dumps(entry) + "\n")
            except OSError as exc:
                print("Telemetry write error:", exc)
        if kind not in ("pointer_delta", "drag_delta", "pointer_reanchor", "secondary_scroll_delta", "two_hand_pan_delta"):
            print(kind, fields if fields else "")

    def move(self, dx, dy, smoothing, absolute=False):
        if self.native_relative and not absolute:
            self.io.moveRel(dx * smoothing, dy * smoothing, duration=0)
            return
        # Relative motion from wrist or palm; never snap to an absolute wrist position.
        self.mx, self.my = self.io.position()
        self.mx = clamp(self.mx + dx * smoothing, 1, self.sw - 2)
        self.my = clamp(self.my + dy * smoothing, 1, self.sh - 2)
        self.io.moveTo(int(self.mx), int(self.my), duration=0)

    def reanchor(self):
        self.mx, self.my = self.io.position()
        self.screen_offset = None
        self.last_mapped_target = None
        if self.native_relative:
            self.io.reanchor()

    def screen_move(self, x, y, dx, dy):
        left, top, right, bottom = self.cfg["camera_active_region"]
        # Camera preview has already been mirrored. Clamp the active region
        # to reach all edges without moving a hand outside the camera frame.
        if self.cfg.get("calibration"):
            u, v = transform(self.cfg["calibration"]["matrix"], (x, y))
            target_x, target_y = u*(self.sw-1), v*(self.sh-1)
        else:
            target_x = clamp((x - left) / (right - left), 0, 1) * (self.sw - 1)
            target_y = clamp((y - top) / (bottom - top), 0, 1) * (self.sh - 1)
        current_x, current_y = self.io.position()
        if self.cfg.get("calibration"):
            self.screen_offset = [0., 0.]
        if self.screen_offset is None:
            # Preserve trackpad position on first activation. Ease into
            # absolute screen coordinates ONLY as the wrist actually moves.
            self.screen_offset = [current_x - target_x, current_y - target_y]
        if not self.cfg.get("calibration") and math.hypot(dx, dy) < self.cfg["screen_motion_deadband"]:
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
        self.io.moveTo(int(clamp(next_x, 1, self.sw-2)),
                  int(clamp(next_y, 1, self.sh-2)), duration=0)

    def scroll(self, dx, dy, accum, step):
        accum[0] += dx * self.sw
        accum[1] += dy * self.sh
        horizontal = math.trunc(accum[0] / step)
        vertical = math.trunc(accum[1] / step)
        if vertical:
            self.io.scroll(-vertical)
            accum[1] -= vertical * step
        if horizontal:
            self.io.hscroll(horizontal)
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
                if self.cfg.get("calibration") and self.cfg["pointer_mode"] == "screen":
                    matrix = self.cfg["calibration"]["matrix"]
                    before = transform(matrix, (data["x"]-data["dx"], data["y"]-data["dy"]))
                    after = transform(matrix, (data["x"], data["y"]))
                    self.move((after[0]-before[0])*self.sw, (after[1]-before[1])*self.sh, 1., absolute=True)
                else:
                    self.move(data["dx"]*self.sw*self.cfg["drag_gain"],
                              data["dy"]*self.sh*self.cfg["drag_gain"],
                              self.cfg["drag_smoothing"])
            elif kind == "mouse_click":
                self.io.click(button=data["button"])
            elif kind == "mouse_double_click":
                self.io.doubleClick(interval=data["interval_ms"]/1000)
            elif kind == "mouse_down":
                self.io.mouseDown(button="left")
                self.drag_held = True
            elif kind == "mouse_up":
                if self.drag_held:
                    self.io.mouseUp(button="left")
                    self.drag_held = False
            elif kind == "secondary_scroll_delta":
                self.scroll(data["dx"], data["dy"], self.scroll_pixels,
                            self.cfg["scroll_step_pixels"])
            elif kind == "two_hand_pan_delta":
                self.scroll(data["dx"], data["dy"], self.pan_pixels,
                            self.cfg["two_hand_pan_step_pixels"])
            elif kind == "zoom_step":
                self.io.hotkey("ctrl", "=" if data["direction"] > 0 else "-")
            elif kind in ("interaction_cancelled", "two_hand_end", "tracking_paused"):
                self.scroll_pixels = [0., 0.]
                self.pan_pixels = [0., 0.]
            if kind not in ("pointer_screen", "pointer_delta", "drag_delta", "pointer_reanchor", "secondary_scroll_delta", "two_hand_pan_delta"):
                self.log(kind, **data)

    def emergency_release(self):
        # MouseUp itself checks FAILSAFE; temporarily bypass it during cleanup.
        previous = self.io.FAILSAFE
        try:
            self.io.FAILSAFE = False
            if self.drag_held:
                self.io.mouseUp(button="left")
            self.io.keyUp("ctrl")
        finally:
            self.drag_held = False
            self.io.FAILSAFE = previous


    def close(self):
        try:
            self.emergency_release()
        finally:
            close = getattr(self.io, 'close', None)
            if close is not None:
                close()


# Backwards-compatible import name for existing integrations/tests.
LinuxX11Adapter = DesktopAdapter


def label(result, i):
    try:
        return result.handedness[i][0].category_name
    except (AttributeError, IndexError, TypeError):
        return "Unknown"


def draw(frame, text, y, color=(255,255,255), scale=0.53):
    cv2.putText(frame, text, (15,y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def handle_key(key, engine, adapter, cfg, now):
    if key in (ord("q"), 27):
        return False
    if key == 32:
        adapter.perform(engine.keyboard_toggle(now))
    elif key == ord("x"):
        adapter.perform(engine.reset())
    elif key == ord("s"):
        save_config(cfg)
        adapter.log("config_saved")
    elif key == ord("r"):
        try:
            new = load_config()
        except (ValueError, OSError) as exc:
            print(f"Profile reload rejected: {exc}")
            return True
        if any(new[k] != cfg[k] for k in ("camera_index", "camera_device", "mirror_camera", "capture_width", "capture_height", "model_path")):
            print("Camera/model edits require restart")
        for k in ("camera_index", "camera_device", "mirror_camera", "capture_width", "capture_height", "model_path"):
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
        if cfg.get("calibration"):
            print("Calibrated reach is active. Open Setup to recalibrate.")
            return True
        region = cfg["camera_active_region"]
        cx, cy = (region[0]+region[2])/2, (region[1]+region[3])/2
        half_w = max(0.15, (region[2]-region[0])/2 - 0.025)
        half_h = max(0.15, (region[3]-region[1])/2 - 0.015)
        cfg["camera_active_region"] = [round(clamp(cx-half_w,0,1),3), round(clamp(cy-half_h,0,1),3), round(clamp(cx+half_w,0,1),3), round(clamp(cy+half_h,0,1),3)]
        adapter.reanchor()
        adapter.log("active_region_changed", bounds=cfg["camera_active_region"])
    elif key == ord("="):
        # Larger active region -> less sensitive hand movement.
        if cfg.get("calibration"):
            print("Calibrated reach is active. Open Setup to recalibrate.")
            return True
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
    global cv2, mp, pg, PROFILE
    parser = argparse.ArgumentParser(description="Gesture Control Pi: setup, profiles and desktop control")
    parser.add_argument("--setup", action="store_true", help="Open profile/device setup and calibration")
    parser.add_argument("--desktop", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", help="Use a named profile")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--check-config", action="store_true", help="Validate profile without camera or display")
    args = parser.parse_args()
    if args.list_profiles:
        print("\n".join(STORE.names()) or "Default (not yet saved)")
        return
    PROFILE = args.profile or STORE.active()
    cfg = load_config()
    if args.check_config:
        print(f"Profile {PROFILE}: configuration valid")
        return
    require_desktop()
    backend = session_backend()
    if backend == 'uinput':
        os.environ['QT_QPA_PLATFORM'] = 'xcb'
    # Keep two running instances from fighting over camera or desktop input.
    import fcntl
    lock_path = state_home() / "controller.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError("Gesture Control is already running. Close its preview or stop that process first.") from exc
    import cv2 as cv_module
    import mediapipe as mp_module
    cv2, mp = cv_module, mp_module
    # PyAutoGUI must never be imported for Wayland input.
    if args.setup or not STORE.path(PROFILE).exists():
        from setup_ui import setup
        from calibration_ui import run_calibration
        result = setup(STORE, PROFILE)
        if result is None:
            return
        PROFILE, cfg, calibrate = result
        if calibrate:
            cfg = run_calibration(cfg)
            if cfg is None:
                print("Setup cancelled. Existing profile was preserved.")
                return
        STORE.save(PROFILE, cfg)
    model = ROOT / cfg["model_path"]
    if not model.is_file():
        raise FileNotFoundError(f"Missing model: {model}. Run bash install_pi.sh to repair dependencies.")
    if cfg.get("microphone_source"):
        try:
            select_microphone(cfg["microphone_source"])
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"Microphone unavailable: {exc}. Gestures remain available.")
    opts = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2)
    engine = GestureEngine(cfg)
    driver = create_driver(backend)
    adapter = DesktopAdapter(cfg, driver=driver)
    adapter.engine = engine
    print(f"Desktop input: {backend}")
    if backend == 'uinput':
        print("Wayland: stop with Q/Escape in preview, Ctrl+C, or bash stop_pi.sh. Mouse-corner failsafe is X11-only.")
    try:
        cap = Camera(cfg)
    except BaseException:
        adapter.close()
        raise
    first_frame = None
    try:
        while first_frame is None:
            first_frame = cap.read()
            time.sleep(.01)
    except BaseException:
        try:
            adapter.close()
        finally:
            cap.close()
        raise
    print(f"Camera ready: {first_frame.shape}; pinky pinch to select owner")
    print("Q quit | SPACE toggle | X reset | S save | R reload | T telemetry")
    print("M screen/relative mode | - faster / = slower screen mapping")
    def stop_signal(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
    started = time.monotonic()
    prev_ts = -1
    last_sample = -1e6
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(opts) as tracker:
            while True:
                frame = cap.read()
                if frame is None:
                    time.sleep(.01)
                    continue
                frame = cv2.resize(frame, (cfg["capture_width"], cfg["capture_height"]))
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
                if not cfg.get("calibration"):
                    cv2.rectangle(frame, (int(left*w), int(top*h)),
                                  (int(right*w), int(bottom*h)), (235, 165, 70), 2)
                    for tx, ty in ((left, top), (right, top), (left, bottom), (right, bottom)):
                        cv2.circle(frame, (int(tx*w), int(ty*h)), 6, (235, 165, 70), -1)
                if cfg.get("calibration"):
                    points = [(int(x*w), int(y*h)) for x,y in cfg["calibration"]["corners"]]
                    for i, point in enumerate(points):
                        cv2.line(frame, point, points[(i+1)%4], (110,230,160), 3)
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
                draw(frame, f"{PROFILE} | {cfg['pointer_mode'].upper()} | {'CALIBRATED' if cfg.get('calibration') else '- / = reach'} | {'PAUSED - return hand' if engine.owner_paused else 'TRACKING'}", h-96, (240,240,240), 0.47)
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
                if cfg.get("show_preview", True) and cv2.getWindowProperty("Gesture Mouse Pi - Touchscreen Mapping", cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key != 255 and not handle_key(key, engine, adapter, cfg, now):
                    break
    except KeyboardInterrupt:
        print("Stopping controller")
    except adapter.io.FailSafeException:
        print("PyAutoGUI failsafe triggered (top-left corner)")
    finally:
        try:
            adapter.perform(engine.reset())
        finally:
            try:
                adapter.close()
            finally:
                cap.close()
                cv2.destroyAllWindows()
        print("Stopped. Profile:", STORE.path(PROFILE))
        print("Telemetry:", LOG_PATH)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Gesture Control: {exc}", file=sys.stderr)
        if "--desktop" in sys.argv and os.environ.get("DISPLAY"):
            try:
                import tkinter as tk
                from tkinter import messagebox
                dialog = tk.Tk()
                dialog.withdraw()
                messagebox.showerror("Gesture Control needs attention", str(exc), parent=dialog)
                dialog.destroy()
            except Exception:
                pass  # Preserve the original error if the desktop itself failed.
        sys.exit(1)
