import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch
from calibration import homography
from desktop_input import require_desktop
from kiosk_session import supervise, web_url, stop_child
import kiosk_session
import gesture_mouse_pi as runtime
from test_engine import CONFIG


class KioskSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.ready=self.folder/'ready.json'
        self.log=(self.folder/'gesture.log').open('w')
        self.addCleanup(self.log.close)

    def controller(self,ready=True,exit_after=None,invalid=False):
        stop=self.folder/'controller-stopped'
        code=f'''import signal,time,sys,json
from pathlib import Path
signal.signal(signal.SIGTERM,lambda *_: (Path({str(stop)!r}).write_text('stopped'),sys.exit(0)))
'''
        if ready:
            code+=f"Path({str(self.ready)!r}).write_text(json.dumps({{'ready':{not invalid!r},'backend':'uinput'}}))\n"
        code+=f'time.sleep({exit_after if exit_after is not None else 60})\n'
        if exit_after is not None: code+='sys.exit(7)\n'
        return [sys.executable,'-u','-c',code]

    def browser(self,wait=False):
        start=self.folder/'browser-started';stop=self.folder/'browser-stopped'
        code=f'''import signal,time,sys
from pathlib import Path
signal.signal(signal.SIGTERM,lambda *_: (Path({str(stop)!r}).write_text('stopped'),sys.exit(0)))
Path({str(start)!r}).write_text('started')
'''
        if wait: code+='time.sleep(60)\n'
        return [sys.executable,'-u','-c',code]

    def run_supervisor(self,controller,browser,timeout=2):
        with contextlib.redirect_stdout(io.StringIO()):
            return supervise(controller,browser,self.ready,self.log,timeout)

    def test_browser_exit_stops_controller(self):
        self.assertEqual(self.run_supervisor(self.controller(),self.browser()),0)
        self.assertTrue((self.folder/'browser-started').exists())
        self.assertTrue((self.folder/'controller-stopped').exists())

    def test_startup_failure_never_launches_browser(self):
        with self.assertRaisesRegex(RuntimeError,'startup failed'):
            self.run_supervisor([sys.executable,'-c','raise SystemExit(4)'],self.browser())
        self.assertFalse((self.folder/'browser-started').exists())

    def test_startup_timeout_cleans_up_child(self):
        with self.assertRaisesRegex(RuntimeError,'timed out'):
            self.run_supervisor(self.controller(ready=False),self.browser(),timeout=.35)
        self.assertTrue((self.folder/'controller-stopped').exists())
        self.assertFalse((self.folder/'browser-started').exists())

    def test_runtime_gesture_failure_closes_browser(self):
        with self.assertRaisesRegex(RuntimeError,'controller stopped'):
            self.run_supervisor(self.controller(exit_after=.5),self.browser(wait=True))
        self.assertTrue((self.folder/'browser-stopped').exists())

    def test_invalid_readiness_never_starts_browser(self):
        with self.assertRaisesRegex(RuntimeError,'invalid kiosk readiness'):
            self.run_supervisor(self.controller(invalid=True),self.browser())
        self.assertFalse((self.folder/'browser-started').exists())
        self.assertTrue((self.folder/'controller-stopped').exists())

    def test_cleanup_reaps_helpers_even_after_parent_exits(self):
        child=Mock(pid=12345)
        with patch.object(kiosk_session.os,'killpg') as kill:
            stop_child(child)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(12345,signal.SIGTERM),(12345,signal.SIGKILL)])
        child.wait.assert_any_call(timeout=3)

    def test_web_url_is_argument_data_and_rejects_options_credentials(self):
        self.assertEqual(web_url('https://app.example/?a=1&b=2'),'https://app.example/?a=1&b=2')
        for value in ('--no-sandbox','file:///tmp/a','https://user:pass@app.example','https://'):
            with self.assertRaises(argparse.ArgumentTypeError):web_url(value)


