"""Desktop input selection and Linux uinput driver for Wayland sessions.

Wayland does not expose the global physical cursor position to this application.
Absolute movement is normalized to the single display; relative movement uses
kernel REL events. Only this app's last requested absolute position is cached.
"""
import os
import time


def session_backend(environ=None):
    env = os.environ if environ is None else environ
    if env.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or env.get('WAYLAND_DISPLAY'):
        return 'uinput'
    return 'x11'


def require_desktop(environ=None):
    env = os.environ if environ is None else environ
    if not env.get('DISPLAY'):
        if session_backend(env) == 'uinput':
            raise RuntimeError('Wayland input is supported, but the setup/preview windows need XWayland. '
                               'Run bash install_pi.sh from a terminal on the Pi desktop to install it.')
        raise RuntimeError('Open a terminal on the Pi desktop and run bash run_pi.sh --setup.')


def screen_size():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        return root.winfo_screenwidth(), root.winfo_screenheight()
    finally:
        root.destroy()


class UInputDriver:
    """Small PyAutoGUI-shaped driver, with native relative movement support.

Three separate devices avoid ambiguous mouse/tablet/keyboard classification.
No physical event devices are read or grabbed; application code runs unprivileged.
"""
    native_relative = True
    FAILSAFE = False  # Physical-cursor corner detection is unavailable on Wayland.
    PAUSE = 0

    class FailSafeException(Exception):
        pass

    def __init__(self, size=None, evdev_module=None, settle=True):
        if evdev_module is None:
            try:
                import evdev as evdev_module
            except ImportError as exc:
                raise RuntimeError('Wayland input dependency is missing. Run bash install_pi.sh.') from exc
        self.e = evdev_module.ecodes
        self.width, self.height = size or screen_size()
        if self.width < 2 or self.height < 2:
            raise ValueError('Cannot determine the display size')
        self.xy = [self.width/2, self.height/2]
        self.fraction = [0., 0.]
        self.held_buttons, self.held_keys = set(), set()
        self.devices = []
        self.closed = False
        e = self.e
        pointer_buttons = [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE]
        wheel_axes = [e.REL_WHEEL, e.REL_HWHEEL]
        axis = evdev_module.AbsInfo(value=0, min=0, max=65535, fuzz=0, flat=0, resolution=100)
        try:
            self.absolute = self._create(evdev_module,
                {e.EV_KEY: pointer_buttons, e.EV_ABS: [(e.ABS_X, axis), (e.ABS_Y, axis)],
                 e.EV_REL: wheel_axes},
                name='Gesture Control Absolute Pointer', input_props=[e.INPUT_PROP_POINTER])
            self.relative = self._create(evdev_module,
                {e.EV_KEY: pointer_buttons, e.EV_REL: [e.REL_X, e.REL_Y] + wheel_axes},
                name='Gesture Control Relative Pointer', input_props=[e.INPUT_PROP_POINTER])
            self.keyboard = self._create(evdev_module,
                {e.EV_KEY: list(range(e.KEY_ESC, e.KEY_MICMUTE + 1))},
                name='Gesture Control Keyboard')
            # Let udev and the compositor discover the new devices before use.
            # No pointer, key or button events are emitted during creation.
            if settle:
                time.sleep(.4)
        except Exception as exc:
            self.close()
            raise RuntimeError('Could not create Wayland input devices through /dev/uinput. '
                               'Run bash install_pi.sh from your local Pi desktop. '
                               f'Detail: {exc}') from exc

    def _create(self, module, capabilities, **kwargs):
        device = module.UInput(capabilities, bustype=self.e.BUS_USB, **kwargs)
        self.devices.append(device)
        return device

    def size(self):
        return self.width, self.height

    def position(self):
        return tuple(self.xy)

    def moveTo(self, x, y, duration=0):
        x = max(0, min(self.width-1, x))
        y = max(0, min(self.height-1, y))
        self.absolute.write(self.e.EV_ABS, self.e.ABS_X, round(x/(self.width-1)*65535))
        self.absolute.write(self.e.EV_ABS, self.e.ABS_Y, round(y/(self.height-1)*65535))
        self.absolute.syn()
        self.xy = [x, y]

    def moveRel(self, dx, dy, duration=0):
        values = [dx + self.fraction[0], dy + self.fraction[1]]
        whole = [int(v) for v in values]
        self.fraction = [v-i for v,i in zip(values,whole)]
        for code, value in zip((self.e.REL_X, self.e.REL_Y), whole):
            if value:
                self.relative.write(self.e.EV_REL, code, value)
        if any(whole):
            self.relative.syn()
        # This estimate is used only for a later transition to absolute mapping.
        # Relative motion itself never warps the pointer to this cached position.
        self.xy = [max(0, min(limit-1, p+d))
                   for p,d,limit in zip(self.xy, whole, (self.width,self.height))]

    def reanchor(self):
        self.fraction = [0., 0.]

    def _button_code(self, button):
        return {'left': self.e.BTN_LEFT, 'right': self.e.BTN_RIGHT,
                'middle': self.e.BTN_MIDDLE}[button]

    def mouseDown(self, button='left'):
        code = self._button_code(button)
        self.held_buttons.add(code)  # Remember before write so partial failures release.
        self.absolute.write(self.e.EV_KEY, code, 1)
        self.absolute.syn()

    def mouseUp(self, button='left'):
        code = self._button_code(button)
        self.absolute.write(self.e.EV_KEY, code, 0)
        self.absolute.syn()
        self.held_buttons.discard(code)

    def click(self, button='left'):
        try:
            self.mouseDown(button)
        finally:
            self.mouseUp(button)

    def doubleClick(self, interval=.12):
        self.click()
        time.sleep(interval)
        self.click()

    def _key_code(self, key):
        return {'ctrl': self.e.KEY_LEFTCTRL, '=': self.e.KEY_EQUAL, '-': self.e.KEY_MINUS}[key]

    def keyUp(self, key):
        code = self._key_code(key)
        self.keyboard.write(self.e.EV_KEY, code, 0)
        self.keyboard.syn()
        self.held_keys.discard(code)

    def hotkey(self, *keys):
        codes = [self._key_code(key) for key in keys]
        try:
            for code in codes:
                self.held_keys.add(code)
                self.keyboard.write(self.e.EV_KEY, code, 1)
                self.keyboard.syn()
        finally:
            first_error = None
            for code in reversed(codes):
                try:
                    self.keyboard.write(self.e.EV_KEY, code, 0)
                    self.keyboard.syn()
                    self.held_keys.discard(code)
                except OSError as exc:
                    first_error = first_error or exc
            if first_error:
                raise first_error

    def scroll(self, clicks):
        self.absolute.write(self.e.EV_REL, self.e.REL_WHEEL, int(clicks))
        self.absolute.syn()

    def hscroll(self, clicks):
        self.absolute.write(self.e.EV_REL, self.e.REL_HWHEEL, int(clicks))
        self.absolute.syn()

    def close(self):
        if self.closed:
            return
        self.closed = True
        for device_name, held in (('absolute', self.held_buttons), ('keyboard', self.held_keys)):
            device = getattr(self, device_name, None)
            if device is not None:
                for code in list(held):
                    try:
                        device.write(self.e.EV_KEY, code, 0)
                        device.syn()
                    except OSError:
                        pass
                held.clear()
        # Closing every descriptor also destroys the virtual devices on failure.
        for device in reversed(self.devices):
            try:
                device.close()
            except OSError:
                pass
        self.devices = []


def create_driver(backend):
    if backend == 'uinput':
        return UInputDriver()
    if backend == 'x11':
        import pyautogui
        return pyautogui
    raise ValueError(f'Unknown desktop input backend: {backend}')
