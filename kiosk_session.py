"""Cage child: supervise gestures and Chromium in the same Wayland/audio session."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from profiles import config_home, state_home

ROOT = Path(__file__).resolve().parent


def web_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise argparse.ArgumentTypeError('Use an http:// or https:// application URL without embedded credentials')
    return value


def stop_child(child):
    if child is None:
        return
    # Each child has its own process group; never stop other browser sessions.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        child.wait(timeout=3)
        return
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # The parent can exit before its helpers. Reap any remaining members of
    # this owned group even when waiting for the parent succeeded.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=3)


def supervise(controller_args, browser_args, ready_file, log, timeout=45):
    controller = browser = None
    ready_file = Path(ready_file)
    try:
        controller = subprocess.Popen(controller_args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
        deadline = time.monotonic()+timeout
        while True:
            if controller.poll() is not None:
                raise RuntimeError('Gesture startup failed. See kiosk-gesture.log; Chromium was not started.')
            if ready_file.exists():
                status = json.loads(ready_file.read_text())
                if status.get('ready') is not True or status.get('backend') != 'uinput':
                    raise RuntimeError('Gesture controller returned an invalid kiosk readiness response')
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Gesture startup timed out. Check camera, calibration and /dev/uinput permissions.')
            time.sleep(.1)
        print(f'Microphone: {status.get("microphone", "system default")}', flush=True)
        print('Gestures ready. Thumb + pinky selects your controlling hand.', flush=True)
        print('For voice, use the webpage microphone button and allow access when requested.', flush=True)
        browser = subprocess.Popen(browser_args, cwd=ROOT, start_new_session=True)
        while True:
            if controller.poll() is not None:
                raise RuntimeError('Gesture controller stopped; closing the kiosk. See kiosk-gesture.log.')
            result = browser.poll()
            if result is not None:
                return result
            time.sleep(.15)
    finally:
        try:
            stop_child(browser)
        finally:
            stop_child(controller)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url',type=web_url)
    parser.add_argument('--browser',required=True)
    parser.add_argument('--profile',help='Saved calibrated gesture profile (default: active profile)')
    args=parser.parse_args()
    if not os.environ.get('WAYLAND_DISPLAY'):
        raise RuntimeError('Launch through bash start_alt_kiosk.sh URL so both processes inherit Cage.')
    parsed=urlsplit(args.url)
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost','127.0.0.1','::1'):
        print('Voice note: browser microphone capture normally requires HTTPS or localhost.',flush=True)
    # A TTY-launched Cage may inherit XDG_SESSION_TYPE=tty; the child's socket is Wayland.
    os.environ['XDG_SESSION_TYPE']='wayland'
    os.environ['PYTHONUNBUFFERED']='1'
    state=state_home(); state.mkdir(parents=True,exist_ok=True)
    lock=(state/'kiosk.lock').open('a+')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError('A gesture kiosk is already running for this account.') from exc
    profile_dir=config_home()/'chromium-kiosk'
    profile_dir.mkdir(parents=True,exist_ok=True)
    browser_args=[args.browser,'--ozone-platform=wayland',f'--user-data-dir={profile_dir}',
                  '--kiosk','--no-first-run','--disable-session-crashed-bubble',
                  '--disable-background-mode',args.url]
    # Do not auto-grant mic/camera globally. Chromium stores the site's normal
    # microphone consent in this persistent, dedicated browser profile.
    log_path=state/'kiosk-gesture.log'
    if log_path.exists():
        log_path.replace(log_path.with_suffix('.log.1'))
    def stopped(_signum,_frame):
        raise KeyboardInterrupt
    previous={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig,stopped)
    try:
        with tempfile.TemporaryDirectory(prefix='kiosk-',dir=state) as temporary, log_path.open('w') as log:
            ready=Path(temporary)/'ready.json'
            command=[sys.executable,'-u',str(ROOT/'gesture_mouse_pi.py'),'--kiosk','--ready-file',str(ready)]
            if args.profile:
                command += ['--profile',args.profile]
            print(f'Gesture startup log: {log_path}',flush=True)
            return supervise(command,browser_args,ready,log)
    except KeyboardInterrupt:
        return 0
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)
        lock.close()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'Gesture kiosk: {exc}',file=sys.stderr)
        raise SystemExit(1)
