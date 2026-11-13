# USB microphone on Raspberry Pi 5

The USB microphone is separate from camera tracking; audio capture is not yet fed into speech recognition. Many webcams have their own USB microphone, which may appear in the list alongside a standalone mic.

## Detect

```bash
sudo apt install -y alsa-utils
./check_microphone.sh
arecord -l
wpctl status
```

`arecord -l` shows ALSA **card/device** numbers. `wpctl status` shows separate **PipeWire source IDs**. Do not interchange them.

## Record and listen

For example, with ALSA card 2, device 0:

```bash
arecord -D plughw:2,0 -f S16_LE -r 16000 -c 1 -d 5 ~/mic-test.wav
aplay ~/mic-test.wav
```

If recording fails, check actual card/device and supported formats. `plughw` may resample to a supported device format. Make sure playback speakers/TV audio are available.

## Default desktop input

Find USB mic under `Sources` in `wpctl status`, then:

```bash
wpctl set-default SOURCE_ID
wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 0.8
wpctl set-mute @DEFAULT_AUDIO_SOURCE@ 0
pw-record ~/mic-pipewire-test.wav
# Speak and press Ctrl+C
pw-play ~/mic-pipewire-test.wav
```

Replace `SOURCE_ID` with the PipeWire source number for your microphone. In Chromium, grant mic permission for your trusted web application. Browser permissions are separate from ALSA/PipeWire selection.

Speech-to-text, wake words, push-to-talk, and voice command routing are future features, not part of this release.
