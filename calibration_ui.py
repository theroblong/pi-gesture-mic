"""Full-screen guided calibration. All practice input is kept inside this window."""
import copy
import math
import time
from datetime import datetime, timezone
from calibration import TARGETS, StableSamples, GestureHold, homography, transform, pinch_thresholds
from gesture_engine import GestureEngine, distance, TIPS
from devices import Camera


class Wizard:
    def __init__(self, cfg):
        self.source_cfg = copy.deepcopy(cfg)
        self.cfg = copy.deepcopy(cfg)
        self.cfg['calibration'] = None
        self.cfg['pointer_landmark'] = 0
        self.cfg['pointer_mode'] = 'screen'
        self.engine = GestureEngine(self.cfg)
        self.stage = 0
        self.samples = StableSamples()
        self.corners, self.opened, self.closed = [], [], []
        self.message = 'Show ONE open hand near your comfortable center. Hold still for 2 seconds.'
        self.matrix = None
        self.hand = None
        self.cursor = (.5, .5)
        self.errors = []
        self.validation = 0
        self.dragging = False
        self.drag_origin = None
        self.drag_previous = None
        self.done = False
        self.cancelled = False
        self.now = self.stage_since = 0.
        self.capture_hold = GestureHold()
        self.command_hold = GestureHold(jitter=.06)
        self.commands_armed = False
        self.save_armed = False
        self.selection_point = None
        self.hold_progress = 0.
        self.hold_label = 'Hold still to begin'
        self.targets = ((.5,.5), (.25,.25), (.75,.25), (.75,.75), (.25,.75))

    def advance(self):
        self.stage += 1
        self.samples.clear()
        self.capture_hold.clear()
        self.command_hold.clear()
        self.stage_since = self.now
        self.hold_progress = 0.
        self.message = ('Open your hand, move the blue dot into the ring, then make a quick index pinch.'
                        if self.stage == 13 else 'Follow the pose shown. Hold steady until the countdown completes.')

    @staticmethod
    def ratios(track):
        width = max(distance(track.hand[5], track.hand[17]), .001)
        return {name: distance(track.hand[4], track.hand[tip])/width for name,tip in TIPS.items()}

    def command(self, track):
        """Deliberate gestures work before thresholds are calibrated; no OS events."""
        if track is None:
            self.command_hold.clear()
            return False
        ratios = self.ratios(track)
        if min(ratios.values()) >= .8:
            self.commands_armed = True
            if self.stage == 15:
                self.save_armed = True
        closest = min(ratios, key=ratios.get)
        distinct = all(value-ratios[closest] >= .15 for name,value in ratios.items() if name != closest)
        action = None
        if self.commands_armed and distinct and ratios[closest] <= .45:
            if closest == 'MIDDLE':
                action = 'restart'
            elif closest == 'RING':
                action = 'cancel'
            elif closest == 'INDEX' and self.stage == 15 and self.save_armed:
                action = 'save'
        if action is None:
            self.command_hold.clear()
            return False
        duration = {'restart':2., 'cancel':3., 'save':1.5}[action]
        ready = self.command_hold.update((track.id,action), track.hand[0], self.now, duration)
        self.hold_progress = self.command_hold.progress
        self.hold_label = f'Hold to {action}'
        self.message = f'Hold {closest.lower()} pinch to {action}. Open your hand to stop the countdown.'
        self.capture_hold.clear()
        self.samples.clear()
        self.dragging = False
        self.drag_previous = None
        self.engine.cancel_interaction([], 'wizard_command')
        if ready:
            if action == 'restart':
                self.__init__(self.source_cfg)
            elif action == 'cancel':
                self.cancelled = True
            else:
                self.done = True
        return True

    def capture_pose(self, owner, ratios):
        """Check pose and new target before starting a dwell, not after capture."""
        point = owner.hand[0]
        opened = min(ratios.values()) >= .8
        if self.stage in (8,10,12):
            baseline = sum(self.opened)/len(self.opened) if self.opened else 1.
            valid = (ratios['INDEX'] <= min(.65, baseline*.65) and
                     baseline-ratios['INDEX'] >= .25 and
                     ratios['INDEX'] == min(ratios.values()))
            return valid, 'Touch index fingertip to thumb and hold your wrist still.'
        if not opened:
            return False, 'Open your fingers and keep your wrist visible.'
        # Avoid recording the same stationary wrist at successive corner prompts.
        if self.stage == 2 and self.selection_point is not None:
            valid = point[0] < self.selection_point[0]-.05 and point[1] < self.selection_point[1]-.05
            return valid, 'Move your open hand up and left from your starting position.'
        if self.stage == 3:
            return point[0] > self.corners[-1][0]+.12, 'Move right to the next corner, then hold still.'
        if self.stage == 4:
            return point[1] > self.corners[-1][1]+.12, 'Move down to the next corner, then hold still.'
        if self.stage == 5:
            return point[0] < self.corners[-1][0]-.12, 'Move left to the next corner, then hold still.'
        if self.stage == 6:
            valid = math.dist(transform(self.matrix, point, clip=False), (.5,.5)) <= .15
            return valid, 'Return your open hand to the comfortable center.'
        return True, 'Keep your open hand still.'

    def capture(self):
        point, ratios = self.samples.capture()
        if 2 <= self.stage <= 5:
            points = self.corners + [point]
            if self.stage == 5:
                self.matrix = homography(points)
            self.corners = points
        elif self.stage == 6:
            if math.dist(transform(self.matrix, point, clip=False), (.5,.5)) > .15:
                raise ValueError('Center is off. Hold a middle pinch to restart with a comfortable rectangular reach.')
            self.neutral = point
        elif self.stage in (7,9,11):
            self.opened.extend(ratios)
        else:
            closed = self.closed + ratios
            if self.stage == 12:
                self.cfg.update(pinch_thresholds(self.opened, closed))
                self.cfg['calibration'] = {
                    'version': 1, 'corners': self.corners, 'matrix': self.matrix,
                    'neutral': self.neutral, 'handedness': self.hand,
                    'mirror_camera': self.cfg['mirror_camera'],
                    'camera_device': self.cfg.get('camera_device'),
                    'created_at': datetime.now(timezone.utc).isoformat()}
                self.engine.cancel_interaction([], 'calibration_finished')
                for state in self.engine.states.values():
                    state.reset(require_open=True)
            self.closed = closed
        self.advance()

    def update(self, observations, now, key=None):
        self.now = now
        self.hold_progress = 0.
        self.hold_label = 'Hold the requested pose'
        events, visible = self.engine.update(observations, now)
        owner = visible.get(self.engine.owner_id)
        candidate = owner if self.stage >= 2 else (next(iter(visible.values())) if len(visible) == 1 else None)
        if self.command(candidate):
            return visible
        if self.stage in (0,1):
            if self.stage == 0 and key == 32 and visible:
                self.advance()
                self.message = 'Hold one open hand still, or use its thumb + pinky pinch.'
                return visible
            if self.stage == 1 and owner and owner.handedness in ('Left','Right'):
                self.hand = owner.handedness
                self.selection_point = owner.hand[0]
                self.advance()
                return visible
            valid = candidate is not None and candidate.handedness in ('Left','Right') and min(self.ratios(candidate).values()) >= .8
            ready = self.capture_hold.update((self.stage,candidate.id) if valid else None,
                                             candidate.hand[0] if valid else None, now)
            self.hold_progress = self.capture_hold.progress
            self.hold_label = 'Hold to choose this hand'
            if ready:
                self.engine.enable(candidate.id, [])
                self.hand = candidate.handedness
                self.selection_point = candidate.hand[0]
                self.stage = 1
                self.advance()
            elif not valid:
                self.message = 'Show only your controlling hand, fingers open, near your comfortable center.'
            return visible
        if self.stage == 15 and key in (10,13):
            self.done = True
            return visible
        if not owner or owner.handedness != self.hand or self.engine.owner_paused:
            self.samples.clear()
            self.capture_hold.clear()
            self.dragging = False
            self.drag_previous = None
            self.message = 'Return your controlling hand. If control is off, use its pinky pinch.'
            return visible
        ratios = self.ratios(owner)
        if 2 <= self.stage <= 12:
            # Keyboard capture remains available as an optional fallback.
            valid, hint = self.capture_pose(owner, ratios)
            sample_pose = valid or (self.stage not in (8,10,12) and min(ratios.values()) >= .8)
            if sample_pose:
                self.samples.add(owner.id, owner.hand[0], ratios['INDEX'], now)
            else:
                self.samples.clear()
            ready = self.capture_hold.update((self.stage,owner.id) if valid and now-self.stage_since >= .6 else None,
                                             owner.hand[0], now)
            self.hold_progress = self.capture_hold.progress
            self.hold_label = 'Hold still to capture'
            if not valid:
                self.message = hint
            elif self.hold_progress > 0:
                self.message = f'Capturing in {max(0., 2.*(1-self.hold_progress)):.1f}s. Keep this pose and wrist position.'
            if key == 32 or ready:
                try:
                    self.capture()
                except ValueError as exc:
                    self.message = str(exc)
                    self.capture_hold.clear()
                    self.samples.clear()
                    self.stage_since = now
        if self.stage in (13,14):
            # Same target lock and smoothing as runtime. No OS mouse events.
            state = self.engine.states[owner.id]
            blocked = state.active or state.candidate or min(state.ratios.values()) < self.cfg['pinch_prelock_ratio']
            if not blocked and not self.dragging:
                target = transform(self.matrix, owner.hand[0])
                alpha = self.cfg['cursor_smoothing']
                self.cursor = tuple(a+alpha*(b-a) for a,b in zip(self.cursor, target))
            for kind, data in events:
                if kind == 'mouse_down':
                    self.dragging = self.stage == 14 and math.dist(self.cursor, (.3,.5)) < .09
                    self.drag_previous = owner.hand[0] if self.dragging else None
                elif kind == 'drag_delta' and self.dragging:
                    # Calibrated drag uses mapped wrist displacement, like runtime.
                    before = transform(self.matrix, self.drag_previous)
                    after = transform(self.matrix, owner.hand[0])
                    self.cursor = tuple(max(0., min(1., c+b-a)) for c,a,b in zip(self.cursor, before, after))
                    self.drag_previous = owner.hand[0]
                elif kind == 'mouse_up':
                    if self.dragging and math.dist(self.cursor, (.7,.5)) < .09:
                        self.advance()
                        self.cfg['calibration']['validation'] = {
                            'click_errors': self.errors,
                            'mean_error': sum(self.errors)/len(self.errors),
                            'max_error': max(self.errors), 'drag_passed': True}
                        self.message = 'Calibration passed. Open your hand, then hold an INDEX pinch for 1.5 seconds to save.'
                    self.dragging = False
                    self.drag_previous = None
                elif kind == 'mouse_click' and data['button'] == 'left' and self.stage == 13:
                    error = math.dist(self.cursor, self.targets[self.validation])
                    if error <= .09:
                        self.errors.append(error)
                        self.validation += 1
                        self.message = f'Nice. {self.validation}/5 targets reached.'
                        if self.validation == 5:
                            self.advance()
                            self.message = 'Pinch and hold the left circle, move it to the right circle, then release.'
                    else:
                        self.message = f'Missed by {error*100:.0f}% of screen span. Aim at the ring and try again.'
        return visible

    def instructions(self):
        if self.stage == 0:
            return 'Camera position', 'Show ONE open hand at your comfortable center. Hold still for 2 seconds to begin.'
        if self.stage == 1:
            return 'Choose your controlling hand', 'Hold ONE open hand still for 2 seconds, or select it with a thumb + pinky pinch.'
        if 2 <= self.stage <= 5:
            corner = ('TOP LEFT','TOP RIGHT','BOTTOM RIGHT','BOTTOM LEFT')[self.stage-2]
            return f'Comfortable reach: {corner}', 'Move your OPEN hand toward the target. Hold still for the 2-second countdown.'
        if self.stage == 6:
            return 'Neutral position', 'Return your OPEN hand to the comfortable center. Hold still for 2 seconds.'
        if 7 <= self.stage <= 12:
            trial = (self.stage-7)//2+1
            return f'Pinch calibration {trial}/3', ('OPEN your fingers. Hold your wrist still until the countdown completes.' if self.stage % 2 else
                                                     'Touch INDEX fingertip to thumb. Hold the pinch and wrist still for 2 seconds.')
        if self.stage == 13:
            return f'Accuracy check {self.validation+1}/5', 'Move the blue dot into the target, then briefly pinch index + thumb to click.'
        if self.stage == 14:
            return 'Practice a drag', f'Hold an index pinch for {self.cfg["drag_hold_ms"]}ms on the left ring. Move right and release.'
        return 'Your profile is ready', f'Click accuracy: average {sum(self.errors)/len(self.errors)*100:.1f}% of screen span. Drag passed.'

    def render(self, frame, visible):
        import cv2
        import numpy as np
        canvas = np.zeros((720,1280,3), dtype=np.uint8)
        canvas[:] = (39,27,16)
        def text(value, x, y, size=.65, color=(240,235,225)):
            cv2.putText(canvas, value, (x,y), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)
        title, instruction = self.instructions()
        text('GESTURE CONTROL / PERSONAL SETUP', 36, 34, .55, (200,185,130))
        text(title, 36, 76, 1.05)
        text(instruction, 36, 110, .56)
        # Stage area has the same aspect-independent normalized mapping as runtime.
        x0,y0,aw,ah = 36,140,860,465
        cv2.rectangle(canvas,(x0,y0),(x0+aw,y0+ah),(75,63,48),1)
        targets = []
        if 2 <= self.stage <= 5:
            targets = [TARGETS[self.stage-2]]
        elif self.stage == 6:
            targets = [(.5,.5)]
        elif self.stage == 13:
            targets = [self.targets[self.validation]]
        elif self.stage == 14:
            targets = [(.3,.5),(.7,.5)]
        for target in targets:
            pt = (x0+int(target[0]*aw), y0+int(target[1]*ah))
            cv2.circle(canvas,pt,32,(160,220,110),3,cv2.LINE_AA)
            cv2.line(canvas,(pt[0]-10,pt[1]),(pt[0]+10,pt[1]),(160,220,110),1)
            cv2.line(canvas,(pt[0],pt[1]-10),(pt[0],pt[1]+10),(160,220,110),1)
        if self.stage in (13,14):
            cv2.circle(canvas,(x0+int(self.cursor[0]*aw), y0+int(self.cursor[1]*ah)),12,
                       (90,220,255) if self.dragging else (255,185,70),-1,cv2.LINE_AA)
        camera = frame.copy()
        h,w = camera.shape[:2]
        for track in visible.values():
            for x,y in track.hand:
                cv2.circle(camera,(int(x*w),int(y*h)),4,
                           (100,255,160) if track.id == self.engine.owner_id else (255,180,70),-1)
        if self.stage in (0,1,7,8,9,10,11,12):
            # A large preview during positioning and pinch measurement.
            camera = cv2.resize(camera,(640,360))
            canvas[190:550,146:786] = camera
        else:
            camera = cv2.resize(camera,(320,240))
            canvas[150:390,924:1244] = camera
        text(f'Hands visible: {len(visible)}',924,430,.55)
        text(f'Owner: {self.hand or "Choose hand"}',924,460,.55)
        text('Camera stays local.',924,520,.48)
        text('No desktop clicks',924,550,.48)
        text('during setup.',924,574,.48)
        # Wrap status instead of clipping recovery instructions.
        import textwrap
        for i,line in enumerate(textwrap.wrap(self.message, 110)):
            text(line,36,638+i*24,.56,(140,220,255))
        text(self.hold_label,924,490,.48,(140,220,255))
        cv2.rectangle(canvas,(36,610),(896,618),(75,63,48),-1)
        if self.hold_progress:
            cv2.rectangle(canvas,(36,610),(36+int(860*self.hold_progress),618),(160,220,110),-1)
        footer = ('Open hand, then hold INDEX pinch 1.5s to save' if self.stage == 15 else
                  'Hold MIDDLE pinch 2s: restart  |  Hold RING pinch 3s: cancel')
        text(footer,36,682,.48)
        text('Optional keys: SPACE capture  |  ENTER save at finish  |  R restart  |  ESC cancel',36,708,.45)
        cv2.rectangle(canvas,(924,660),(1244,671),(75,63,48),-1)
        cv2.rectangle(canvas,(924,660),(924+int(320*self.stage/15),671),(190,215,100),-1)
        return canvas


