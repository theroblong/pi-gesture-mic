"""Gesture-only wizard paths; none of these flows send a keyboard key."""
import copy
import unittest
from calibration import GestureHold
from calibration_ui import Wizard
from profiles import validate
from test_engine import CONFIG, hand


class HandsFreeTests(unittest.TestCase):
    def setUp(self):
        self.original=validate(copy.deepcopy(CONFIG))
        self.wizard=Wizard(self.original)
        self.t=0.
        self.position=(.5,.55)

    def step(self,finger=None, observations=None):
        self.t+=.05
        obs=observations if observations is not None else [(hand(*self.position,finger),'Left')]
        return self.wizard.update(obs,self.t)

    def hold(self,finger=None,seconds=2.8):
        for _ in range(round(seconds/.05)):
            self.step(finger)

    def move(self,point,finger=None):
        start=self.position
        for i in range(1,21):
            self.position=tuple(a+(b-a)*i/20 for a,b in zip(start,point))
            self.step(finger)

    def choose(self):
        self.hold()
        self.assertEqual(self.wizard.stage,2)
        self.assertEqual(self.wizard.hand,'Left')

    def prepare(self):
        self.choose()
        for index,p in enumerate(((.2,.3),(.8,.3),(.8,.8),(.2,.8))):
            self.move(p);self.hold()
            self.assertEqual(self.wizard.stage,3+index,self.wizard.message)
        self.move((.5,.55));self.hold()
        self.assertEqual(self.wizard.stage,7)
        for index in range(3):
            self.hold()
            self.assertEqual(self.wizard.stage,8+2*index)
            self.hold('INDEX')
            self.assertEqual(self.wizard.stage,9+2*index,self.wizard.message)
        self.assertEqual(self.wizard.stage,13)

    @staticmethod
    def camera_point(target):
        return (.2+(target[0]-.1)*.6/.8,.3+(target[1]-.1)*.5/.8)

    def click(self):
        self.hold('INDEX',.15)
        self.hold(None,.20)

    def practice(self):
        for target in self.wizard.targets:
            self.move(self.camera_point(target));self.click()
        self.assertEqual(self.wizard.stage,14)
        self.move(self.camera_point((.3,.5)))
        self.hold('INDEX',.65)
        self.assertTrue(self.wizard.dragging)
        self.move(self.camera_point((.7,.5)),'INDEX')
        self.hold(None,.25)
        self.assertEqual(self.wizard.stage,15)

    def test_entire_wizard_saves_without_any_keyboard_input(self):
        self.prepare();self.practice()
        self.assertFalse(self.wizard.done)
        self.hold('INDEX',1.7)
        self.assertTrue(self.wizard.done)
        self.assertFalse(self.wizard.cancelled)
        validate(self.wizard.cfg)
        self.assertIsNone(self.original['calibration'])
        self.assertEqual(len(self.wizard.cfg['calibration']['validation']['click_errors']),5)

    def test_two_visible_hands_do_not_auto_choose_owner(self):
        for _ in range(80):
            self.step(observations=[(hand(.3,.5),'Left'),(hand(.65,.5),'Right')])
        self.assertEqual(self.wizard.stage,0)
        self.assertIsNone(self.wizard.hand)

    def test_same_position_does_not_capture_first_or_next_corner(self):
        self.choose();self.hold(seconds=4)
        self.assertEqual(self.wizard.stage,2)
        self.move((.2,.3));self.hold()
        self.assertEqual(self.wizard.stage,3)
        self.hold(seconds=5)
        self.assertEqual(self.wizard.stage,3)
        self.assertEqual(len(self.wizard.corners),1)

    def test_wrong_pose_does_not_capture_open_or_pinch_sample(self):
        self.prepare()
        # Revisit the first pinch-measurement stage with a valid open baseline.
        self.wizard.stage=8;self.wizard.stage_since=self.t
        before=list(self.wizard.closed)
        self.hold(seconds=4)
        self.assertEqual(self.wizard.stage,8)
        self.assertEqual(self.wizard.closed,before)
        self.wizard.stage=7;self.wizard.stage_since=self.t
        self.hold('INDEX',4)
        self.assertEqual(self.wizard.stage,7)

    def test_tracking_loss_discards_in_progress_dwell(self):
        self.choose();self.move((.2,.3));self.hold(seconds=1)
        self.assertGreater(self.wizard.hold_progress,0)
        self.step(observations=[])
        self.assertEqual(self.wizard.hold_progress,0)
        self.hold(seconds=1.2)
        self.assertEqual(self.wizard.stage,2)
        self.hold(seconds=1.4)
        self.assertEqual(self.wizard.stage,3)

    def test_middle_pinch_restarts_without_changing_source_profile(self):
        self.choose();self.move((.2,.3));self.hold()
        self.hold('MIDDLE',2.2)
        self.assertEqual(self.wizard.stage,0)
        self.assertEqual(self.wizard.corners,[])
        self.assertIsNone(self.original['calibration'])
        self.assertFalse(self.wizard.commands_armed)

    def test_ring_pinch_cancels_without_saving(self):
        self.choose();self.hold('RING',3.2)
        self.assertTrue(self.wizard.cancelled)
        self.assertFalse(self.wizard.done)
        self.assertIsNone(self.original['calibration'])

    def test_short_command_pinch_does_not_restart_or_cancel(self):
        self.choose()
        self.hold('MIDDLE',.5);self.hold(None,.2)
        self.assertEqual(self.wizard.stage,2)
        self.hold('RING',.5);self.hold(None,.2)
        self.assertFalse(self.wizard.cancelled)
        self.assertEqual(self.wizard.stage,2)

    def test_save_requires_open_hand_then_fresh_deliberate_hold(self):
        self.prepare();self.practice()
        self.wizard.save_armed=False
        self.hold('INDEX',2)
        self.assertFalse(self.wizard.done)
        self.hold(None,.3)
        self.hold('INDEX',.5);self.hold(None,.2)
        self.assertFalse(self.wizard.done)
        self.hold('INDEX',1.7)
        self.assertTrue(self.wizard.done)

    def test_command_during_drag_clears_local_drag_even_if_aborted(self):
        self.prepare()
        self.wizard.stage=14
        self.move(self.camera_point((.3,.5)))
        self.hold('INDEX',.65)
        self.assertTrue(self.wizard.dragging)
        self.hold('MIDDLE',.5)
        self.assertFalse(self.wizard.dragging)
        self.assertIsNone(self.wizard.drag_previous)
        self.hold(None,.3)
        self.assertEqual(self.wizard.stage,14)


class HoldTests(unittest.TestCase):
    def test_time_gap_identity_and_movement_restart_countdown(self):
        for reason in ('gap','identity','movement'):
            hold=GestureHold()
            for i in range(31):self.assertFalse(hold.update(1,(.5,.5),i*.05))
            self.assertGreater(hold.progress,.7)
            now=1.9 if reason=='gap' else 1.55
            token=2 if reason=='identity' else 1
            point=(.55,.5) if reason=='movement' else (.5,.5)
            self.assertFalse(hold.update(token,point,now))
            self.assertEqual(hold.progress,0)

    def test_wrong_pose_clears_and_stale_two_frames_cannot_complete_hold(self):
        hold=GestureHold()
        self.assertFalse(hold.update(1,(.5,.5),0))
        self.assertFalse(hold.update(1,(.5,.5),2.1))
        hold.update(None,None,2.15)
        self.assertEqual(hold.progress,0)
        self.assertIsNone(hold.token)
