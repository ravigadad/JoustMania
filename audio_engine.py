"""The one process that owns the sound card. It mixes every effect, voice and music
track itself, because the Pi's HDMI outputs can't be shared between processes."""
import glob
import logging
import queue
import random
import time
from dataclasses import dataclass

import setproctitle

from audio_loader import SampleLoader
from audio_mixer import Mixer
from audio_output import AlsaOutput, OutputError, choose_card
from audio_samples import OUTPUT_RATE

logger = logging.getLogger(__name__)

BLOCK_FRAMES = 1024
OUTPUT_RETRY_SECONDS = 3.0


def run_engine(commands, configured_card):
    """Entry point for the engine process. configured_card is an ALSA card id, or None
    to use a USB adapter when one is present and the system default otherwise."""
    setproctitle.setproctitle("JoustMania-AudioEngine")
    AudioEngine(commands, configured_card).run()


@dataclass
class MusicTrack:
    pattern: str
    ratio: float
    generation: int = 0
    playing: bool = False


class AudioEngine:
    """Runs a loop that applies waiting commands, mixes one block and writes it. Writing
    blocks until the card has room, so the card's playback rate paces the loop."""

    def __init__(self, commands, configured_card):
        self.commands = commands
        self.configured_card = configured_card
        self.mixer = Mixer()
        self.loader = SampleLoader()
        self.output = None
        self.next_output_attempt = time.monotonic()
        self.last_output_error = None
        self.effect_samples = {}
        self.loading_effects = set()
        self.pending_effect_plays = {}
        self.music_tracks = {}

    def run(self):
        while self._apply_commands():
            self._apply_loaded()
            result = self.mixer.next_block(BLOCK_FRAMES)
            self._continue_music(result.finished_music)
            self._play(result.block)
        self._shutdown()

    def _apply_commands(self):
        """Handles every waiting command. Returns False once shutdown is requested."""
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                return True
            if command[0] == "shutdown":
                return False
            self._handle_command(command)

    def _handle_command(self, command):
        name, *arguments = command
        handler = {
            "preload_effect": self._preload_effect,
            "play_effect": self._play_effect,
            "stop_effect": self._stop_effect,
            "play_samples": self._play_samples,
            "start_music": self._start_music,
            "stop_music": self._stop_music,
            "set_music_ratio": self._set_music_ratio,
            "set_output": self._set_output,
        }.get(name)
        if handler is None:
            logger.error("Unknown audio command: %s", name)
            return
        handler(*arguments)

    def _preload_effect(self, path):
        self._request_effect(path)

    def _play_effect(self, path):
        samples = self.effect_samples.get(path)
        if samples is not None:
            self.mixer.play_effect(path, samples)
            return
        self.pending_effect_plays[path] = self.pending_effect_plays.get(path, 0) + 1
        self._request_effect(path)

    def _stop_effect(self, path):
        self.mixer.stop_effect(path)
        self.pending_effect_plays.pop(path, None)

    def _play_samples(self, key, samples):
        self.mixer.play_effect(key, samples)

    def _request_effect(self, path):
        if path in self.effect_samples or path in self.loading_effects:
            return
        self.loading_effects.add(path)
        self.loader.request(path, ("effect", path))

    def _start_music(self, music_name, pattern, ratio):
        previous = self.music_tracks.get(music_name)
        # A song requested before this start belongs to an older generation and is
        # dropped when it arrives.
        generation = previous.generation + 1 if previous else 1
        self.music_tracks[music_name] = MusicTrack(pattern, ratio, generation=generation, playing=True)
        self._request_next_song(music_name)

    def _stop_music(self, music_name):
        self.mixer.stop_music(music_name)
        track = self.music_tracks.get(music_name)
        if track is not None:
            track.playing = False
            track.generation += 1

    def _set_music_ratio(self, music_name, ratio):
        track = self.music_tracks.get(music_name)
        if track is None:
            return
        track.ratio = ratio
        self.mixer.set_music_ratio(music_name, ratio)

    def _request_next_song(self, music_name):
        track = self.music_tracks[music_name]
        songs = glob.glob(track.pattern)
        if not songs:
            logger.warning("No music matches %s", track.pattern)
            return
        self.loader.request(random.choice(songs), ("music", music_name, track.generation))

    def _continue_music(self, finished_music):
        for music_name in finished_music:
            track = self.music_tracks.get(music_name)
            if track is not None and track.playing:
                self._request_next_song(music_name)

    def _apply_loaded(self):
        for loaded in self.loader.completed():
            kind, *details = loaded.tag
            if kind == "effect":
                self._effect_loaded(loaded.path, loaded.samples)
            else:
                music_name, generation = details
                self._song_loaded(music_name, generation, loaded.path, loaded.samples)

    def _effect_loaded(self, path, samples):
        self.loading_effects.discard(path)
        waiting_plays = self.pending_effect_plays.pop(path, 0)
        if samples is None:
            return
        self.effect_samples[path] = samples
        for _ in range(waiting_plays):
            self.mixer.play_effect(path, samples)

    def _song_loaded(self, music_name, generation, path, samples):
        track = self.music_tracks.get(music_name)
        if track is None or track.generation != generation or samples is None:
            return
        logger.info("Playing %s on the %s music track", path, music_name)
        self.mixer.start_music(music_name, samples, ratio=track.ratio)

    def _set_output(self, card):
        self._close_output()
        self.configured_card = card
        self.next_output_attempt = time.monotonic()
        self.last_output_error = None

    def _current_output(self):
        if self.output is None and time.monotonic() >= self.next_output_attempt:
            card = choose_card(self.configured_card)
            try:
                self.output = AlsaOutput(card, period_frames=BLOCK_FRAMES)
                logger.info("Audio output opened on %s", card or "the system default device")
                self.last_output_error = None
            except OutputError as error:
                # A chosen output can stay unavailable for hours, so an unchanged
                # failure is logged once rather than on every retry.
                if str(error) != self.last_output_error:
                    logger.error("%s; retrying every %s seconds", error, OUTPUT_RETRY_SECONDS)
                    self.last_output_error = str(error)
                self.next_output_attempt = time.monotonic() + OUTPUT_RETRY_SECONDS
        return self.output

    def _play(self, block):
        output = self._current_output()
        if output is None:
            # Without a card to pace the loop, waiting one block's worth of time keeps
            # effects and music moving at their normal speed.
            time.sleep(BLOCK_FRAMES / OUTPUT_RATE)
            return
        try:
            output.write(block)
        except OutputError as error:
            logger.error("%s; reopening in %s seconds", error, OUTPUT_RETRY_SECONDS)
            self._close_output()
            self.next_output_attempt = time.monotonic() + OUTPUT_RETRY_SECONDS

    def _close_output(self):
        if self.output is not None:
            self.output.close()
            self.output = None

    def _shutdown(self):
        self._close_output()
        self.loader.stop()
