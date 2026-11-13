"""Framework-independent two-hand gesture logic for Gesture Mouse v6.

No camera, OS mouse, or MediaPipe imports. Operations are returned as simple
(name, payload) events, so they can be tested and later routed to a browser UI.
"""
import itertools
import math
from dataclasses import dataclass, field

TIPS = {"INDEX": 8, "MIDDLE": 12, "RING": 16, "PINKY": 20}


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def clamp(value, low, high):
    return max(low, min(high, value))


def palm_center(hand):
    indexes = (0, 5, 9, 17)
    return tuple(sum(hand[i][axis] for i in indexes) / 4 for axis in (0, 1))


@dataclass
class Track:
    id: int
    wrist: tuple
    last_seen: float
    handedness: str = "Unknown"
    hand: list = field(default_factory=list)


class HandAssociator:
    """Keep identities stable through frame reordering and brief occlusions."""
    def __init__(self, timeout_ms=350, max_distance=0.32):
        self.tracks = {}
        self.next_id = 1
        self.timeout = timeout_ms / 1000
        self.max_distance = max_distance

    def update(self, observations, now):
        # observations: [(21 (x,y) landmarks, label), ...]
        self.tracks = {k: v for k, v in self.tracks.items()
                       if now - v.last_seen < self.timeout}
        ids = list(self.tracks)
        pairs = []
        for i, (hand, label) in enumerate(observations):
            for id_ in ids:
                track = self.tracks[id_]
                d = distance(hand[0], track.wrist)
                if d <= self.max_distance:
                    # Preserve spatial continuity first; label is a tie breaker.
                    cost = d + (0.06 if (label != track.handedness and
                                          label != "Unknown" and
                                          track.handedness != "Unknown") else 0)
                    pairs.append((cost, i, id_))
        used_obs, used_tracks = set(), set()
        matches = {}
        for _, i, id_ in sorted(pairs):
            if i not in used_obs and id_ not in used_tracks:
                matches[i] = id_
                used_obs.add(i)
                used_tracks.add(id_)
        visible = {}
        for i, (hand, label) in enumerate(observations):
            if i in matches:
                track = self.tracks[matches[i]]
                track.wrist, track.hand, track.last_seen = hand[0], hand, now
                if label != "Unknown":
                    track.handedness = label
            else:
                track = Track(self.next_id, hand[0], now, label, hand)
                self.tracks[self.next_id] = track
                self.next_id += 1
            visible[track.id] = track
        return visible


class PinchState:
    """Independent recognizer per hand; hysteresis + debounce + rearming."""
    def __init__(self):
        self.active = None
        self.candidate = None
        self.candidate_since = 0
        self.release_since = None
        self.armed = True
        self.ratios = {}

    def reset(self, require_open=True):
        self.active = None
        self.candidate = None
        self.release_since = None
        self.armed = not require_open

    def update(self, hand, now, config):
        width = max(distance(hand[5], hand[17]), 0.001)
        self.ratios = {name: distance(hand[4], hand[tip]) / width
                       for name, tip in TIPS.items()}
        events = []
        start = config["pinch_start_ratio"]
        end = config["pinch_end_ratio"]
        if self.active is not None:
            if self.ratios[self.active] >= end:
                if self.release_since is None:
                    self.release_since = now
                if (now - self.release_since) * 1000 >= config["pinch_release_ms"]:
                    events.append(("end", self.active))
                    self.active = None
                    self.candidate = None
                    self.release_since = None
                    self.armed = True
            else:
                self.release_since = None
            return events
        closest = min(self.ratios, key=self.ratios.get)
        closest_ratio = self.ratios[closest]
        if closest_ratio >= end:
            self.armed = True
        if self.armed and closest_ratio <= start:
            if self.candidate != closest:
                self.candidate = closest
                self.candidate_since = now
            if (now - self.candidate_since) * 1000 >= config["pinch_confirmation_ms"]:
                self.active = closest
                self.armed = False
                self.candidate = None
                self.release_since = None
                events.append(("start", closest))
        else:
            self.candidate = None
        return events


