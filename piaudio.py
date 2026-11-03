"""Sound for the game. Linux plays everything through one audio engine process, because
the Pi's HDMI outputs can't be shared between processes. Windows keeps its pygame and
PyAudio playback."""
import runtime_platform

if runtime_platform.is_windows():
    from windows_audio import Audio, InitAudio, Music, speak
else:
    from audio_client import Audio, InitAudio, Music, speak

__all__ = ["Audio", "InitAudio", "Music", "speak"]
