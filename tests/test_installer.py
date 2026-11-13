"""Run installer control flow with fake OS commands; never invokes real sudo/apt."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.app=self.base/'app with spaces'; self.app.mkdir()
        self.bin=self.base/'bin'; self.bin.mkdir()
        self.log=self.base/'calls.log'
        self.osfile=self.base/'os-release'
        self.osfile.write_text('ID=debian\nVERSION_CODENAME=trixie\n')
        script=(ROOT/'install_pi.sh').read_text().replace('/etc/os-release',str(self.osfile))
        # Root CI runners exercise the normal-user path without running privileges.
        script=script.replace('[[ $EUID -ne 0 ]]','[[ 501 -ne 0 ]]')
        # Host test environment denies /dev/fd process substitution; omit tee only.
        script=script.replace('exec > >(tee -a "$STATE_DIR/install.log") 2>&1', ':')
        (self.app/'install_pi.sh').write_text(script)
        shutil.copy(ROOT/'run_pi.sh',self.app)
        (self.app/'tools').mkdir()
        shutil.copy(ROOT/'tools/desktop_entry.py',self.app/'tools')
        self.env={**os.environ,'PATH':str(self.bin)+':'+os.environ['PATH'],
                  'XDG_CONFIG_HOME':str(self.base/'config'),'XDG_STATE_HOME':str(self.base/'state'),
                  'XDG_DATA_HOME':str(self.base/'data'),'DISPLAY':':0','XDG_SESSION_TYPE':'x11',
                  'WAYLAND_DISPLAY':'','CALL_LOG':str(self.log)}
        self.command('uname','if [ "$1" = -s ]; then echo Linux; else echo aarch64; fi')
        self.command('sudo','echo "sudo $*" >> "$CALL_LOG"\n[ "${FAIL_SUDO:-}" != 1 ]')
        self.command('raspi-config','exit 0')
        self.command('sha256sum','cat >/dev/null; exit 0')
        runtime='#!/bin/bash\necho "runtime $*" >> "$CALL_LOG"\nif [ "${FAIL_INPUT:-}" = 1 ] && [ "$1" = tools/check_input.py ]; then exit 1; fi\n'
        self.runtime=runtime
        py = '#!'+sys.executable+'\n'+'''import os,sys,pathlib,subprocess
with open(os.environ['CALL_LOG'],'a') as f: f.write('python '+ ' '.join(sys.argv[1:])+'\\n')
if sys.argv[1:3] == ['-m','venv']:
 p=pathlib.Path('.venv/bin/python'); p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(RUNTIME); p.chmod(0o755)
elif sys.argv[1] == '-':
 sys.stdin.read()
else:
 sys.exit(subprocess.call([REAL_PYTHON]+sys.argv[1:]))
'''
        py=py.replace('RUNTIME',repr(runtime)).replace('REAL_PYTHON',repr(sys.executable))
        path=self.bin/'python3';path.write_text(py);path.chmod(0o755)

    def command(self,name,body):
        path=self.bin/name;path.write_text('#!/bin/bash\n'+body+'\n');path.chmod(0o755)

    def run_installer(self,*args):
        return subprocess.run(['bash',str(self.app/'install_pi.sh'),*args],env=self.env,
                              input='',text=True,capture_output=True,timeout=15)

    def test_fresh_install_and_rerun(self):
        for _ in range(2):
            result=self.run_installer()
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        calls=self.log.read_text()
        self.assertEqual(calls.count('runtime gesture_mouse_pi.py --setup'),2)
        self.assertIn('runtime tools/verify_runtime.py',calls)
        self.assertTrue((self.base/'data/applications/pi-gesture-mic.desktop').exists())
        self.assertFalse((self.base/'config/autostart/gesture-control-pi.desktop').exists())

    def test_wayland_installs_input_and_launches_without_desktop_switch(self):
        self.env.update(XDG_SESSION_TYPE='wayland',WAYLAND_DISPLAY='wayland-0')
        result=self.run_installer()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        calls=self.log.read_text()
        self.assertIn('sudo modprobe uinput',calls)
        self.assertIn('sudo install -m 0644 system/70-pi-gesture-mic-uinput.rules',calls)
        self.assertIn('runtime tools/check_input.py',calls)
        self.assertIn('runtime gesture_mouse_pi.py --setup',calls)
        self.assertNotIn('raspi-config',calls)
        self.assertNotIn('reboot',calls)
        self.assertFalse((self.base/'config/autostart/pi-gesture-mic-resume.desktop').exists())

    def test_wayland_headless_resume_does_not_reinstall_or_switch(self):
        self.env.update(XDG_SESSION_TYPE='wayland',WAYLAND_DISPLAY='wayland-0',DISPLAY='')
        self.assertEqual(self.run_installer().returncode,0)
        resume=self.base/'config/autostart/pi-gesture-mic-resume.desktop'
        self.assertTrue(resume.exists())
        self.log.write_text('')
        self.env['DISPLAY']=':0'
        result=self.run_installer('--resume')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(resume.exists())
        self.assertNotIn('sudo',self.log.read_text())
        self.assertIn('runtime tools/check_input.py',self.log.read_text())
        self.assertIn('runtime gesture_mouse_pi.py --setup',self.log.read_text())

    def test_failed_wayland_input_check_stops_before_launch(self):
        self.env.update(XDG_SESSION_TYPE='wayland',FAIL_INPUT='1')
        result=self.run_installer()
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('runtime gesture_mouse_pi.py',self.log.read_text())
        self.assertIn('Log out and back',result.stdout+result.stderr)
        self.assertNotIn('raspi-config',self.log.read_text())

    def test_legacy_x11_flag_does_not_reconfigure_desktop(self):
        self.env.update(XDG_SESSION_TYPE='wayland')
        result=self.run_installer('--configure-x11')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('no longer needed',result.stdout)
        self.assertNotIn('raspi-config',self.log.read_text())

    def test_headless_schedules_setup_at_desktop_login(self):
        self.env['DISPLAY']=''
        result=self.run_installer()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((self.base/'config/autostart/pi-gesture-mic-resume.desktop').exists())
        self.assertNotIn('runtime gesture_mouse_pi.py',self.log.read_text())

    def test_failed_prerequisites_stop_launch(self):
        self.env['FAIL_SUDO']='1'
        result=self.run_installer()
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('runtime',self.log.read_text())
        self.assertIn('Setup failed',result.stdout+result.stderr)

    def test_no_launch_and_opt_in_autostart(self):
        result=self.run_installer('--no-launch','--autostart')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue((self.base/'config/autostart/gesture-control-pi.desktop').exists())
        self.assertNotIn('runtime gesture_mouse_pi.py',self.log.read_text())

    def test_invalid_option_rejected_before_changes(self):
        result=self.run_installer('--invalid')
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.log.exists())


class DesktopEntryTests(unittest.TestCase):
    def test_quoting_does_not_treat_paths_as_commands(self):
        from tools.desktop_entry import exec_quote
        value=exec_quote('/a folder/$HOME/`name`/100%/run.sh')
        self.assertTrue(value.startswith('"') and value.endswith('"'))
        self.assertIn('100%%',value)
        self.assertIn('\\\\$',value)
        self.assertIn('\\\\`',value)
        with self.assertRaises(ValueError): exec_quote('/a\nb')
