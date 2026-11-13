import copy
import unittest
from calibration import transform
from calibration_ui import Wizard
from profiles import validate
from test_engine import CONFIG, hand


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.original = validate(copy.deepcopy(CONFIG))
        self.wizard = Wizard(self.original)
        self.t = 0
        self.position = (.2,.3)

    def step(self, finger=None, key=None):
        self.t += .05
        return self.wizard.update([(hand(*self.position,finger),'Left')],self.t,key)

    def move(self, point):
        start=self.position
        for i in range(1,21):
            self.position=tuple(a+(b-a)*i/20 for a,b in zip(start,point))
            self.step()

    def sample(self, finger=None):
        for _ in range(22): self.step(finger)
        self.step(finger,32)

    def prepare(self):
        self.step(key=32)
        for _ in range(4): self.step('PINKY')
        self.assertEqual(self.wizard.stage,2)
        for p in ((.2,.3),(.8,.3),(.8,.8),(.2,.8)):
            self.move(p); self.sample()
        self.assertEqual(self.wizard.stage,6)
        self.move((.5,.55)); self.sample()
        for _ in range(3): self.sample(); self.sample('INDEX')
        self.assertEqual(self.wizard.stage,13)

    def camera_point(self, target):
        return (.2+(target[0]-.1)*.6/.8, .3+(target[1]-.1)*.5/.8)

    def click(self):
        for _ in range(3): self.step('INDEX')
        for _ in range(4): self.step()

    def test_full_calibration_click_and_drag_flow(self):
        self.prepare()
        for target in self.wizard.targets:
            self.move(self.camera_point(target))
            self.click()
        self.assertEqual(self.wizard.stage,14,self.wizard.message)
        self.move(self.camera_point((.3,.5)))
        for _ in range(13): self.step('INDEX')
        self.assertTrue(self.wizard.dragging)
        start=self.position; end=self.camera_point((.7,.5))
        for i in range(1,21):
            self.position=tuple(a+(b-a)*i/20 for a,b in zip(start,end))
            self.step('INDEX')
        for _ in range(4): self.step()
        self.assertEqual(self.wizard.stage,15,self.wizard.message)
        self.step(key=13)
        self.assertTrue(self.wizard.done)
        validate(self.wizard.cfg)
        self.assertTrue(self.wizard.cfg['calibration']['validation']['drag_passed'])
        self.assertIsNone(self.original['calibration'])

    def test_insufficient_samples_do_not_advance(self):
        self.step(key=32)
        for _ in range(4): self.step('PINKY')
        self.step(key=32)
        self.assertEqual(self.wizard.stage,2)
        self.assertIn('Hold steady',self.wizard.message)

    def test_loss_clears_pending_sample(self):
        self.step(key=32)
        for _ in range(4): self.step('PINKY')
        for _ in range(20): self.step()
        self.wizard.update([],self.t+.05,32)
        self.assertEqual(self.wizard.stage,2)
        self.assertEqual(self.wizard.samples.samples,[])

    def test_missed_target_does_not_pass_validation(self):
        self.prepare()
        self.move(self.camera_point((.2,.2)))
        self.click()
        self.assertEqual(self.wizard.validation,0)
        self.assertEqual(self.wizard.stage,13)