def run_calibration(cfg):
    import cv2
    import mediapipe as mp
    from pathlib import Path
    wizard = Wizard(cfg)
    model = Path(__file__).resolve().parent / cfg['model_path']
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2)
    camera = Camera(cfg)
    window = 'Gesture Control - Guided Setup'
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window,cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)
    previous = -1
    shown = False
    started = time.monotonic()
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
            while True:
                frame = camera.read()
                if frame is None:
                    time.sleep(.01)
                    continue
                frame = cv2.resize(frame,(cfg['capture_width'],cfg['capture_height']))
                timestamp = max(previous+1,int((time.monotonic()-started)*1000))
                previous = timestamp
                result = tracker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)),timestamp)
                observations = [([(p.x,p.y) for p in points], result.handedness[i][0].category_name)
                                for i,points in enumerate(result.hand_landmarks)]
                key = cv2.waitKey(1) & 0xff
                if key == 27 or (shown and cv2.getWindowProperty(window,cv2.WND_PROP_VISIBLE) < 1):
                    return None
                if key == ord('r'):
                    wizard = Wizard(cfg)
                visible = wizard.update(observations,time.monotonic(),key)
                cv2.imshow(window,wizard.render(frame,visible))
                shown = True
                if wizard.cancelled:
                    return None
                if wizard.done:
                    return wizard.cfg
    finally:
        camera.close()
        cv2.destroyAllWindows()
