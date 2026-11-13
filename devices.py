"""Bounded hardware discovery and audio diagnostics. No recording by default."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def command(args, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"{args[0]} failed")
    return result.stdout


def cameras():
    stable = sorted(Path('/dev/v4l/by-id').glob('*'))
    stable += sorted(Path('/dev/v4l/by-path').glob('*'))
    devices, seen = [], set()
    for path in stable + sorted(Path('/dev').glob('video*')):
        real = path.resolve()
        if real in seen:
            continue
        seen.add(real)
        try:
            info = command(['v4l2-ctl', '--device', str(path), '--all'], timeout=2)
            # Metadata and codec devices are not usable capture cameras.
            if 'Video Capture' not in info:
                continue
            name_path = Path('/sys/class/video4linux') / real.name / 'name'
            name = name_path.read_text().strip() if name_path.exists() else real.name
            devices.append((str(path), f'{name} ({real.name})'))
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            continue
    return devices


def microphones():
    # pactl's source.name is persistent; numeric PipeWire node IDs are not.
    sources = json.loads(command(['pactl', '-f', 'json', 'list', 'sources']))
    return [(s['name'], s.get('description', s['name'])) for s in sources
            if not s['name'].endswith('.monitor') and
            str(s.get('monitor_of_sink', '4294967295')) in ('4294967295', '-1', 'None')]


def select_microphone(name):
    if name:
        available = dict(microphones())
        if name not in available:
            raise RuntimeError('Saved microphone is unavailable. Reconnect it or choose another in Setup.')
        command(['pactl', 'set-default-source', name])
        command(['pactl', 'set-source-mute', name, '0'])


def stop_process(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def microphone_test(name, cancel=None):
    """Record only on explicit Test action, play back, then remove the WAV."""
    import tempfile
    import wave
    import array
    import math
    cancel = cancel or threading.Event()
    with tempfile.TemporaryDirectory(prefix='gesture-mic-') as folder:
        path = str(Path(folder) / 'test.wav')
        args = ['parecord', '--file-format=wav', '--rate=16000', '--channels=1', '--format=s16le']
        if name:
            args += ['--device', name]
        with subprocess.Popen(args + [path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as proc:
            deadline = time.monotonic()+4
            try:
                while time.monotonic() < deadline:
                    if cancel.wait(.05):
                        raise RuntimeError('Microphone test cancelled')
                    if proc.poll() is not None:
                        raise RuntimeError(proc.communicate()[1].decode().strip() or 'Recording ended early')
            finally:
                stop_process(proc)
        if cancel.is_set():
            raise RuntimeError('Microphone test cancelled')
        with wave.open(path, 'rb') as stream:
            data = array.array('h', stream.readframes(stream.getnframes()))
        if not data:
            raise RuntimeError('Microphone returned no audio')
        rms = math.sqrt(sum(v*v for v in data)/len(data))/32768
        peak = max(abs(v) for v in data)/32768
        with subprocess.Popen(['paplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as proc:
            deadline = time.monotonic()+10
            try:
                while proc.poll() is None:
                    if cancel.wait(.05):
                        raise RuntimeError('Microphone test cancelled')
                    if time.monotonic() > deadline:
                        raise RuntimeError('Playback timed out; check your audio output')
                if proc.returncode:
                    raise RuntimeError(proc.communicate()[1].decode().strip() or 'Playback failed')
            finally:
                stop_process(proc)
        return f'Playback complete | level {20*math.log10(max(rms, 1e-6)):.0f} dB | ' + (
            'Clipping: lower microphone volume' if peak > .99 else
            'Very quiet: move closer or raise input volume' if rms < .003 else 'Signal looks good')


class Camera:
    """Read on a daemon thread so unplugging a camera cannot freeze the UI."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.frame = None
        self.error = None
        self.last_delivered = None
        self.timestamp = time.monotonic()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        import cv2
        source = self.cfg.get('camera_device') or self.cfg['camera_index']
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        try:
            if not cap.isOpened():
                raise RuntimeError(f'Camera cannot open: {source}. Close other camera apps and check its cable.')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg['capture_width'])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg['capture_height'])
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while not self.stopped.is_set():
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError('Camera disconnected or stopped sending frames. Reconnect it and run Setup.')
                if self.cfg.get('mirror_camera', True):
                    frame = cv2.flip(frame, 1)
                self.frame, self.timestamp = frame, time.monotonic()
        except Exception as exc:
            self.error = str(exc)
        finally:
            cap.release()

    def read(self):
        if self.error:
            raise RuntimeError(self.error)
        if time.monotonic()-self.timestamp > 3:
            raise RuntimeError('Camera timed out. Reconnect it or select a different camera in Setup.')
        if self.frame is None or self.timestamp == self.last_delivered:
            return None
        self.last_delivered = self.timestamp
        return self.frame.copy()

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=.3)
