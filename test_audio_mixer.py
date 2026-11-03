import unittest
from unittest import mock

import numpy

import audio_mixer


def stereo(*values):
    return numpy.array([[value, value] for value in values], dtype=numpy.int16)


def fake_voice(block, finished=False):
    voice = mock.Mock()
    voice.next_block.return_value = numpy.asarray(block, dtype=numpy.float32)
    voice.finished = finished
    return voice


class EffectVoiceTest(unittest.TestCase):
    def test_returns_successive_blocks_of_the_sample(self):
        voice = audio_mixer.EffectVoice(stereo(1, 2, 3, 4))

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(1, 2))
        numpy.testing.assert_array_equal(voice.next_block(2), stereo(3, 4))
        self.assertTrue(voice.finished)

    def test_pads_the_last_block_with_silence(self):
        voice = audio_mixer.EffectVoice(stereo(1, 2, 3))
        voice.next_block(2)

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(3, 0))
        self.assertTrue(voice.finished)

    def test_is_not_finished_while_frames_remain(self):
        voice = audio_mixer.EffectVoice(stereo(1, 2, 3))

        voice.next_block(2)

        self.assertFalse(voice.finished)

    def test_empty_sample_is_finished_and_silent(self):
        voice = audio_mixer.EffectVoice(numpy.zeros((0, 2), dtype=numpy.int16))

        self.assertTrue(voice.finished)
        numpy.testing.assert_array_equal(voice.next_block(2), stereo(0, 0))


class MusicVoiceTest(unittest.TestCase):
    def test_plays_at_normal_speed_with_ratio_one(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20, 30, 40), ratio=1.0)

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(0, 10))
        numpy.testing.assert_array_equal(voice.next_block(2), stereo(20, 30))

    def test_interpolates_between_frames_when_slowed(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20), ratio=0.5)

        numpy.testing.assert_array_equal(voice.next_block(4), stereo(0, 5, 10, 15))

    def test_skips_frames_when_sped_up(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20, 30, 40, 50), ratio=2.0)

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(0, 20))

    def test_carries_fractional_position_across_blocks(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20, 30, 40), ratio=1.5)
        voice.next_block(1)

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(15, 30))

    def test_uses_a_changed_ratio_from_the_current_position(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20, 30, 40), ratio=1.0)
        voice.next_block(1)

        voice.ratio = 2.0

        numpy.testing.assert_array_equal(voice.next_block(2), stereo(10, 30))

    def test_pads_with_silence_and_finishes_at_the_end(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20), ratio=1.0)

        numpy.testing.assert_array_equal(voice.next_block(4), stereo(0, 10, 0, 0))
        self.assertTrue(voice.finished)

    def test_is_not_finished_while_frames_remain(self):
        voice = audio_mixer.MusicVoice(stereo(0, 10, 20, 30), ratio=1.0)

        voice.next_block(1)

        self.assertFalse(voice.finished)

    def test_sample_shorter_than_two_frames_is_finished_and_silent(self):
        voice = audio_mixer.MusicVoice(stereo(7), ratio=1.0)

        self.assertTrue(voice.finished)
        numpy.testing.assert_array_equal(voice.next_block(2), stereo(0, 0))


