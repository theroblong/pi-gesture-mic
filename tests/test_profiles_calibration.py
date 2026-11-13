import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from calibration import homography, transform, TARGETS, StableSamples, pinch_thresholds
from profiles import ProfileStore, validate

DEFAULTS = Path(__file__).resolve().parents[1]/'gesture_config.json'


class CalibrationTests(unittest.TestCase):
    def test_skewed_plane_maps_corners(self):
        points = [(0.2,0.2),(0.8,0.22),(0.75,0.8),(0.22,0.78)]
        matrix = homography(points)
        for p,t in zip(points,TARGETS):
            self.assertLess(math.dist(transform(matrix,p),t), 1e-8)

    def test_invalid_planes_rejected(self):
        for points in ([ (.5,.5)]*4, [(0,0),(1,1),(1,0),(0,1)],
                       [(0,0),(.01,0),(.01,.01),(0,.01)],
                       [(0,0),(math.nan,0),(1,1),(0,1)],
                       [(0,0),(0,1),(1,1),(1,0)]):
            with self.assertRaises(ValueError): homography(points)

    def test_mapping_clips_edges_and_rejects_horizon(self):
        matrix = homography([(.2,.2),(.8,.2),(.8,.8),(.2,.8)])
        self.assertEqual(transform(matrix,(-1,2)),(0.,1.))
        with self.assertRaises(ValueError): transform([1,0,0,0,1,0,0,0,0],(.5,.5))

    def test_sampling_requires_duration_stability_and_same_identity(self):
        samples = StableSamples()
        for i in range(20): samples.add(1,(.4,.5),.2,i*.05)
        self.assertEqual(samples.capture()[0],(.4,.5))
        samples.add(2,(.4,.5),.2,1.)
        with self.assertRaises(ValueError): samples.capture()
        for i in range(20): samples.add(2,(.4+i*.01,.5),.2,1.05+i*.05)
        with self.assertRaises(ValueError): samples.capture()
        samples.add(2,(.4,.5),.2,4.)
        with self.assertRaises(ValueError): samples.capture()

    def test_pinch_thresholds_hysteresis_and_overlap(self):
        cfg = pinch_thresholds([1.3]*30,[.2]*30)
        self.assertLess(.2,cfg['pinch_start_ratio'])
        self.assertLess(cfg['pinch_start_ratio'],cfg['pinch_end_ratio'])
        self.assertLess(cfg['pinch_end_ratio'],1.3)
        for opened,closed in (([.3]*20,[.2]*20),([1.]*2,[.2]*20),([math.nan]*20,[.2]*20)):
            with self.assertRaises(ValueError): pinch_thresholds(opened,closed)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProfileStore(self.temp.name,DEFAULTS)
        self.cfg = self.store.load('Default')

    def test_persistence_migration_and_isolation(self):
        legacy = copy.deepcopy(self.cfg)
        legacy['schema_version'] = 6
        for key in ('camera_device', 'microphone_source', 'mirror_camera', 'calibration'):
            legacy.pop(key)
        migrated = validate(legacy)
        self.assertEqual(migrated['schema_version'],7)
        self.assertEqual(migrated['cursor_smoothing'],legacy['cursor_smoothing'])
        self.assertIsNone(migrated['calibration'])
        self.assertEqual(legacy['schema_version'],6)
        self.assertEqual(self.cfg['schema_version'],7)
        self.store.save('Alice',self.cfg)
        bob = copy.deepcopy(self.cfg)
        bob['cursor_smoothing'] = .8
        self.store.save('Bob',bob)
        self.assertEqual(self.store.active(),'Bob')
        self.assertEqual(self.store.load('Alice')['cursor_smoothing'],.35)
        self.assertEqual(self.store.load()['cursor_smoothing'],.8)
        self.assertEqual(self.store.names(),['Alice','Bob'])

    def test_reject_invalid_names(self):
        for name in ('../outside','/tmp/evil','','.hidden','x'*49,'a\nb'):
            with self.assertRaises(ValueError): self.store.path(name)

    def test_invalid_save_preserves_existing(self):
        self.store.save('Alice',self.cfg)
        before = self.store.path('Alice').read_bytes()
        self.cfg['pinch_end_ratio'] = .01
        with self.assertRaises(ValueError): self.store.save('Alice',self.cfg)
        self.assertEqual(before,self.store.path('Alice').read_bytes())
        self.assertEqual(list(Path(self.temp.name).rglob('.pending-*')),[])

    def test_invalid_config_types_and_nonfinite(self):
        for key,value in [('cursor_smoothing',True),('cursor_smoothing',math.nan),
                          ('capture_width',0),('capture_height',100000),('show_preview',1),
                          ('camera_device','https://example.com/video'),('model_path',None)]:
            cfg = copy.deepcopy(self.cfg); cfg[key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): validate(cfg)

    def test_camera_changes_invalidate_calibration(self):
        corners = [(.2,.2),(.8,.2),(.8,.8),(.2,.8)]
        self.cfg['calibration'] = dict(version=1,corners=corners,matrix=homography(corners),
            handedness='Left',mirror_camera=True,camera_device=None)
        validate(self.cfg)
        self.cfg['mirror_camera'] = False
        with self.assertRaises(ValueError): validate(self.cfg)
        self.cfg['mirror_camera'] = True
        self.cfg['calibration']['matrix'][0] = 100
        with self.assertRaises(ValueError): validate(self.cfg)

    def test_corrupt_profile_is_not_silently_overwritten(self):
        path = self.store.path('Alice'); path.parent.mkdir(parents=True)
        path.write_text('{bad')
        with self.assertRaises(ValueError): self.store.load('Alice')
        self.assertEqual(path.read_text(),'{bad')
