import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import zipfile
import devices
from tools.build_release import build


class PackageTests(unittest.TestCase):
    def test_archive_is_repeatable_complete_and_contains_no_private_state(self):
        with tempfile.TemporaryDirectory() as folder:
            archive,digest,_=build(folder)
            first=archive.read_bytes()
            self.assertEqual(build(folder)[1],digest)
            self.assertEqual(archive.read_bytes(),first)
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                self.assertIsNone(z.testzip())
                self.assertFalse(any('/.git/' in n or '/.venv/' in n or '.wav' in n or '.jsonl' in n or '/dist/' in n for n in names))
                manifest=json.loads(z.read('pi-gesture-mic/MANIFEST.json'))
                self.assertEqual(len(names),len(manifest['files'])+1)
                for name,sha in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(z.read('pi-gesture-mic/'+name)).hexdigest(),sha)
                self.assertTrue(z.getinfo('pi-gesture-mic/install_pi.sh').external_attr >> 16 & 0o111)
                z.extractall(Path(folder)/'extract')
                self.assertTrue((Path(folder)/'extract/pi-gesture-mic/README.md').is_file())


class DeviceTests(unittest.TestCase):
    def test_monitor_sources_excluded_and_stable_names_used(self):
        sources=[dict(name='alsa_input.usb-mic',description='USB Mic',monitor_of_sink=None),
                 dict(name='alsa_output.hdmi.monitor',description='Output',monitor_of_sink=1)]
        with patch.object(devices,'command',return_value=json.dumps(sources)):
            self.assertEqual(devices.microphones(),[('alsa_input.usb-mic','USB Mic')])

    def test_missing_microphone_never_changes_desktop_default(self):
        with patch.object(devices,'microphones',return_value=[]),patch.object(devices,'command') as command:
            with self.assertRaises(RuntimeError): devices.select_microphone('missing')
            command.assert_not_called()

    def test_microphone_selection_sets_default_and_unmutes_only_selected(self):
        with patch.object(devices,'microphones',return_value=[('usb-mic','Mic')]),patch.object(devices,'command') as command:
            devices.select_microphone('usb-mic')
            self.assertEqual(command.call_args_list[0].args[0],['pactl','set-default-source','usb-mic'])
            self.assertEqual(command.call_args_list[1].args[0],['pactl','set-source-mute','usb-mic','0'])

    def test_stale_camera_and_disconnect_raise_before_delivering_old_frame(self):
        camera=devices.Camera.__new__(devices.Camera)
        camera.error=None; camera.timestamp=time.monotonic()-4
        camera.frame=Mock(); camera.last_delivered=None
        with self.assertRaises(RuntimeError): camera.read()
        camera.timestamp=time.monotonic();camera.error='Disconnected'
        with self.assertRaisesRegex(RuntimeError,'Disconnected'): camera.read()
        camera.error=None
        self.assertIsNotNone(camera.read())
        self.assertIsNone(camera.read())

    def test_cancelled_microphone_test_stops_child_and_removes_recording(self):
        import threading
        cancel=threading.Event();cancel.set()
        proc=Mock(); proc.poll.return_value=None
        proc.__enter__=Mock(return_value=proc)
        proc.__exit__=Mock(return_value=False)
        paths=[]
        def launch(args,**kwargs):
            paths.append(Path(args[-1]))
            paths[-1].write_bytes(b'temporary audio')
            return proc
        with patch.object(devices.subprocess,'Popen',side_effect=launch):
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                devices.microphone_test('usb-mic',cancel)
        proc.terminate.assert_called_once()
        self.assertFalse(paths[0].exists())
