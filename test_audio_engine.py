import queue
import sys
import unittest
from unittest import mock

sys.modules.setdefault("alsaaudio", mock.MagicMock())

import audio_engine
from audio_loader import LoadedSample
from audio_mixer import MixResult
from audio_output import OutputError


class RunEngineTest(unittest.TestCase):
    def test_names_the_process_and_runs_an_engine_on_the_commands(self):
        with mock.patch.object(audio_engine, "setproctitle") as setproctitle, \
             mock.patch.object(audio_engine, "AudioEngine") as engine_class:
            audio_engine.run_engine("fake-commands", "fake-card")

        setproctitle.setproctitle.assert_called_once_with("JoustMania-AudioEngine")
        engine_class.assert_called_once_with("fake-commands", "fake-card")
        engine_class.return_value.run.assert_called_once_with()


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.commands = queue.Queue()
        self.patch("Mixer")
        self.patch("SampleLoader")
        self.patch("AlsaOutput")
        self.patch("choose_card")
        self.patch("time")
        self.patch("glob")
        self.patch("random")
        self.mixer = audio_engine.Mixer.return_value
        self.loader = audio_engine.SampleLoader.return_value
        self.loader.completed.return_value = []
        audio_engine.time.monotonic.return_value = 100.0
        self.engine = audio_engine.AudioEngine(self.commands, "fake-configured-card")

    def patch(self, name):
        patcher = mock.patch.object(audio_engine, name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def playing_track(self, name="fake-music", pattern="fake/*.wav", ratio=1.0, generation=1):
        track = audio_engine.MusicTrack(pattern, ratio, generation=generation, playing=True)
        self.engine.music_tracks[name] = track
        return track


class RunTest(EngineTestCase):
    def test_mixes_and_plays_blocks_until_shutdown_then_shuts_down(self):
        block_result = MixResult("fake-block", ["fake-finished-music"])
        self.mixer.next_block.return_value = block_result
        calls = mock.Mock()
        with mock.patch.object(self.engine, "_apply_commands", side_effect=[True, False]) as apply_commands, \
             mock.patch.object(self.engine, "_apply_loaded") as apply_loaded, \
             mock.patch.object(self.engine, "_continue_music") as continue_music, \
             mock.patch.object(self.engine, "_play") as play, \
             mock.patch.object(self.engine, "_shutdown") as shutdown:
            calls.attach_mock(apply_commands, "apply_commands")
            calls.attach_mock(apply_loaded, "apply_loaded")
            calls.attach_mock(self.mixer.next_block, "next_block")
            calls.attach_mock(continue_music, "continue_music")
            calls.attach_mock(play, "play")
            calls.attach_mock(shutdown, "shutdown")

            self.engine.run()

        self.assertEqual(calls.mock_calls, [
            mock.call.apply_commands(),
            mock.call.apply_loaded(),
            mock.call.next_block(audio_engine.BLOCK_FRAMES),
            mock.call.continue_music(["fake-finished-music"]),
            mock.call.play("fake-block"),
            mock.call.apply_commands(),
            mock.call.shutdown(),
        ])


class ApplyCommandsTest(EngineTestCase):
    def test_handles_every_waiting_command_in_order(self):
        self.commands.put(("fake_command_a",))
        self.commands.put(("fake_command_b", "fake-argument"))

        with mock.patch.object(self.engine, "_handle_command") as handle_command:
            result = self.engine._apply_commands()

        self.assertEqual(handle_command.call_args_list, [
            mock.call(("fake_command_a",)),
            mock.call(("fake_command_b", "fake-argument")),
        ])
        self.assertTrue(result)

    def test_stops_at_shutdown_and_reports_it(self):
        self.commands.put(("shutdown",))
        self.commands.put(("fake_command",))

        with mock.patch.object(self.engine, "_handle_command") as handle_command:
            result = self.engine._apply_commands()

        handle_command.assert_not_called()
        self.assertFalse(result)


class HandleCommandTest(EngineTestCase):
    def test_calls_the_handler_named_by_the_command_with_its_arguments(self):
        for command, arguments in [
            ("preload_effect", ("fake-path",)),
            ("play_effect", ("fake-path",)),
            ("stop_effect", ("fake-path",)),
            ("play_samples", ("fake-key", "fake-samples")),
            ("start_music", ("fake-music", "fake-pattern", 1.2)),
            ("stop_music", ("fake-music",)),
            ("set_music_ratio", ("fake-music", 1.2)),
            ("set_output", ("fake-card",)),
        ]:
            with self.subTest(command=command), mock.patch.object(self.engine, "_" + command) as handler:
                self.engine._handle_command((command, *arguments))

                handler.assert_called_once_with(*arguments)

    def test_logs_and_ignores_an_unknown_command(self):
        with self.assertLogs(audio_engine.logger, level="ERROR") as logs:
            self.engine._handle_command(("fake_unknown_command",))

        self.assertIn("fake_unknown_command", logs.output[0])


class EffectCommandsTest(EngineTestCase):
    def test_preload_requests_an_effect_that_is_not_loaded(self):
        with mock.patch.object(self.engine, "_request_effect") as request_effect:
            self.engine._preload_effect("fake-path")

        request_effect.assert_called_once_with("fake-path")

    def test_play_plays_a_loaded_effect_at_once(self):
        self.engine.effect_samples["fake-path"] = "fake-samples"

        self.engine._play_effect("fake-path")

        self.mixer.play_effect.assert_called_once_with("fake-path", "fake-samples")

    def test_play_requests_an_unloaded_effect_and_plays_it_once_loaded(self):
        with mock.patch.object(self.engine, "_request_effect") as request_effect:
            self.engine._play_effect("fake-path")
            self.engine._play_effect("fake-path")

        self.mixer.play_effect.assert_not_called()
        self.assertEqual(request_effect.call_args_list, [mock.call("fake-path"), mock.call("fake-path")])
        self.assertEqual(self.engine.pending_effect_plays["fake-path"], 2)

    def test_stop_stops_the_effect_and_cancels_plays_waiting_for_it(self):
        self.engine.pending_effect_plays["fake-path"] = 2

        self.engine._stop_effect("fake-path")

        self.mixer.stop_effect.assert_called_once_with("fake-path")
        self.assertNotIn("fake-path", self.engine.pending_effect_plays)

    def test_play_samples_plays_the_given_samples(self):
        self.engine._play_samples("fake-key", "fake-samples")

        self.mixer.play_effect.assert_called_once_with("fake-key", "fake-samples")


class RequestEffectTest(EngineTestCase):
    def test_asks_the_loader_for_the_effect(self):
        self.engine._request_effect("fake-path")

        self.loader.request.assert_called_once_with("fake-path", ("effect", "fake-path"))

    def test_skips_an_effect_already_loaded_or_loading(self):
        self.engine.effect_samples["fake-loaded-path"] = "fake-samples"
        self.engine._request_effect("fake-loading-path")
        self.loader.request.reset_mock()

        self.engine._request_effect("fake-loaded-path")
        self.engine._request_effect("fake-loading-path")

        self.loader.request.assert_not_called()


class MusicCommandsTest(EngineTestCase):
    def test_start_plays_a_new_song_for_the_track(self):
        with mock.patch.object(self.engine, "_request_next_song") as request_next_song:
            self.engine._start_music("fake-music", "fake/*.wav", 1.2)

        self.assertEqual(self.engine.music_tracks["fake-music"], audio_engine.MusicTrack("fake/*.wav", 1.2, generation=1, playing=True))
        request_next_song.assert_called_once_with("fake-music")

    def test_restarting_a_track_supersedes_its_earlier_song_load(self):
        self.playing_track(generation=4)

        with mock.patch.object(self.engine, "_request_next_song"):
            self.engine._start_music("fake-music", "fake/*.wav", 1.0)

        self.assertEqual(self.engine.music_tracks["fake-music"].generation, 5)

    def test_stop_silences_the_track_and_supersedes_its_song_load(self):
        self.playing_track(generation=4)

        self.engine._stop_music("fake-music")

        self.mixer.stop_music.assert_called_once_with("fake-music")
        self.assertFalse(self.engine.music_tracks["fake-music"].playing)
        self.assertEqual(self.engine.music_tracks["fake-music"].generation, 5)

    def test_stop_ignores_a_track_never_started(self):
        self.engine._stop_music("fake-music")

        self.mixer.stop_music.assert_called_once_with("fake-music")
        self.assertNotIn("fake-music", self.engine.music_tracks)

    def test_set_ratio_changes_the_playing_song_and_the_ratio_for_later_songs(self):
        track = self.playing_track(ratio=1.0)

        self.engine._set_music_ratio("fake-music", 1.4)

        self.mixer.set_music_ratio.assert_called_once_with("fake-music", 1.4)
        self.assertEqual(track.ratio, 1.4)

    def test_set_ratio_ignores_a_track_never_started(self):
        self.engine._set_music_ratio("fake-music", 1.4)

        self.mixer.set_music_ratio.assert_not_called()


class RequestNextSongTest(EngineTestCase):
    def test_asks_the_loader_for_a_random_matching_song(self):
        self.playing_track(pattern="fake/*.wav", generation=3)
        audio_engine.glob.glob.return_value = ["fake/a.wav", "fake/b.wav"]
        audio_engine.random.choice.return_value = "fake/b.wav"

        self.engine._request_next_song("fake-music")

        audio_engine.glob.glob.assert_called_once_with("fake/*.wav")
        audio_engine.random.choice.assert_called_once_with(["fake/a.wav", "fake/b.wav"])
        self.loader.request.assert_called_once_with("fake/b.wav", ("music", "fake-music", 3))

    def test_logs_when_no_song_matches(self):
        self.playing_track(pattern="fake/*.wav")
        audio_engine.glob.glob.return_value = []

        with self.assertLogs(audio_engine.logger, level="WARNING") as logs:
            self.engine._request_next_song("fake-music")

        self.assertIn("fake/*.wav", logs.output[0])
        self.loader.request.assert_not_called()


class ContinueMusicTest(EngineTestCase):
    def test_requests_another_song_for_tracks_still_playing(self):
        self.playing_track("fake-music-playing")
        self.playing_track("fake-music-stopped").playing = False

        with mock.patch.object(self.engine, "_request_next_song") as request_next_song:
            self.engine._continue_music(["fake-music-playing", "fake-music-stopped", "fake-music-unknown"])

        request_next_song.assert_called_once_with("fake-music-playing")


class ApplyLoadedTest(EngineTestCase):
    def test_hands_each_loaded_sample_to_its_kind_of_handler(self):
        self.loader.completed.return_value = [
            LoadedSample("fake-effect-path", ("effect", "fake-effect-path"), "fake-effect-samples"),
            LoadedSample("fake-song-path", ("music", "fake-music", 2), "fake-song-samples"),
        ]

        with mock.patch.object(self.engine, "_effect_loaded") as effect_loaded, \
             mock.patch.object(self.engine, "_song_loaded") as song_loaded:
            self.engine._apply_loaded()

        effect_loaded.assert_called_once_with("fake-effect-path", "fake-effect-samples")
        song_loaded.assert_called_once_with("fake-music", 2, "fake-song-path", "fake-song-samples")


class EffectLoadedTest(EngineTestCase):
    def test_caches_the_effect_and_plays_each_waiting_play(self):
        self.engine._request_effect("fake-path")
        self.engine.pending_effect_plays["fake-path"] = 2

        self.engine._effect_loaded("fake-path", "fake-samples")

        self.assertEqual(self.engine.effect_samples["fake-path"], "fake-samples")
        self.assertEqual(self.mixer.play_effect.call_args_list, [mock.call("fake-path", "fake-samples")] * 2)
        self.assertNotIn("fake-path", self.engine.pending_effect_plays)
        self.assertNotIn("fake-path", self.engine.loading_effects)

    def test_drops_waiting_plays_for_an_unreadable_effect_and_allows_a_retry(self):
        self.engine._request_effect("fake-path")
        self.engine.pending_effect_plays["fake-path"] = 1

        self.engine._effect_loaded("fake-path", None)

        self.mixer.play_effect.assert_not_called()
        self.assertNotIn("fake-path", self.engine.effect_samples)
        self.assertNotIn("fake-path", self.engine.pending_effect_plays)
        self.assertNotIn("fake-path", self.engine.loading_effects)


class SongLoadedTest(EngineTestCase):
    def test_starts_the_song_at_the_track_ratio_and_logs_it(self):
        self.playing_track(ratio=1.3, generation=2)

        with self.assertLogs(audio_engine.logger, level="INFO") as logs:
            self.engine._song_loaded("fake-music", 2, "fake/song.wav", "fake-samples")

        self.mixer.start_music.assert_called_once_with("fake-music", "fake-samples", ratio=1.3)
        self.assertIn("fake/song.wav", logs.output[0])
        self.assertIn("fake-music", logs.output[0])

    def test_drops_a_song_from_a_superseded_request(self):
        self.playing_track(generation=3)

        self.engine._song_loaded("fake-music", 2, "fake/song.wav", "fake-samples")

        self.mixer.start_music.assert_not_called()

    def test_drops_a_song_for_a_track_never_started(self):
        self.engine._song_loaded("fake-music", 1, "fake/song.wav", "fake-samples")

        self.mixer.start_music.assert_not_called()

    def test_leaves_the_track_silent_when_the_song_is_unreadable(self):
        self.playing_track(generation=2)

        self.engine._song_loaded("fake-music", 2, "fake/song.wav", None)

        self.mixer.start_music.assert_not_called()


class SetOutputTest(EngineTestCase):
    def test_closes_the_current_output_and_reopens_with_the_new_card_now(self):
        with mock.patch.object(self.engine, "_close_output") as close_output:
            self.engine._set_output("fake-new-card")

        close_output.assert_called_once_with()
        self.assertEqual(self.engine.configured_card, "fake-new-card")
        self.assertEqual(self.engine.next_output_attempt, 100.0)

    def test_logs_the_first_failure_to_open_the_new_card(self):
        audio_engine.AlsaOutput.side_effect = OutputError("fake-open-failure")
        self.engine._current_output()

        self.engine._set_output("fake-new-card")
        with self.assertLogs(audio_engine.logger, level="ERROR"):
            self.engine._current_output()


class CurrentOutputTest(EngineTestCase):
    def test_opens_the_chosen_card_when_due_and_logs_it(self):
        audio_engine.choose_card.return_value = "fake-chosen-card"

        with self.assertLogs(audio_engine.logger, level="INFO") as logs:
            result = self.engine._current_output()

        audio_engine.choose_card.assert_called_once_with("fake-configured-card")
        audio_engine.AlsaOutput.assert_called_once_with("fake-chosen-card", period_frames=audio_engine.BLOCK_FRAMES)
        self.assertIs(result, audio_engine.AlsaOutput.return_value)
        self.assertIn("fake-chosen-card", logs.output[0])

    def test_logs_the_system_default_when_no_card_is_chosen(self):
        audio_engine.choose_card.return_value = None

        with self.assertLogs(audio_engine.logger, level="INFO") as logs:
            self.engine._current_output()

        self.assertIn("system default", logs.output[0])

    def test_returns_the_open_output_without_reopening(self):
        self.engine.output = "fake-output"

        self.assertEqual(self.engine._current_output(), "fake-output")
        audio_engine.AlsaOutput.assert_not_called()

    def test_schedules_a_retry_when_the_card_cannot_be_opened(self):
        audio_engine.AlsaOutput.side_effect = OutputError("fake-open-failure")

        with self.assertLogs(audio_engine.logger, level="ERROR") as logs:
            result = self.engine._current_output()

        self.assertIsNone(result)
        self.assertIn("fake-open-failure", logs.output[0])
        self.assertEqual(self.engine.next_output_attempt, 100.0 + audio_engine.OUTPUT_RETRY_SECONDS)

    def test_does_not_log_the_same_failure_again(self):
        audio_engine.AlsaOutput.side_effect = OutputError("fake-open-failure")
        self.engine._current_output()
        self.engine.next_output_attempt = 100.0

        with self.assertNoLogs(audio_engine.logger, level="ERROR"):
            self.engine._current_output()

    def test_logs_a_failure_that_differs_from_the_last_one(self):
        audio_engine.AlsaOutput.side_effect = [OutputError("fake-first-failure"), OutputError("fake-second-failure")]
        self.engine._current_output()
        self.engine.next_output_attempt = 100.0

        with self.assertLogs(audio_engine.logger, level="ERROR") as logs:
            self.engine._current_output()

        self.assertIn("fake-second-failure", logs.output[0])

    def test_logs_a_failure_again_after_the_output_has_opened(self):
        audio_engine.AlsaOutput.side_effect = [OutputError("fake-open-failure"), "fake-output", OutputError("fake-open-failure")]
        self.engine._current_output()
        self.engine.next_output_attempt = 100.0
        self.engine._current_output()
        self.engine.output = None

        with self.assertLogs(audio_engine.logger, level="ERROR"):
            self.engine._current_output()

    def test_does_not_retry_before_the_scheduled_time(self):
        self.engine.next_output_attempt = 100.5

        self.assertIsNone(self.engine._current_output())
        audio_engine.AlsaOutput.assert_not_called()


class PlayTest(EngineTestCase):
    def test_writes_the_block_to_the_output(self):
        output = mock.Mock()

        with mock.patch.object(self.engine, "_current_output", return_value=output):
            self.engine._play("fake-block")

        output.write.assert_called_once_with("fake-block")
        audio_engine.time.sleep.assert_not_called()

    def test_waits_one_block_of_time_without_an_output(self):
        with mock.patch.object(self.engine, "_current_output", return_value=None):
            self.engine._play("fake-block")

        audio_engine.time.sleep.assert_called_once_with(audio_engine.BLOCK_FRAMES / audio_engine.OUTPUT_RATE)

    def test_closes_a_failed_output_and_schedules_a_retry(self):
        output = mock.Mock()
        output.write.side_effect = OutputError("fake-write-failure")

        with mock.patch.object(self.engine, "_current_output", return_value=output), \
             mock.patch.object(self.engine, "_close_output") as close_output, \
             self.assertLogs(audio_engine.logger, level="ERROR") as logs:
            self.engine._play("fake-block")

        close_output.assert_called_once_with()
        self.assertIn("fake-write-failure", logs.output[0])
        self.assertEqual(self.engine.next_output_attempt, 100.0 + audio_engine.OUTPUT_RETRY_SECONDS)


class CloseOutputTest(EngineTestCase):
    def test_closes_and_forgets_the_open_output(self):
        output = mock.Mock()
        self.engine.output = output

        self.engine._close_output()

        output.close.assert_called_once_with()
        self.assertIsNone(self.engine.output)

    def test_does_nothing_without_an_open_output(self):
        self.engine._close_output()

        self.assertIsNone(self.engine.output)


class ShutdownTest(EngineTestCase):
    def test_closes_the_output_and_stops_the_loader(self):
        with mock.patch.object(self.engine, "_close_output") as close_output:
            self.engine._shutdown()

        close_output.assert_called_once_with()
        self.loader.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
