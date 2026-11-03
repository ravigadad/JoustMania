"""Reads WAV files into the one format the audio engine mixes: 48 kHz stereo 16-bit."""
import math

import numpy
from scipy import signal
from scipy.io import wavfile

OUTPUT_RATE = 48000


def load_sample(path):
    """Returns the file's audio as an int16 array of shape (frames, 2) at OUTPUT_RATE."""
    source_rate, data = wavfile.read(path)
    return resample_to_output_rate(to_stereo(to_int16(data)), source_rate)


def to_int16(data):
    if data.dtype == numpy.int16:
        return data
    if data.dtype.kind == "f":
        return numpy.clip(numpy.round(data * 32767), -32768, 32767).astype(numpy.int16)
    if data.dtype == numpy.uint8:
        return ((data.astype(numpy.int16) - 128) << 8).astype(numpy.int16)
    if data.dtype == numpy.int32:
        return (data >> 16).astype(numpy.int16)
    raise ValueError(f"Unsupported WAV sample type: {data.dtype}")


def to_stereo(data):
    if data.ndim == 1:
        return numpy.column_stack((data, data))
    channel_count = data.shape[1]
    if channel_count == 1:
        return numpy.repeat(data, 2, axis=1)
    if channel_count == 2:
        return data
    raise ValueError(f"Unsupported channel count: {channel_count}")


def resample_to_output_rate(data, source_rate):
    if source_rate == OUTPUT_RATE:
        return data
    common_divisor = math.gcd(OUTPUT_RATE, source_rate)
    # The anti-aliasing filter rings past full scale on loud transients. Resampling in
    # floats and converting through to_int16 clips those peaks instead of letting them
    # wrap around to the opposite sign.
    resampled = signal.resample_poly(data / 32767, OUTPUT_RATE // common_divisor, source_rate // common_divisor, axis=0)
    return to_int16(resampled)
