"""Desktop profile/device setup. Imports GUI dependencies only when opened."""
import copy
import queue
import threading
from profiles import ProfileStore
from devices import Camera, cameras, microphones, microphone_test


def setup(store, selected=None):
    import tkinter as tk
    from tkinter import ttk, messagebox
    from PIL import Image, ImageTk
    import cv2
    root = tk.Tk()
    root.title('Gesture Control · Setup')
    root.geometry('1060x760')
    root.minsize(900, 690)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TFrame', background='#101b2d')
    style.configure('TLabel', background='#101b2d', foreground='#e9f1ff', font=('Sans', 11))
    style.configure('Title.TLabel', font=('Sans', 26, 'bold'))
    style.configure('TButton', padding=(14, 10), font=('Sans', 11))
    root.configure(background='#101b2d')
    body = ttk.Frame(root, padding=24)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Make the screen yours.', style='Title.TLabel').pack(anchor='w')
    ttk.Label(body, text='1  Profile & devices     /     2  Guided calibration     /     3  Ready to control').pack(anchor='w', pady=(6,18))
    form = ttk.Frame(body)
    form.pack(fill='x')
    name = tk.StringVar(value=selected or store.active())
    camera_var, mic_var = tk.StringVar(), tk.StringVar()
    mirror = tk.BooleanVar(value=True)
    fields = []
    for row, (title, var, values, state) in enumerate([
            ('Your profile', name, store.names() or ['Default'], 'normal'),
            ('Camera', camera_var, [], 'readonly'),
            ('Microphone', mic_var, [], 'readonly')]):
        ttk.Label(form, text=title).grid(row=row, column=0, sticky='w', padx=(0,20), pady=5)
        widget = ttk.Combobox(form, textvariable=var, values=values, state=state, width=63)
        widget.grid(row=row, column=1, sticky='ew', pady=5)
        fields.append(widget)
    form.columnconfigure(1, weight=1)
    preview = ttk.Label(body, text='Connecting to your camera…', anchor='center')
    preview.pack(fill='both', expand=True, pady=14)
    status = tk.StringVar(value='Choose an existing profile, or type a new name. Discovery is running…')
    ttk.Label(body, textvariable=status, wraplength=980).pack(fill='x', pady=8)
    ttk.Label(body, text='Place the camera near the screen. Keep both hands, wrists and fingertips visible.\nAudio is recorded only when you press Test microphone; the test is deleted after playback.', wraplength=980).pack(anchor='w')
    actions = ttk.Frame(body)
    actions.pack(fill='x', pady=(14,0))
    inbox = queue.Queue()
    audio_cancel = threading.Event()
    state = {'cfg': store.load(name.get()), 'camera': None, 'cameras': [], 'mics': [], 'result': None, 'busy': False}

    def background(kind, fn):
        def work():
            try:
                inbox.put((kind, fn(), None))
            except Exception as exc:
                inbox.put((kind, None, str(exc)))
        # Audio workers must finish process cleanup even when the window closes.
        threading.Thread(target=work, daemon=(kind != 'audio')).start()

    def close():
        audio_cancel.set()
        if state['camera']:
            state['camera'].close()
            state['camera'] = None
        root.destroy()

    def current_cfg():
        cfg = copy.deepcopy(state['cfg'])
        index = fields[1].current()
        if index < 0 or index >= len(state['cameras']):
            raise ValueError('Connect a USB camera and press Refresh devices')
        cfg['camera_device'] = state['cameras'][index][0]
        mic_index = fields[2].current()
        cfg['microphone_source'] = state['mics'][mic_index-1][0] if mic_index > 0 else None
        cfg['mirror_camera'] = mirror.get()
        if any(cfg.get(k) != state['cfg'].get(k) for k in ('camera_device','mirror_camera')):
            cfg['calibration'] = None
        return cfg

    def start_camera(*_):
        if state['camera']:
            state['camera'].close()
        try:
            state['camera'] = Camera(current_cfg())
        except ValueError as exc:
            state['camera'] = None
            status.set(str(exc))

    def apply_choices():
        cfg = state['cfg']
        fields[1]['values'] = [v[1] for v in state['cameras']]
        if state['cameras']:
            index = next((i for i,(key,_) in enumerate(state['cameras']) if key == cfg.get('camera_device')), 0)
            fields[1].current(index)
        else:
            camera_var.set('No capture camera found')
        fields[2]['values'] = ['Keep system default / no microphone'] + [v[1] for v in state['mics']]
        index = next((i+1 for i,(key,_) in enumerate(state['mics']) if key == cfg.get('microphone_source')), 0)
        fields[2].current(index)
        mirror.set(cfg.get('mirror_camera', True))
        start_camera()

    def load_profile(*_):
        try:
            state['cfg'] = store.load(name.get())
            apply_choices()
            status.set('Profile loaded. Calibrate after changing your camera position or seating.')
        except (ValueError, OSError) as exc:
            messagebox.showerror('Profile needs attention', str(exc))

    def discover():
        status.set('Looking for cameras and microphones…')
        def find():
            cams = cameras()
            try:
                return cams, microphones(), ''
            except Exception as exc:
                return cams, [], f'Audio discovery: {exc}. Gesture control can continue.'
        background('devices', find)

    def test_mic():
        if state['busy']:
            return
        state['busy'] = True
        audio_cancel.clear()
        test_button.state(['disabled'])
        status.set('Speak for four seconds. Your recording will then play back.')
        index = fields[2].current()
        source = state['mics'][index-1][0] if index > 0 else None
        background('audio', lambda: microphone_test(source, audio_cancel))

    def finish(calibrate):
        try:
            store.path(name.get())
            cfg = current_cfg()
            if not state['camera'] or state['camera'].frame is None:
                raise ValueError('Wait for a live camera picture before continuing')
            state['camera'].read()  # Checks disconnect/staleness even between frames.
            if not calibrate and not cfg.get('calibration'):
                raise ValueError('This profile needs guided calibration first')
            # Calibration is transactional: save after every practice step passes.
            state['result'] = (name.get(), cfg, calibrate)
            close()
        except Exception as exc:
            messagebox.showerror('Setup needs attention', str(exc))

    fields[0].bind('<<ComboboxSelected>>', load_profile)
    fields[0].bind('<FocusOut>', load_profile)
    fields[1].bind('<<ComboboxSelected>>', start_camera)
    ttk.Checkbutton(actions, text='Mirror camera', variable=mirror, command=start_camera).pack(side='left')
    ttk.Button(actions, text='Refresh devices', command=discover).pack(side='left', padx=6)
    test_button = ttk.Button(actions, text='Test microphone', command=test_mic)
    test_button.pack(side='left')
    ttk.Button(actions, text='Launch saved profile', command=lambda: finish(False)).pack(side='right', padx=6)
    ttk.Button(actions, text='Calibrate', command=lambda: finish(True)).pack(side='right')
    root.protocol('WM_DELETE_WINDOW', close)

    def tick():
        try:
            while True:
                kind, value, error = inbox.get_nowait()
                if kind == 'devices' and not error:
                    state['cameras'], state['mics'], warning = value
                    apply_choices()
                    status.set(warning or 'Devices ready. Check the preview, then choose Calibrate.')
                elif kind == 'audio':
                    state['busy'] = False
                    test_button.state(['!disabled'])
                    status.set(error or value)
                else:
                    status.set(error or str(value))
        except queue.Empty:
            pass
        if state['camera']:
            try:
                frame = state['camera'].read()
                if frame is not None:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    picture = Image.fromarray(frame)
                    picture.thumbnail((760, 340))
                    preview.image = ImageTk.PhotoImage(picture)
                    preview.configure(image=preview.image, text='')
            except RuntimeError as exc:
                status.set(str(exc))
                state['camera'].close()
                state['camera'] = None
                preview.configure(image='', text='Camera unavailable · reconnect and refresh')
        root.after(40, tick)
    discover()
    tick()
    import signal
    previous_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous_handlers:
        signal.signal(sig, lambda _sig, _frame: close())
    try:
        root.mainloop()
    finally:
        audio_cancel.set()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    return state['result']
