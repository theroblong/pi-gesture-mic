import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture_engine import GestureEngine, HandAssociator

CONFIG = json.loads((Path(__file__).resolve().parents[1]/"gesture_config.json").read_text())


def hand(x, y, finger=None):
    # Synthetic hand with wide-open fingertips and one thumb+finger pinch.
    pts = [(x, y)] * 21
    pts[0] = (x,y)
    pts[5] = (x+0.06,y-0.05)
    pts[9] = (x+0.09,y-0.05)
    pts[17] = (x+0.16,y-0.05)
    pts[4] = (x+0.02,y-0.14)
    pts[8] = (x+0.13,y-0.14)
    pts[12] = (x+0.14,y-0.23)
    pts[16] = (x+0.15,y-0.30)
    pts[20] = (x+0.16,y-0.38)
    if finger:
        i = {"INDEX":8,"MIDDLE":12,"RING":16,"PINKY":20}[finger]
        pts[i] = (x+0.025,y-0.14)
    return pts


def names(events):
    return [e[0] for e in events]


class TestGestureEngine(unittest.TestCase):
    def setUp(self):
        self.cfg = copy.deepcopy(CONFIG)
        self.cfg["pinch_confirmation_ms"] = 20
        self.cfg["pinch_release_ms"] = 20
        self.cfg["toggle_cooldown_ms"] = 0
        self.cfg["pointer_mode"] = "relative"
        self.engine = GestureEngine(self.cfg)
        self.t = 0.0

    def step(self, specs):
        self.t += 0.05
        obs = [(hand(*v), k) for k, v in specs]
        events, visible = self.engine.update(obs, self.t)
        return events, visible

    def activate(self, side="Left"):
        base = 0.2 if side == "Left" else 0.60
        self.step([(side, (base, 0.5, None))])
        self.step([(side, (base, 0.5, "PINKY"))])
        events, _ = self.step([(side, (base, 0.5, "PINKY"))])
        self.assertIn("control_on", names(events))
        return self.engine.owner_id

    def test_owner_pinky_selects_hand_and_other_cannot_disable(self):
        self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,None))])
        self.step([("Left", (0.2,0.5,"PINKY")), ("Right", (0.6,0.5,None))])
        events,_ = self.step([("Left", (0.2,0.5,"PINKY")), ("Right", (0.6,0.5,None))])
        owner = self.engine.owner_id
        self.assertIn("control_on", names(events))
        self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,"PINKY"))])
        self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,"PINKY"))])
        self.assertEqual(owner, self.engine.owner_id)
        self.assertTrue(self.engine.enabled)
        self.step([("Left", (0.2,0.5,"PINKY")), ("Right", (0.6,0.5,None))])
        events,_ = self.step([("Left", (0.2,0.5,"PINKY")), ("Right", (0.6,0.5,None))])
        self.assertIn("control_off", names(events))
        self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,None))])
        self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,"PINKY"))])
        events,_ = self.step([("Left", (0.2,0.5,None)), ("Right", (0.6,0.5,"PINKY"))])
        self.assertIn("control_on", names(events))
        self.assertNotEqual(owner, self.engine.owner_id)

    def test_screen_pointer_uses_wrist_and_not_pinching_finger(self):
        self.cfg["pointer_mode"] = "screen"
        self.activate()
        self.step([("Left", (0.2,0.5,None))])
        self.step([("Left", (0.22,0.5,None))])
        events, _ = self.step([("Left", (0.25,0.5,None))])
        self.assertIn("pointer_screen", names(events))
        # Pinching changes the fingertip positions; the pointer should freeze.
        self.step([("Left", (0.25,0.5,"INDEX"))])
        events, _ = self.step([("Left", (0.25,0.5,"INDEX"))])
        self.assertNotIn("pointer_screen", names(events))

    def test_relative_reanchor_after_trackpad(self):
        self.activate()
        self.step([("Left", (0.2,0.5,None))])
        events,_ = self.step([("Left", (0.2,0.5,None))])
        self.assertNotIn("pointer_delta", names(events))
        events,_ = self.step([("Left", (0.22,0.5,None))])
        self.assertIn("pointer_delta", names(events))
        self.engine.disable([], "test")
        self.step([("Left", (0.22,0.5,None))])
        self.step([("Left", (0.22,0.5,"PINKY"))])
        self.step([("Left", (0.22,0.5,"PINKY"))])
        self.step([("Left", (0.22,0.5,None))])
        events,_ = self.step([("Left", (0.22,0.5,None))])
        self.assertNotIn("pointer_delta", names(events))

    def test_quick_index_pinch_clicks_not_drags(self):
        self.activate()
        self.step([("Left",(0.2,0.5,None))])
        self.step([("Left",(0.2,0.5,"INDEX"))])
        self.step([("Left",(0.2,0.5,"INDEX"))])
        self.step([("Left",(0.2,0.5,None))])
        events,_ = self.step([("Left",(0.2,0.5,None))])
        self.assertIn(("mouse_click", {"button":"left"}), events)

    def test_hold_drags_and_releases(self):
        self.activate()
        self.step([("Left",(0.2,0.5,None))])
        self.step([("Left",(0.2,0.5,"INDEX"))])
        self.step([("Left",(0.2,0.5,"INDEX"))])
        all_events = []
        for _ in range(10):
            events,_ = self.step([("Left",(0.2,0.5,"INDEX"))])
            all_events += events
        self.assertIn("mouse_down", names(all_events))
        self.step([("Left",(0.2,0.5,None))])
        events,_ = self.step([("Left",(0.2,0.5,None))])
        self.assertIn("mouse_up", names(events))
        self.assertNotIn("mouse_click", names(events))

    def test_secondary_scrolling_and_dual_zoom(self):
        self.step([("Left",(0.2,0.5,None)), ("Right",(0.6,0.5,None))])
        self.step([("Left",(0.2,0.5,"PINKY")), ("Right",(0.6,0.5,None))])
        self.step([("Left",(0.2,0.5,"PINKY")), ("Right",(0.6,0.5,None))])
        self.step([("Left",(0.2,0.5,None)), ("Right",(0.6,0.5,None))])
        self.step([("Left",(0.2,0.5,None)), ("Right",(0.6,0.5,"INDEX"))])
        self.step([("Left",(0.2,0.5,None)), ("Right",(0.6,0.5,"INDEX"))])
        events,_ = self.step([("Left",(0.2,0.5,None)), ("Right",(0.6,0.55,"INDEX"))])
        self.assertIn("secondary_scroll_delta", names(events))
        self.step([("Left",(0.2,0.5,"INDEX")), ("Right",(0.6,0.55,"INDEX"))])
        events,_ = self.step([("Left",(0.2,0.5,"INDEX")), ("Right",(0.6,0.55,"INDEX"))])
        self.assertIn("two_hand_start", names(events))
        events,_ = self.step([("Left",(0.10,0.5,"INDEX")), ("Right",(0.72,0.55,"INDEX"))])
        self.assertIn("zoom_step", names(events))
        self.assertNotIn("mouse_down", names(events))

    def test_identity_stable_when_detection_order_changes(self):
        obs1 = [(hand(0.2,0.5),"Left"),(hand(0.65,0.5),"Right")]
        v1 = self.engine.associator.update(obs1, 0.0)
        left_id = next(k for k,t in v1.items() if t.handedness == "Left")
        v2 = self.engine.associator.update(obs1[::-1], 0.05)
        self.assertEqual(left_id, next(k for k,t in v2.items() if t.handedness == "Left"))

    def test_owner_loss_pauses_but_stays_enabled(self):
        self.activate()
        for _ in range(10):
            events,_ = self.step([])
        self.assertTrue(self.engine.enabled)
        self.assertTrue(self.engine.owner_paused)
        self.assertIsNotNone(self.engine.owner_id)
        # Same-hand reappearance should resume rather than require another toggle.
        events,_ = self.step([("Left", (0.2,0.5,None))])
        self.assertIn("tracking_resumed", names(events))
        self.assertTrue(self.engine.enabled)


if __name__ == "__main__":
    unittest.main()