class GestureEngine:
    """Deterministic state machine. Emits actions; never accesses the OS."""
    def __init__(self, config):
        self.cfg = config
        self.associator = HandAssociator(config["hand_loss_ms"],
                                         config["track_match_max_distance"])
        self.states = {}
        self.enabled = False
        self.owner_id = None
        self.last_toggle = -1e6
        self.last_wrist = None
        self.pointer_locked = False
        self.owner_pinch_start = None
        self.owner_pinch_dragging = False
        self.owner_pinch_suppressed = False
        self.drag_palm_anchor = None
        self.secondary_scroll_anchor = None
        self.zoom_anchor = None
        self.pan_anchor = None
        self.dual_mode = False
        self.owner_click_target = None
        self.last_visible = {}
        self.owner_handedness = None
        self.owner_wrist = None
        self.owner_paused = False
        self.pointing_offset = None  # constant wrist->fingertip offset sampled at activation
        self.reacquire_open = False

    def emit(self, out, kind, **kwargs):
        out.append((kind, kwargs))

    def cancel_interaction(self, out, reason):
        if self.owner_pinch_dragging:
            self.emit(out, "mouse_up", button="left", reason=reason)
        self.owner_pinch_dragging = False
        self.owner_pinch_start = None
        self.owner_pinch_suppressed = False
        self.drag_palm_anchor = None
        self.pointer_locked = False
        self.last_wrist = None
        self.secondary_scroll_anchor = None
        self.zoom_anchor = None
        self.pan_anchor = None
        self.dual_mode = False
        self.owner_click_target = None
        self.emit(out, "interaction_cancelled", reason=reason)

    def disable(self, out, reason):
        self.cancel_interaction(out, reason)
        self.enabled = False
        self.emit(out, "control_off", former_owner=self.owner_id)
        self.owner_id = None
        self.owner_handedness = None
        self.owner_wrist = None
        self.owner_paused = False
        self.pointing_offset = None
        # Both hands must open their pinches before initiating a new toggle.
        for state in self.states.values():
            state.reset(require_open=True)

    def enable(self, id_, out):
        self.enabled = True
        self.owner_id = id_
        track = self.last_visible.get(id_)
        self.owner_handedness = track.handedness if track else None
        self.owner_wrist = track.wrist if track else None
        self.owner_paused = False
        self.pointing_offset = None
        self.last_wrist = None  # next visible wrist is a fresh relative anchor
        self.pointer_locked = False
        self.emit(out, "control_on", owner=id_)
        # All held gestures must open before another action can fire.
        for state in self.states.values():
            state.reset(require_open=True)

    def keyboard_toggle(self, now):
        out = []
        if self.enabled:
            self.disable(out, "keyboard")
        else:
            # Space resumes only if previous owner is visible. Otherwise pinky
            # pinch must pick the hand, avoiding ambiguous ownership.
            if self.owner_id is None and len(self.last_visible) == 1:
                id_ = next(iter(self.last_visible))
                self.enable(id_, out)
            else:
                self.emit(out, "owner_selection_required")
        self.last_toggle = now
        return out

    def reset(self):
        out = []
        self.disable(out, "manual_reset")
        return out

    def _pointer(self, out, hand, allow_movement):
        wrist = hand[self.cfg["pointer_landmark"]]
        if self.pointing_offset is None:
            # A stable proxy for the fingertip: wrist location plus the initial
            # wrist-to-index vector. We intentionally DO NOT recompute this
            # vector during pinching (finger flexion would move the target).
            self.pointing_offset = (hand[8][0] - wrist[0], hand[8][1] - wrist[1])
        if self.last_wrist is None:
            self.last_wrist = wrist
            self.emit(out, "pointer_reanchor")
            return
        dx = wrist[0] - self.last_wrist[0]
        dy = wrist[1] - self.last_wrist[1]
        self.last_wrist = wrist
        if allow_movement and (abs(dx) > 0.00001 or abs(dy) > 0.00001):
            if self.cfg.get("pointer_mode", "screen") == "screen":
                self.emit(out, "pointer_screen", x=wrist[0] + self.pointing_offset[0],
                          y=wrist[1] + self.pointing_offset[1], dx=dx, dy=dy)
            else:
                self.emit(out, "pointer_delta", dx=dx, dy=dy)

    def update(self, observations, now):
        out = []
        visible = self.associator.update(observations, now)
        self.last_visible = visible
        current_events = {}
        for id_, track in visible.items():
            state = self.states.setdefault(id_, PinchState())
            current_events[id_] = state.update(track.hand, now, self.cfg)
        for id_, state in list(self.states.items()):
            if id_ not in self.associator.tracks:
                del self.states[id_]

        if self.enabled and self.owner_id not in visible:
            # Tracking loss pauses control instead of switching it off. Always
            # release a held drag to avoid an invisible pressed mouse button.
            if not self.owner_paused:
                self.cancel_interaction(out, "owner_out_of_frame")
                self.emit(out, "tracking_paused")
                self.owner_paused = True
            # A track can expire while out of view. Reacquire only a uniquely
            # visible hand with the same known handedness and no rival track.
            # This avoids automatically transferring ownership to the other hand.
            if self.owner_id not in self.associator.tracks:
                candidates = [id_ for id_, t in visible.items()
                              if self.owner_handedness not in (None, "Unknown")
                              and t.handedness == self.owner_handedness]
                if len(candidates) == 1:
                    self.owner_id = candidates[0]
                    self.states[self.owner_id].reset(require_open=True)
                    self.pointing_offset = None
                    self.last_wrist = None
                    self.owner_paused = False
                    self.emit(out, "tracking_resumed", owner=self.owner_id)
                else:
                    return out, visible
            else:
                return out, visible
        if self.enabled and self.owner_paused:
            self.owner_paused = False
            self.pointing_offset = None
            self.last_wrist = None
            self.states[self.owner_id].reset(require_open=True)
            self.emit(out, "tracking_resumed", owner=self.owner_id)

        # Pinky pinch chooses the hand *only* when disabled. When enabled,
        # only the current owner can turn control off.
        for id_, events in current_events.items():
            for event, finger in events:
                if event != "start" or finger != "PINKY":
                    continue
                if (now - self.last_toggle) * 1000 < self.cfg["toggle_cooldown_ms"]:
                    continue
                if not self.enabled:
                    self.last_toggle = now
                    self.enable(id_, out)
                    return out, visible
                if id_ == self.owner_id:
                    self.last_toggle = now
                    self.disable(out, "owner_pinky")
                    return out, visible

        if not self.enabled:
            return out, visible
        owner = visible.get(self.owner_id)
        if owner is None:
            return out, visible
        owner_state = self.states[self.owner_id]
        secondaries = [(id_, track) for id_, track in visible.items()
                       if id_ != self.owner_id]
        secondary_id, secondary = secondaries[0] if secondaries else (None, None)
        secondary_state = self.states[secondary_id] if secondary_id is not None else None
        owner_index = owner_state.active == "INDEX"
        secondary_index = secondary_state is not None and secondary_state.active == "INDEX"
        two_hand = owner_index and secondary_index

        # The owner controls the pointer by wrist movement in *relative* mode.
        # Re-establish the anchor even if movement is temporarily locked.
        early_pinch = owner_state.active is not None or owner_state.candidate is not None or (
            bool(owner_state.ratios) and min(owner_state.ratios.values()) < self.cfg["pinch_prelock_ratio"])
        blocked = early_pinch or secondary_index
        self._pointer(out, owner.hand,
                      not blocked and not self.owner_pinch_dragging)
        self.pointer_locked = blocked

        for event, finger in current_events.get(self.owner_id, []):
            if finger == "PINKY":
                continue
            action = self.cfg["actions"][finger]
            if event == "start":
                if finger == "INDEX" and action == "left_click_drag":
                    self.owner_pinch_start = now
                    self.owner_pinch_dragging = False
                    self.owner_pinch_suppressed = secondary_index
                    self.owner_click_target = True
                    self.emit(out, "pinch_start", owner=self.owner_id, finger=finger)
                elif action == "right_click":
                    self.emit(out, "mouse_click", button="right")
                elif action == "double_click":
                    self.emit(out, "mouse_double_click", interval_ms=self.cfg["double_click_interval_ms"])
            elif event == "end" and finger == "INDEX":
                if self.owner_pinch_dragging:
                    self.emit(out, "mouse_up", button="left", reason="pinch_release")
                elif (self.owner_pinch_start is not None and
                      not self.owner_pinch_suppressed and not self.dual_mode):
                    self.emit(out, "mouse_click", button="left")
                self.owner_pinch_start = None
                self.owner_pinch_dragging = False
                self.owner_pinch_suppressed = False
                self.drag_palm_anchor = None
                self.owner_click_target = None

        if secondary_index:
            if self.secondary_scroll_anchor is None:
                self.secondary_scroll_anchor = palm_center(secondary.hand)
            if owner_index:
                self.owner_pinch_suppressed = True
                if self.owner_pinch_dragging:
                    self.emit(out, "mouse_up", button="left", reason="two_hand_mode")
                    self.owner_pinch_dragging = False
                if not self.dual_mode:
                    self.dual_mode = True
                    self.zoom_anchor = distance(palm_center(owner.hand), palm_center(secondary.hand))
                    self.pan_anchor = tuple((a+b)/2 for a,b in zip(palm_center(owner.hand), palm_center(secondary.hand)))
                    self.emit(out, "two_hand_start")
                else:
                    separation = distance(palm_center(owner.hand), palm_center(secondary.hand))
                    step = self.cfg["zoom_step_ratio"]
                    if self.zoom_anchor is not None and self.zoom_anchor > 0.005:
                        ratio = (separation - self.zoom_anchor) / self.zoom_anchor
                        if abs(ratio) >= step:
                            direction = 1 if ratio > 0 else -1
                            self.emit(out, "zoom_step", direction=direction)
                            self.zoom_anchor *= (1 + step * direction)
                    if self.cfg.get("two_hand_pan", True):
                        centroid = tuple((a+b)/2 for a,b in zip(palm_center(owner.hand), palm_center(secondary.hand)))
                        if self.pan_anchor is not None:
                            dx, dy = centroid[0] - self.pan_anchor[0], centroid[1] - self.pan_anchor[1]
                            self.emit(out, "two_hand_pan_delta", dx=dx, dy=dy)
                        self.pan_anchor = centroid
            elif not self.dual_mode:
                palm = palm_center(secondary.hand)
                anchor = self.secondary_scroll_anchor
                self.emit(out, "secondary_scroll_delta", dx=palm[0]-anchor[0], dy=palm[1]-anchor[1])
                self.secondary_scroll_anchor = palm
        else:
            self.secondary_scroll_anchor = None

        if self.dual_mode and not two_hand:
            self.emit(out, "two_hand_end")
            self.dual_mode = False
            self.zoom_anchor = None
            self.pan_anchor = None
            self.owner_pinch_suppressed = True
            # Do not initiate a single-hand drag until owner fully releases.

        if owner_index and self.owner_pinch_start is not None and not secondary_index:
            if (not self.owner_pinch_dragging and not self.owner_pinch_suppressed and
                    owner_state.release_since is None and
                    (now - self.owner_pinch_start) * 1000 >= self.cfg["drag_hold_ms"]):
                self.emit(out, "mouse_down", button="left")
                self.owner_pinch_dragging = True
                self.drag_palm_anchor = palm_center(owner.hand)
                self.emit(out, "drag_start")
            if self.owner_pinch_dragging:
                palm = palm_center(owner.hand)
                anchor = self.drag_palm_anchor
                self.emit(out, "drag_delta", dx=palm[0]-anchor[0], dy=palm[1]-anchor[1])
                self.drag_palm_anchor = palm

        return out, visible