class KioskRuntimeTests(unittest.TestCase):
    def test_cage_runtime_requires_wayland_socket_but_not_xwayland(self):
        require_desktop({'WAYLAND_DISPLAY':'wayland-1'},kiosk=True)
        with self.assertRaisesRegex(RuntimeError,'inside Cage'):
            require_desktop({'DISPLAY':':0'},kiosk=True)

    def test_no_preview_runtime_has_no_tk_dependency_and_reports_real_frame_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'profile.json').write_text('{}')
            (root/'hand_landmarker.task').write_bytes(b'mock model')
            ready=root/'ready.json'
            cfg=copy.deepcopy(CONFIG)
            corners=[(.2,.2),(.8,.2),(.8,.8),(.2,.8)]
            cfg['calibration']={'matrix':homography(corners),'corners':corners}
            cfg['telemetry_enabled']=False
            cfg['microphone_source']=None
            store=Mock();store.active.return_value='Default';store.load.return_value=cfg
            store.path.return_value=root/'profile.json'
            frame=Mock();frame.shape=(540,960,3)
            camera=Mock();camera.read.side_effect=[frame,frame,KeyboardInterrupt]
            cv=MagicMock();cv.resize.return_value=frame
            mp=MagicMock()
            tracker=mp.tasks.vision.HandLandmarker.create_from_options.return_value.__enter__.return_value
            tracker.detect_for_video.return_value=Mock(hand_landmarks=[])
            driver=Mock();driver.size.return_value=(1920,1080);driver.position.return_value=(960,540)
            driver.FailSafeException=RuntimeError
            previous=signal.getsignal(signal.SIGTERM)
            import builtins
            original_import=builtins.__import__
            def guarded(name,*args,**kwargs):
                self.assertNotIn(name,('tkinter','pyautogui','setup_ui'))
                return original_import(name,*args,**kwargs)
            try:
                with patch.object(runtime,'ROOT',root),patch.object(runtime,'STORE',store), \
                     patch.object(runtime,'state_home',return_value=root), \
                     patch.object(runtime,'Camera',return_value=camera), \
                     patch.object(runtime,'create_driver',return_value=driver) as create, \
                     patch.dict(sys.modules,{'cv2':cv,'mediapipe':mp}), \
                     patch('builtins.__import__',side_effect=guarded), \
                     patch.dict(os.environ,{'WAYLAND_DISPLAY':'wayland-1','DISPLAY':''}), \
                     patch.object(sys,'argv',['gesture_mouse_pi.py','--kiosk','--ready-file',str(ready)]), \
                     contextlib.redirect_stdout(io.StringIO()):
                    runtime.main()
                create.assert_called_once_with('uinput',size=(1920,1080))
                cv.imshow.assert_not_called()
                store.save.assert_not_called()
                camera.close.assert_called_once()
                driver.close.assert_called_once()
                self.assertTrue(json.loads(ready.read_text())['ready'])
                tracker.detect_for_video.assert_called_once()
            finally:
                signal.signal(signal.SIGTERM,previous)

    def test_kiosk_without_saved_calibration_explains_setup(self):
        store=Mock();store.active.return_value='Default';store.load.return_value=copy.deepcopy(CONFIG)
        store.path.return_value=Path('/nonexistent/gesture-profile.json')
        with patch.object(runtime,'STORE',store),patch.object(sys,'argv',['gesture_mouse_pi.py','--kiosk']):
            with self.assertRaisesRegex(RuntimeError,'saved calibrated profile'):runtime.main()


class KioskLauncherTests(unittest.TestCase):
    def test_shell_launch_preserves_url_and_profile_arguments(self):
        with tempfile.TemporaryDirectory(prefix='kiosk path ') as folder:
            root=Path(folder)
            shutil.copyfile(Path(__file__).resolve().parents[1]/'start_alt_kiosk.sh',root/'start_alt_kiosk.sh')
            (root/'.venv/bin').mkdir(parents=True)
            (root/'bin').mkdir()
            python=root/'.venv/bin/python';python.write_text('#!/bin/sh\nexit 0\n');python.chmod(0o755)
            browser=root/'bin/chromium';browser.write_text('#!/bin/sh\nexit 0\n');browser.chmod(0o755)
            cage=root/'bin/cage'
            cage.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARG_CAPTURE"\n');cage.chmod(0o755)
            capture=root/'args'
            env=dict(os.environ,PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],ARG_CAPTURE=str(capture))
            url='https://app.example/?a=1&b=two%20words'
            result=subprocess.run(['bash',str(root/'start_alt_kiosk.sh'),url,'--profile','Living room'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(capture.read_text().splitlines(),['--',str(python),str(root/'kiosk_session.py'),url,'--browser',str(browser),'--profile','Living room'])

    def test_session_uses_persistent_profile_without_blanket_mic_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def inspect_launch(controller,browser,ready,log):
                self.assertIn('--kiosk',controller)
                self.assertEqual(controller[-2:],['--profile','Living room'])
                self.assertIn(f'--user-data-dir={root}/config/chromium-kiosk',browser)
                self.assertIn('--ozone-platform=wayland',browser)
                self.assertFalse(any('fake-ui' in arg or 'auto-accept' in arg for arg in browser))
                self.assertEqual(os.environ['XDG_SESSION_TYPE'],'wayland')
                return 0
            with patch.object(kiosk_session,'config_home',return_value=root/'config'), \
                 patch.object(kiosk_session,'state_home',return_value=root/'state'), \
                 patch.object(kiosk_session,'supervise',side_effect=inspect_launch) as run, \
                 patch.dict(os.environ,{'WAYLAND_DISPLAY':'wayland-1','XDG_SESSION_TYPE':'tty'}), \
                 patch.object(sys,'argv',['kiosk_session.py','https://app.example','--browser','chromium','--profile','Living room']), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(kiosk_session.main(),0)
                run.assert_called_once()
            self.assertTrue((root/'config/chromium-kiosk').is_dir())
