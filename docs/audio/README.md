# Audio

[Back to the main README](../../README.md)

## Which output plays

On Linux, JoustMania plays through the first of these that exists:

1. A USB audio adapter.
2. A Raspberry Pi 4's headphone jack.
3. The system's default ALSA device. On a Raspberry Pi 5 without an adapter, this is the HDMI output the TV or monitor is connected to.

JoustMania doesn't need an `/etc/asound.conf`. When one exists, it only affects the third case.

The output is checked whenever the sound card is opened: at startup, and every few seconds while no card can be opened. An adapter plugged in after startup is used only after JoustMania restarts or loses its current output.

### Choosing an output

The **Audio Output** section of the web UI's debug page lists every sound card on the Pi and shows which one is playing. Choosing one switches to it straight away, without stopping a game, and saves it as `audio_output` in `joustsettings.yaml`, so it's used again after a restart. **Automatic** goes back to the order above.

A chosen output stays chosen. If it can't be opened, JoustMania plays nothing and keeps trying to open it every few seconds, then resumes on it once it's back. Meanwhile the debug page says it's waiting for that output. The log records the failure once, and again only if the error changes or after the output has opened in between.

An HDMI port can be opened only while a display is connected to it. The Pi's HDMI driver refuses to open a port with nothing attached, so choosing an empty port leaves JoustMania waiting.

## One process owns the sound card

On Linux, a single audio engine process opens the sound card and mixes everything the game plays: music, sound effects and robot speech. Game code asks for sound through `piaudio` (`Audio`, `Music` and `speak`), which sends requests to the engine over a queue. `InitAudio()` starts the engine, and every process forked after that can send it requests.

The engine exists because the Raspberry Pi's HDMI outputs can't be shared. Their hardware accepts audio only in the HDMI wire format (IEC958 subframes). ALSA's mixing plugin, dmix, can't mix in that format, so a second program trying to open the same HDMI output fails with "Device or resource busy". Mixing inside one process avoids the problem on every output, so USB adapters and the headphone jack don't need dmix either.

The engine opens each card through its `default:CARD=<card>` device. For HDMI, that device converts ordinary 16-bit audio into the wire format and handles any sample rate.

## How the engine plays sound

The engine runs a loop: apply waiting requests, mix one block of about 21 ms, and write it to the card. Writing waits until the card has room, so the card's own playback rate sets the pace. When no card can be opened, the engine waits one block's worth of time in its place and keeps trying to open the card every few seconds, so effects and music keep their timing.

Every file is converted once, when it's loaded, to 48 kHz 16-bit stereo. Loading happens on a separate thread inside the engine, so reading a long song doesn't interrupt playback. Effects stay in memory after their first load. Songs are loaded when a music track needs one and released when it ends.

Music speed changes during games by stepping through the song faster or slower and interpolating between neighbouring samples. Pitch changes with speed, which is how the game has always sounded. A music track keeps its list of songs when it stops, so the next game that starts it plays music again.

## Windows

Windows keeps its own playback in `windows_audio.py`: effects through pygame's mixer and each music track through its own PyAudio stream. Windows mixes streams from separate processes itself, so the engine's reason for existing doesn't apply there. `piaudio` picks the implementation for the platform it's running on.

## Approaches that don't work on the Pi's HDMI

- **Sharing the card through dmix.** dmix can't mix the HDMI wire format, as described above. The ALSA maintainers' advice for this hardware is to mix in a sound server or in the application.
- **pygame's mixer as the only owner.** SDL, which pygame uses, lists the Pi's HDMI outputs only by their raw hardware names. Opening one of those by name fails with "Unsupported audio format". Music would also have to be mixed in a callback inside the game process, so busy game logic could interrupt it.
- **PortAudio, through `sounddevice`.** It can't open a per-card device such as `default:CARD=vc4hdmi0` by name.
- **PipeWire.** It mixes and handles HDMI, but JoustMania runs as root under supervisor, outside the desktop user's session. A Pi running Raspberry Pi OS Lite has no PipeWire at all.
