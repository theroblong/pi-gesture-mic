# USB microphone

Plug in a USB Audio Class microphone before opening Setup. Its descriptive desktop input appears in the Microphone selector. Source names are persisted instead of ephemeral PipeWire numeric IDs. Selecting a source makes it the desktop default and unmutes it; the volume is left unchanged. The selected source is reapplied on launch, including after a reboot when available.

**Test microphone** explicitly records four seconds through the selected desktop source, plays it through the desktop output, reports RMS level/clipping, and deletes the temporary WAV. There is no background application audio recording. If no input is connected, keep the system default and continue gesture setup; the microphone is optional.

If a saved microphone is missing on launch, the controller warns and continues gestures. Open Setup to select a replacement. Desktop audio requires the logged-in user's PipeWire/PulseAudio session. The installer adds audio utilities; it does not replace the OS sound server or overwrite `.asoundrc`.

```bash
bash check_microphone.sh         # USB, ALSA and desktop audio inventory
bash check_microphone.sh --test  # explicit four-second test of the current default
```

For low/clipped audio, adjust the desktop microphone level and repeat the test. If capture works but playback is silent, check the HDMI/speaker output device and volume. When using Chromium, select/allow the microphone in the site's permission prompt; system default selection does not grant browser permission. Remote sites generally need HTTPS (localhost is an exception).

**No speech-to-text, wake word or voice-command service is included.** This product configures and validates the capture device for other desktop/browser applications.
