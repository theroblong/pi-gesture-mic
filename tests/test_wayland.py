"""Virtual input event contracts tested without kernel device access."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import desktop_input
from desktop_input import UInputDriver, session_backend, require_desktop
from gesture_mouse_pi import DesktopAdapter
from test_engine import CONFIG


# Linux UAPI codes used by the backend. Event recording fakes do not emulate libinput.
CODES = dict(EV_KEY=1,EV_REL=2,EV_ABS=3,REL_X=0,REL_Y=1,REL_HWHEEL=6,REL_WHEEL=8,
             ABS_X=0,ABS_Y=1,BTN_LEFT=272,BTN_RIGHT=273,BTN_MIDDLE=274,
             KEY_ESC=1,KEY_LEFTCTRL=29,KEY_EQUAL=13,KEY_MINUS=12,KEY_MICMUTE=248,
             INPUT_PROP_POINTER=0,BUS_USB=3)


class FakeDevice:
    def __init__(self, caps, **kwargs):
        self.caps, self.options = caps, kwargs
        self.events=[]; self.closed=False; self.fail_code=None
    def write(self, kind, code, value):
        if self.fail_code == code:
            self.fail_code=None
            raise OSError('simulated interrupted write')
        self.events.append((kind,code,value))
    def syn(self): self.events.append(('SYN',))
    def close(self): self.closed=True


class WaylandTests(unittest.TestCase):
    def setUp(self):
        self.devices=[]
        def create(caps,**kwargs):
            device=FakeDevice(caps,**kwargs);self.devices.append(device);return device
        self.module=SimpleNamespace(ecodes=SimpleNamespace(**CODES),
                                    AbsInfo=lambda **kwargs:kwargs,UInput=create)
        self.driver=UInputDriver(size=(1920,1080),evdev_module=self.module,settle=False)
        self.addCleanup(self.driver.close)

    def test_separate_devices_are_classified_without_setup_events(self):
        self.assertEqual(len(self.devices),3)
        absolute,relative,keyboard=self.devices
        self.assertIn(3,absolute.caps)
        self.assertEqual(relative.caps[2],[0,1,8,6])
        self.assertEqual(absolute.options['input_props'],[0])
        self.assertIn(CODES['KEY_EQUAL'],keyboard.caps[1])
        self.assertTrue(all(d.events==[] for d in self.devices))

    def test_absolute_coordinates_normalize_and_clamp(self):
        self.driver.moveTo(-50,3000)
        self.assertEqual(self.driver.absolute.events,[(3,0,0),(3,1,65535),('SYN',)])
        self.assertEqual(self.driver.position(),(0,1079))

    def test_relative_motion_uses_rel_events_and_preserves_fraction(self):
        for _ in range(4): self.driver.moveRel(.3,-.3)
        self.assertEqual(self.driver.relative.events,[(2,0,1),(2,1,-1),('SYN',)])
        self.assertEqual(self.driver.absolute.events,[])

    def test_click_drag_release_and_scroll(self):
        self.driver.mouseDown();self.driver.moveTo(100,200);self.driver.mouseUp()
        self.driver.click(button='right')
        self.driver.scroll(-2);self.driver.hscroll(3)
        events=self.driver.absolute.events
        self.assertEqual(events[:2],[(1,272,1),('SYN',)])
        self.assertIn((1,272,0),events)
        self.assertIn((1,273,1),events)
        self.assertIn((1,273,0),events)
        self.assertIn((2,8,-2),events)
        self.assertIn((2,6,3),events)
        self.assertEqual(self.driver.held_buttons,set())

    def test_keyboard_shortcut_releases_in_reverse_order(self):
        self.driver.hotkey('ctrl','=')
        self.assertEqual(self.driver.keyboard.events,
                         [(1,29,1),('SYN',),(1,13,1),('SYN',),(1,13,0),('SYN',),(1,29,0),('SYN',)])
        self.assertEqual(self.driver.held_keys,set())

    def test_failed_shortcut_releases_ctrl(self):
        self.driver.keyboard.fail_code=13
        with self.assertRaises(OSError): self.driver.hotkey('ctrl','=')
        self.assertIn((1,29,0),self.driver.keyboard.events)
        self.assertEqual(self.driver.held_keys,set())

    def test_close_releases_held_input_and_destroys_every_device(self):
        self.driver.mouseDown()
        self.driver.held_keys.add(29)
        self.driver.close();self.driver.close()
        self.assertIn((1,272,0),self.devices[0].events)
        self.assertIn((1,29,0),self.devices[2].events)
        self.assertTrue(all(d.closed for d in self.devices))

    def test_partial_creation_failure_destroys_prior_devices(self):
        made=[]
        def create(caps,**kwargs):
            if made: raise PermissionError('/dev/uinput')
            device=FakeDevice(caps,**kwargs);made.append(device);return device
        self.module.UInput=create
        with self.assertRaisesRegex(RuntimeError,'install_pi.sh'):
            UInputDriver(size=(100,100),evdev_module=self.module,settle=False)
        self.assertTrue(made[0].closed)

    def test_adapter_relative_path_does_not_warp_to_cached_position(self):
        cfg=copy.deepcopy(CONFIG);cfg['telemetry_enabled']=False
        adapter=DesktopAdapter(cfg,driver=self.driver)
        self.assertFalse(self.driver.FAILSAFE)
        adapter.move(20,10,.5)
        self.assertEqual(self.driver.relative.events,[(2,0,10),(2,1,5),('SYN',)])
        self.assertEqual(self.driver.absolute.events,[])
        adapter.close()
        self.assertTrue(all(d.closed for d in self.devices))

    def test_calibrated_drag_keeps_absolute_mapping(self):
        from calibration import homography
        cfg=copy.deepcopy(CONFIG);cfg['telemetry_enabled']=False
        cfg['calibration']={'matrix':homography([(.2,.2),(.8,.2),(.8,.8),(.2,.8)])}
        adapter=DesktopAdapter(cfg,driver=self.driver)
        adapter.perform([('mouse_down',{'button':'left'}),
                         ('drag_delta',dict(x=.6,y=.5,dx=.1,dy=0)),
                         ('mouse_up',{'button':'left'})])
        self.assertEqual(self.driver.relative.events,[])
        self.assertTrue(any(event[0]==3 for event in self.driver.absolute.events))
        self.assertFalse(adapter.drag_held)


class SessionTests(unittest.TestCase):
    def test_wayland_takes_precedence_over_xwayland_display(self):
        self.assertEqual(session_backend({'DISPLAY':':0','XDG_SESSION_TYPE':'wayland'}),'uinput')
        self.assertEqual(session_backend({'DISPLAY':':0','WAYLAND_DISPLAY':'wayland-0'}),'uinput')
        self.assertEqual(session_backend({'DISPLAY':':0','XDG_SESSION_TYPE':'x11'}),'x11')
        require_desktop({'DISPLAY':':0','WAYLAND_DISPLAY':'wayland-0'})

    def test_missing_ui_display_error_does_not_ask_for_x11_switch(self):
        with self.assertRaisesRegex(RuntimeError,'XWayland'):
            require_desktop({'WAYLAND_DISPLAY':'wayland-0'})

    def test_factory_wayland_never_imports_pyautogui(self):
        import builtins
        original=builtins.__import__
        def guarded(name,*args,**kwargs):
            self.assertNotEqual(name,'pyautogui')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=guarded),patch.object(desktop_input,'UInputDriver') as driver:
            self.assertIs(desktop_input.create_driver('uinput'),driver.return_value)