class MixerTest(unittest.TestCase):
    def test_sums_all_voices_into_one_int16_block(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "EffectVoice", side_effect=[fake_voice(stereo(1, 2)), fake_voice(stereo(10, 20))]), \
             mock.patch.object(audio_mixer, "MusicVoice", return_value=fake_voice(stereo(100, 200))):
            mixer.play_effect("fake-effect-a", "fake-samples-a")
            mixer.play_effect("fake-effect-b", "fake-samples-b")
            mixer.start_music("fake-music", "fake-song", ratio=1.0)

        result = mixer.next_block(2)

        self.assertEqual(result.block.dtype, numpy.int16)
        numpy.testing.assert_array_equal(result.block, stereo(111, 222))

    def test_returns_silence_with_no_voices(self):
        result = audio_mixer.Mixer().next_block(2)

        numpy.testing.assert_array_equal(result.block, stereo(0, 0))
        self.assertEqual(result.finished_music, [])

    def test_clips_the_sum_to_the_int16_range(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "EffectVoice", side_effect=[fake_voice(stereo(30000, -30000)), fake_voice(stereo(30000, -30000))]):
            mixer.play_effect("fake-effect-a", "fake-samples")
            mixer.play_effect("fake-effect-b", "fake-samples")

        numpy.testing.assert_array_equal(mixer.next_block(2).block, stereo(32767, -32768))

    def test_creates_voices_from_the_given_samples(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "EffectVoice") as effect_voice, \
             mock.patch.object(audio_mixer, "MusicVoice") as music_voice:
            mixer.play_effect("fake-effect", "fake-effect-samples")
            mixer.start_music("fake-music", "fake-song", ratio=1.3)

        effect_voice.assert_called_once_with("fake-effect-samples")
        music_voice.assert_called_once_with("fake-song", ratio=1.3)

    def test_drops_finished_effects_after_mixing_their_last_block(self):
        mixer = audio_mixer.Mixer()
        finishing_voice = fake_voice(stereo(5, 5), finished=True)
        with mock.patch.object(audio_mixer, "EffectVoice", return_value=finishing_voice):
            mixer.play_effect("fake-effect", "fake-samples")

        numpy.testing.assert_array_equal(mixer.next_block(2).block, stereo(5, 5))
        numpy.testing.assert_array_equal(mixer.next_block(2).block, stereo(0, 0))
        self.assertEqual(finishing_voice.next_block.call_count, 1)

    def test_reports_and_drops_finished_music(self):
        mixer = audio_mixer.Mixer()
        finishing_voice = fake_voice(stereo(5, 5), finished=True)
        with mock.patch.object(audio_mixer, "MusicVoice", return_value=finishing_voice):
            mixer.start_music("fake-music", "fake-song", ratio=1.0)

        self.assertEqual(mixer.next_block(2).finished_music, ["fake-music"])
        self.assertEqual(mixer.next_block(2).finished_music, [])

    def test_stop_effect_stops_every_voice_of_that_effect(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "EffectVoice", side_effect=[fake_voice(stereo(1, 1)), fake_voice(stereo(1, 1)), fake_voice(stereo(10, 10))]):
            mixer.play_effect("fake-effect-a", "fake-samples")
            mixer.play_effect("fake-effect-a", "fake-samples")
            mixer.play_effect("fake-effect-b", "fake-samples")

        mixer.stop_effect("fake-effect-a")

        numpy.testing.assert_array_equal(mixer.next_block(2).block, stereo(10, 10))

    def test_stop_effect_ignores_an_effect_that_is_not_playing(self):
        mixer = audio_mixer.Mixer()

        mixer.stop_effect("fake-effect")

        numpy.testing.assert_array_equal(mixer.next_block(1).block, stereo(0))

    def test_starting_music_replaces_the_track_already_playing(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "MusicVoice", side_effect=[fake_voice(stereo(1, 1)), fake_voice(stereo(7, 7))]):
            mixer.start_music("fake-music", "fake-song-a", ratio=1.0)
            mixer.start_music("fake-music", "fake-song-b", ratio=1.0)

        numpy.testing.assert_array_equal(mixer.next_block(2).block, stereo(7, 7))

    def test_stop_music_silences_that_track_without_reporting_it_finished(self):
        mixer = audio_mixer.Mixer()
        with mock.patch.object(audio_mixer, "MusicVoice", return_value=fake_voice(stereo(1, 1))):
            mixer.start_music("fake-music", "fake-song", ratio=1.0)

        mixer.stop_music("fake-music")
        result = mixer.next_block(2)

        numpy.testing.assert_array_equal(result.block, stereo(0, 0))
        self.assertEqual(result.finished_music, [])

    def test_stop_music_ignores_a_track_that_is_not_playing(self):
        mixer = audio_mixer.Mixer()

        mixer.stop_music("fake-music")

        numpy.testing.assert_array_equal(mixer.next_block(1).block, stereo(0))

    def test_set_music_ratio_changes_the_playing_track(self):
        mixer = audio_mixer.Mixer()
        voice = fake_voice(stereo(1, 1))
        with mock.patch.object(audio_mixer, "MusicVoice", return_value=voice):
            mixer.start_music("fake-music", "fake-song", ratio=1.0)

        mixer.set_music_ratio("fake-music", 1.4)

        self.assertEqual(voice.ratio, 1.4)

    def test_set_music_ratio_ignores_a_track_that_is_not_playing(self):
        mixer = audio_mixer.Mixer()

        mixer.set_music_ratio("fake-music", 1.4)

        numpy.testing.assert_array_equal(mixer.next_block(1).block, stereo(0))


if __name__ == "__main__":
    unittest.main()
