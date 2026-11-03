"""Plays sound on Linux by sending requests to the audio engine process, which owns
the sound card."""
import asyncio
import functools
import logging
import multiprocessing
import subprocess
import time

from scipy.io import wavfile

import audio_engine
from audio_samples import load_sample
from robot_voice import render_robot_voice

logger = logging.getLogger(__name__)

_commands = None


def InitAudio():
    """Starts the audio engine. Processes forked afterwards inherit its command queue."""
    global _commands
    if _commands is not None:
        return
    _commands = multiprocessing.Queue()
    multiprocessing.Process(target=audio_engine.run_engine, args=(_commands, None), daemon=True).start()


def set_output(card):
    """Switches the engine to an ALSA card id, or to the automatic choice for None."""
    _send(("set_output", card))


def _send(command):
    if _commands is None:
        raise RuntimeError("InitAudio() must run before any sound is played")
    _commands.put(command)


class Audio:
    def __init__(self, fname):
        self.fname = fname
        _send(("preload_effect", fname))

    def start_effect(self):
        _send(("play_effect", self.fname))

    def stop_effect(self):
        _send(("stop_effect", self.fname))

    def get_length_secs(self):
        rate, data = wavfile.read(self.fname, mmap=True)
        return len(data) / rate

    def start_effect_and_wait(self):
        self.start_effect()
        time.sleep(self.get_length_secs())


@functools.lru_cache(maxsize=16)
class Music:
    def __init__(self, name):
        self.name = name
        self.pattern = None
        self.ratio = 1.0
        self.transition_future_ = None

    def load_audio(self, pattern):
        self.pattern = pattern

    def start_audio_loop(self):
        if self.pattern is None:
            return
        _send(("start_music", self.name, self.pattern, self.ratio))

    def stop_audio(self):
        _send(("stop_music", self.name))
        self._cancel_transition()

    def change_ratio(self, ratio):
        self.ratio = ratio
        _send(("set_music_ratio", self.name, ratio))

    def transition_ratio(self, new_ratio, transition_duration=1.0):
        """Smoothly transitions between the current sampling ratio and the given one.
           Returns a task that completes once the transition is finished."""
        async def do_transition():
            num_steps = 20
            old_ratio = self.ratio
            for i in range(num_steps):
                t = (i + 1) / num_steps
                self.change_ratio(old_ratio * (1 - t) + new_ratio * t)
                await asyncio.sleep(transition_duration / num_steps)

        self._cancel_transition()
        self.transition_future_ = asyncio.ensure_future(do_transition())
        return self.transition_future_

    def _cancel_transition(self):
        if self.transition_future_ is not None:
            self.transition_future_.cancel()


def speak(message):
    """Plays robot speech through the same engine as game effects."""
    try:
        samples = _robot_voice_samples(message)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        logger.warning("Robot voice unavailable: %s", error)
        return
    if samples is not None:
        _send(("play_samples", "robot-voice", samples))


@functools.lru_cache(maxsize=16)
def _robot_voice_samples(message):
    wav = render_robot_voice(message)
    if wav is None:
        return None
    return load_sample(wav)
