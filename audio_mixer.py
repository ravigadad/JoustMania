"""Mixes effects and variable-speed music into blocks of 16-bit stereo audio."""
from collections import namedtuple

import numpy

MixResult = namedtuple("MixResult", ["block", "finished_music"])


class EffectVoice:
    def __init__(self, samples):
        self.samples = samples
        self.position = 0

    @property
    def finished(self):
        return self.position >= len(self.samples)

    def next_block(self, frame_count):
        block = numpy.zeros((frame_count, 2), dtype=numpy.float32)
        frames = self.samples[self.position:self.position + frame_count]
        block[:len(frames)] = frames
        self.position += frame_count
        return block


class MusicVoice:
    """Plays a song at a changeable speed by stepping through it at `ratio` frames per
    output frame and interpolating between neighbouring frames. Speed and pitch change
    together, as the game has always done."""

    def __init__(self, samples, ratio):
        self.samples = samples
        self.ratio = ratio
        self.position = 0.0

    @property
    def finished(self):
        return self.position >= len(self.samples) - 1

    def next_block(self, frame_count):
        positions = self.position + self.ratio * numpy.arange(frame_count)
        self.position += self.ratio * frame_count
        block = numpy.zeros((frame_count, 2), dtype=numpy.float32)
        # Interpolation reads the frame after each position, so the last frame can
        # only be reached as that neighbour.
        playable = positions < len(self.samples) - 1
        indexes = positions[playable].astype(numpy.int64)
        fractions = (positions[playable] - indexes)[:, numpy.newaxis]
        block[playable] = self.samples[indexes] * (1 - fractions) + self.samples[indexes + 1] * fractions
        return block


class Mixer:
    def __init__(self):
        self.effect_voices = []
        self.music_voices = {}

    def play_effect(self, effect_key, samples):
        self.effect_voices.append((effect_key, EffectVoice(samples)))

    def stop_effect(self, effect_key):
        self.effect_voices = [(key, voice) for key, voice in self.effect_voices if key != effect_key]

    def start_music(self, music_name, samples, ratio):
        self.music_voices[music_name] = MusicVoice(samples, ratio=ratio)

    def stop_music(self, music_name):
        self.music_voices.pop(music_name, None)

    def set_music_ratio(self, music_name, ratio):
        voice = self.music_voices.get(music_name)
        if voice is not None:
            voice.ratio = ratio

    def next_block(self, frame_count):
        mix = numpy.zeros((frame_count, 2), dtype=numpy.float32)
        for _, voice in self.effect_voices:
            mix += voice.next_block(frame_count)
        for voice in self.music_voices.values():
            mix += voice.next_block(frame_count)
        self.effect_voices = [(key, voice) for key, voice in self.effect_voices if not voice.finished]
        finished_music = [name for name, voice in self.music_voices.items() if voice.finished]
        for name in finished_music:
            del self.music_voices[name]
        return MixResult(numpy.clip(mix, -32768, 32767).astype(numpy.int16), finished_music)
