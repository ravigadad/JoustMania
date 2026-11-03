"""Plays sound on Windows: effects through pygame's mixer and each music track through
its own PyAudio stream. Windows mixes streams from separate processes itself, so this
code doesn't need Linux's single audio engine."""
import asyncio
import subprocess
import logging
import wave
import functools
import numpy
import os
import time
import scipy.signal as signal

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
import random
import glob
import setproctitle

import pyaudio
from multiprocessing import Process, Value, Array, Queue, Manager

import common
from robot_voice import render_robot_voice

# The min and max timeframe in seconds for
# the speed change to trigger, randomly selected
MIN_MUSIC_FAST_TIME = 4
MAX_MUSIC_FAST_TIME = 8
MIN_MUSIC_SLOW_TIME = 10
MAX_MUSIC_SLOW_TIME = 23

END_MIN_MUSIC_FAST_TIME = 6
END_MAX_MUSIC_FAST_TIME = 10
END_MIN_MUSIC_SLOW_TIME = 8
END_MAX_MUSIC_SLOW_TIME = 12


def resample_stereo_s16(data, ratio):
    """Resample interleaved stereo 16-bit PCM data by a playback ratio."""
    if ratio <= 0:
        raise ValueError("Audio playback ratio must be greater than zero")

    samples = numpy.frombuffer(data, dtype=numpy.int16)
    if samples.size % 2:
        raise ValueError("Stereo PCM data must contain complete sample pairs")

    # Divide by two for stereo, then round down to a multiple of 32 because
    # scipy's FFT resampler is more efficient near power-of-two sizes.
    num_output_frames = int(samples.size / (ratio * 2)) & (~0x1f)
    if num_output_frames <= 0:
        return b""

    left = signal.resample(samples[0::2], num_output_frames)
    right = signal.resample(samples[1::2], num_output_frames)

    output = numpy.empty((num_output_frames, 2))
    output[:, 0] = left
    output[:, 1] = right
    return output.astype(numpy.int16).tobytes()


def win_audio_loop(fname,ratio,stop_proc):
    p = pyaudio.PyAudio()
    #define stream chunk
    chunk = 1024

    #open a wav format music
    while(True):
        if(stop_proc.value):
            pass
        elif(fname['song'] != ''):
            # print(fname['song'])
            f = wave.open(random.choice(glob.glob(fname['song'])))
            #instantiate PyAudio

            #open stream
            stream = p.open(format = p.get_format_from_width(f.getsampwidth()),
                            channels = f.getnchannels(),
                            rate = f.getframerate(),
                            output = True)

            #read data
            data = f.readframes(chunk)

            #play stream
            while data:
                stream.write(data)
                data = f.readframes(chunk)
                if data:
                    data = resample_stereo_s16(data, ratio.value)
                if stop_proc.value:
                    stream.stop_stream()
                    stream.close()
                    break



            #stop stream
            stream.stop_stream()
            stream.close()
            #
            # #close PyAudio
            # p.terminate()



@functools.lru_cache(maxsize=128)
class Audio:
    def __init__(self, fname):
        setproctitle.setproctitle(f"JoustMania-Audio({fname})")
        #these are probably not necessary
        #segment = AudioSegment.from_file(fname)
        #buf = io.BytesIO()
        #segment.export(buf, 'wav')
        #buf.seek(0)
        self.sample_ = pygame.mixer.Sound(file=fname)
        self.fname_ = fname

    #this will not work for files other than wav at the moment
    def start_effect(self):
        self.sample_.play()

    def stop_effect(self):
        self.sample_.stop()

    def start_effect_music(self):
        self.sample_.play(-1)

    def stop_effect_music(self):
        self.sample_.stop()

    def get_length_secs(self):
        return self.sample_.get_length()

    def start_effect_and_wait(self):
        self.start_effect()
        time.sleep(self.get_length_secs())

@functools.lru_cache(maxsize=16)
class Music:
    def __init__(self, name):
        setproctitle.setproctitle(f"JoustMania-Music({name})")
    
        self.name = name
        self.transition_future_ = asyncio.Future()

        self.stop_proc = Value('i', 1)
        self.ratio = Value('d' , 1.0)
        manager = Manager()
        self.fname = manager.dict()
        self.fname['song'] = ''
        self.t = Process(target=win_audio_loop, args=(self.fname, self.ratio, self.stop_proc))
        self.t.start()


    def load_audio(self, fname):
        self.fname['song'] = fname

    def start_audio_loop(self):
        self.stop_proc.value = 0

    def stop_audio(self):
        self.stop_proc.value = 1
        self.fname['song'] = ''
        time.sleep(0.1)
        self.transition_future_.cancel()

    def change_ratio(self, ratio):
        self.ratio.value = ratio

    def transition_ratio(self, new_ratio, transition_duration=1.0):
        """Smoothly transitions between the current sampling ratio and the given one.
           Returns a task that completes once the transition is finished."""
        async def do_transition():
            num_steps = 20
            old_ratio = self.ratio.value
            for i in range(num_steps):
                t = (i+1) / 20
                ratio = common.lerp(old_ratio, new_ratio, t)
                ratio = old_ratio * (1-t) + new_ratio * t
                self.change_ratio(ratio)
                await asyncio.sleep(transition_duration / num_steps)

        self.transition_future_.cancel()
        self.transition_future_ = asyncio.ensure_future(do_transition())
        return self.transition_future_

class DummyMusic:
    def start_audio_loop(self): pass
    def stop_audio(self): pass
    def change_ratio(self): pass
    def transition_ratio(self, new_ratio, transition_duration=None):
        async def do_nothing(): pass
        return asyncio.ensure_future(do_nothing())

def InitAudio():
    pygame.mixer.init(47000, -16, 2 , 4096)


@functools.lru_cache(maxsize=16)
def _robot_voice_sample(message):
    wav = render_robot_voice(message)
    if wav is None:
        return None
    return pygame.mixer.Sound(file=wav)


def speak(message):
    """Play robot speech through the same mixer/output as game effects."""
    try:
        sample = _robot_voice_sample(message)
        if sample is not None:
            sample.play()
    except (OSError, subprocess.SubprocessError, pygame.error) as error:
        logging.getLogger(__name__).warning("Robot voice unavailable: %s", error)
