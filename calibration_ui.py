"""Full-screen guided calibration. All practice input is kept inside this window."""
import copy
import math
import time
from datetime import datetime, timezone
from calibration import TARGETS, StableSamples, homography, transform, pinch_thresholds
from gesture_engine import GestureEngine, distance
from devices import Camera


class Wizard:
    def __init__(self, cfg):
        self.cfg = copy.deepcopy(cfg)
        self.cfg['calibration'] = None
        self.cfg['pointer_landmark'] = 0
        self.cfg['pointer_mode'] = 'screen'
        self.engine = GestureEngine(self.cfg)
        self.stage = 0
        self.samples = StableSamples()
        self.corners, self.opened, self.closed = [], [], []
        self.message = 'Press SPACE when your camera is positioned comfortably.'
        self.matrix = None
        self.hand = None
        self.cursor = (.5, .5)
        self.errors = []
        self.validation = 0
        self.dragging = False
        self.drag_origin = None
        self.drag_previous = None
        self.done = False
        self.targets = ((.5,.5), (.25,.25), (.75,.25), (.75,.75), (.25,.75))

    def advance(self):
        self.stage += 1
        self.samples.clear()
        self.message = ('Open your hand, move the blue dot into the ring, then make a quick index pinch.'
                        if self.stage == 13 else 'Hold your wrist steady, then press SPACE.')

    def update(self, observations, now, key=None):
        events, visible = self.engine.update(observations, now)
        owner = visible.get(self.engine.owner_id)
        if self.stage == 0:
            if key == 32 and visible:
                self.advance()
                self.message = 'Touch thumb to pinky on the hand you want to use.'
            return visible
        if self.stage == 1:
            if owner and owner.handedness in ('Left', 'Right'):
                self.hand = owner.handedness
                self.advance()
            return visible
        if not owner or owner.handedness != self.hand or self.engine.owner_paused:
            self.samples.clear()
            self.dragging = False
            self.drag_previous = None
            self.message = 'Return your controlling hand. If control is off, use its pinky pinch.'
            return visible
        ratio = distance(owner.hand[4], owner.hand[8]) / max(distance(owner.hand[5], owner.hand[17]), .001)
        self.samples.add(owner.id, owner.hand[0], ratio, now)
        if 2 <= self.stage <= 12 and key == 32:
            try:
                point, ratios = self.samples.capture()
                if 2 <= self.stage <= 5:
                    points = self.corners + [point]
                    if self.stage == 5:
                        self.matrix = homography(points)
                    self.corners = points
                elif self.stage == 6:
                    error = math.dist(transform(self.matrix, point, clip=False), (.5,.5))
                    if error > .15:
                        raise ValueError('Center is off. Press R to restart and use a comfortable rectangular reach.')
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
            except ValueError as exc:
                self.message = str(exc)
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
                        self.message = 'Calibration passed. Press ENTER to save and launch.'
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
        if self.stage == 15 and key in (10,13):
            self.done = True
        return visible

    def instructions(self):
        if self.stage == 0:
            return 'Camera position', 'Face the camera. Show both wrists and fingertips. SPACE to continue.'
        if self.stage == 1:
            return 'Choose your controlling hand', 'Thumb + pinky selects the hand. Your other hand will scroll and zoom.'
        if 2 <= self.stage <= 5:
            corner = ('TOP LEFT','TOP RIGHT','BOTTOM RIGHT','BOTTOM LEFT')[self.stage-2]
            return f'Comfortable reach: {corner}', 'Move your open hand toward the target. Keep your wrist still. Press SPACE.'
        if self.stage == 6:
            return 'Neutral position', 'Move your open hand to a comfortable center. Hold still and press SPACE.'
        if 7 <= self.stage <= 12:
            trial = (self.stage-7)//2+1
            return f'Pinch calibration {trial}/3', ('OPEN your fingers. Hold your wrist still. Press SPACE.' if self.stage % 2 else
                                                     'Touch INDEX fingertip to thumb. Hold it still. Press SPACE.')
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
        footer = ('ENTER save and launch' if self.stage == 15 else
                  'Pinch to interact' if self.stage in (13,14) else 'SPACE capture')
        text(footer + '  |  R restart  |  ESC cancel without saving',36,704,.52)
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
                if wizard.done:
                    return wizard.cfg
    finally:
        camera.close()
        cv2.destroyAllWindows()
