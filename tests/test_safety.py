import copy
import unittest
from unittest.mock import Mock, patch
import gesture_mouse_pi as runtime
from gesture_engine import HandAssociator
import test_engine as fixtures
from test_engine import hand, names, CONFIG


class SafetyTests(unittest.TestCase):
    setUp = fixtures.TestGestureEngine.setUp
    step = fixtures.TestGestureEngine.step
    activate = fixtures.TestGestureEngine.activate

    def test_ambiguous_simultaneous_claim_does_not_pick_detection_order(self):
        self.step([('Left',(.2,.5,None)),('Right',(.6,.5,None))])
        self.step([('Left',(.2,.5,'PINKY')),('Right',(.6,.5,'PINKY'))])
        events,_=self.step([('Left',(.2,.5,'PINKY')),('Right',(.6,.5,'PINKY'))])
        self.assertIn('owner_selection_required',names(events))
        self.assertFalse(self.engine.enabled)

    def test_opposite_hand_does_not_take_lost_owner_track(self):
        owner=self.activate()
        for _ in range(5): self.step([('Right',(.2,.5,None))])
        self.assertEqual(owner,self.engine.owner_id)
        self.assertTrue(self.engine.owner_paused)

    def test_tracking_loss_during_drag_releases_once(self):
        self.activate()
        self.step([('Left',(.2,.5,None))])
        for _ in range(12): self.step([('Left',(.2,.5,'INDEX'))])
        events,_=self.step([])
        self.assertEqual(names(events).count('mouse_up'),1)
        events,_=self.step([])
        self.assertNotIn('mouse_up',names(events))
        for _ in range(3):
            events,_=self.step([('Left',(.2,.5,'INDEX'))])
            self.assertNotIn('mouse_down',names(events))
            self.assertNotIn('mouse_click',names(events))

    def test_secondary_loss_cannot_produce_owner_click(self):
        self.activate()
        for _ in range(3): self.step([('Left',(.2,.5,None)),('Right',(.6,.5,None))])
        for _ in range(3): self.step([('Left',(.2,.5,'INDEX')),('Right',(.6,.5,'INDEX'))])
        self.assertTrue(self.engine.dual_mode)
        self.step([('Left',(.2,.5,'INDEX'))])
        events=[]
        for _ in range(4):
            e,_=self.step([('Left',(.2,.5,None))]); events.extend(e)
        self.assertNotIn('mouse_click',names(events))
        self.assertNotIn('mouse_down',names(events))

    def test_secondary_start_during_click_release_suppresses_click(self):
        self.activate()
        for _ in range(2): self.step([('Left',(.2,.5,None)),('Right',(.6,.5,None))])
        for _ in range(2): self.step([('Left',(.2,.5,'INDEX')),('Right',(.6,.5,None))])
        for _ in range(2):
            events,_=self.step([('Left',(.2,.5,None)),('Right',(.6,.5,'INDEX'))])
        self.assertNotIn('mouse_click',names(events))

    def test_expired_owner_reacquires_only_its_known_hand(self):
        original=self.activate()
        for _ in range(35): self.step([('Right',(.6,.5,None))])
        self.assertTrue(self.engine.owner_paused)
        events,_=self.step([('Left',(.2,.5,'INDEX')),('Right',(.6,.5,None))])
        self.assertIn('tracking_resumed',names(events))
        self.assertNotEqual(original,self.engine.owner_id)
        self.assertNotIn('mouse_click',names(events))
        self.assertNotIn('mouse_down',names(events))


class AssociationTests(unittest.TestCase):
    def test_crossing_with_consistent_labels_keeps_identity(self):
        assoc=HandAssociator()
        first=assoc.update([(hand(.3,.5),'Left'),(hand(.7,.5),'Right')],0)
        left=next(k for k,v in first.items() if v.handedness=='Left')
        for time, lx, rx in ((.05,.4,.6),(.10,.48,.52),(.15,.52,.48),(.20,.6,.4)):
            visible=assoc.update([(hand(rx,.5),'Right'),(hand(lx,.5),'Left')],time)
            self.assertEqual(visible[left].handedness,'Left')

    def test_label_flip_pauses_instead_of_swapping(self):
        assoc=HandAssociator()
        assoc.update([(hand(.4,.5),'Left'),(hand(.6,.5),'Right')],0)
        visible=assoc.update([(hand(.4,.5),'Right'),(hand(.6,.5),'Left')],.05)
        self.assertEqual(visible,{})

    def test_unknown_observation_cannot_steal_known_owner(self):
        assoc=HandAssociator()
        first=assoc.update([(hand(.4,.5),'Left')],0)
        visible=assoc.update([(hand(.4,.5),'Unknown')],.05)
        self.assertTrue(set(first).isdisjoint(visible))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.pg=Mock()
        self.pg.size.return_value=(1920,1080)
        self.pg.position.return_value=(500,400)
        self.pg.FAILSAFE=True
        patcher=patch.object(runtime,'pg',self.pg)
        patcher.start(); self.addCleanup(patcher.stop)
        self.cfg=copy.deepcopy(CONFIG); self.cfg['telemetry_enabled']=False
        self.adapter=runtime.LinuxX11Adapter(self.cfg)

    def test_emergency_release_bypasses_failsafe_and_restores_it(self):
        self.adapter.drag_held=True
        self.pg.mouseUp.side_effect=lambda **_: self.assertFalse(self.pg.FAILSAFE)
        self.adapter.emergency_release()
        self.pg.mouseUp.assert_called_once_with(button='left')
        self.pg.keyUp.assert_called_with('ctrl')
        self.assertTrue(self.pg.FAILSAFE)
        self.assertFalse(self.adapter.drag_held)

    def test_generated_moves_avoid_failsafe_corners(self):
        self.adapter.move(-10000,-10000,1)
        self.pg.moveTo.assert_called_with(1,1,duration=0)

    def test_cancel_clears_partial_scroll(self):
        self.adapter.scroll_pixels=[12,42]; self.adapter.pan_pixels=[3,7]
        self.adapter.perform([('interaction_cancelled',{'reason':'test'})])
        self.assertEqual(self.adapter.scroll_pixels,[0,0])
        self.assertEqual(self.adapter.pan_pixels,[0,0])

    def test_calibrated_screen_and_drag_share_mapping(self):
        from calibration import homography
        matrix=homography([(.2,.2),(.8,.2),(.8,.8),(.2,.8)])
        self.cfg.update(calibration={'matrix':matrix},cursor_smoothing=1.)
        self.adapter.screen_move(.5,.5,0,0)
        self.pg.moveTo.assert_called_with(959,539,duration=0)
        self.adapter.perform([('drag_delta',dict(x=.6,y=.5,dx=.1,dy=0))])
        self.pg.moveTo.assert_called_with(756,400,duration=0)
