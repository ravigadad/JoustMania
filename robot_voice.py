"""Renders robot speech with espeak for announcements that have no recorded voice file."""
import io
import shutil
import subprocess
import tempfile
import wave

import numpy


def render_robot_voice(message):
    """Returns the spoken message as an in-memory WAV file, or None when neither espeak
    nor espeak-ng is installed."""
    engine = shutil.which("espeak") or shutil.which("espeak-ng")
    if not engine:
        return None
    # stdout WAV headers use an unknown length, which SDL can interpret as
    # a huge allocation. A file gives espeak a seekable, correctly sized WAV.
    with tempfile.NamedTemporaryFile(suffix=".wav") as output:
        subprocess.run(
            [engine, "-w", output.name, "-ven", "-p", "70", message],
            capture_output=True, check=True, timeout=5,
        )
        # Some USB speakers stay asleep through digital silence. A quiet
        # attention tone wakes the output before the first spoken syllable.
        with wave.open(output.name, "rb") as source:
            params = source.getparams()
            frames = source.readframes(source.getnframes())
        padded = io.BytesIO()
        with wave.open(padded, "wb") as target:
            target.setparams(params)
            tone_frames = int(params.framerate * 0.3)
            phase = numpy.arange(tone_frames) / params.framerate
            envelope = numpy.minimum(phase / 0.02, (0.3 - phase) / 0.02).clip(0, 1)
            tone = (numpy.sin(2 * numpy.pi * 660 * phase) * envelope * 2500).astype('<i2')
            target.writeframes(tone.tobytes())
            target.writeframes(bytes(int(params.framerate * 0.4) * params.nchannels * params.sampwidth))
            target.writeframes(frames)
        padded.seek(0)
        return padded
