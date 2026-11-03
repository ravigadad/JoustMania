import asyncio
import subprocess
import sys
import unittest
from unittest import mock

sys.modules.setdefault("alsaaudio", mock.MagicMock())

import audio_client


class InitAudioTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(audio_client, "_commands", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_starts_the_engine_process_with_a_command_queue(self):
        with mock.patch.object(audio_client, "multiprocessing") as multiprocessing:
            audio_client.InitAudio()

        commands = multiprocessing.Queue.return_value
        multiprocessing.Process.assert_called_once_with(
            target=audio_client.audio_engine.run_engine, args=(commands, None), daemon=True)
        multiprocessing.Process.return_value.start.assert_called_once_with()
        self.assertIs(audio_client._commands, commands)

    def test_starts_the_engine_only_once(self):
        with mock.patch.object(audio_client, "multiprocessing") as multiprocessing:
            audio_client.InitAudio()
            audio_client.InitAudio()

        multiprocessing.Process.assert_called_once()


class SendTest(unittest.TestCase):
    def test_puts_the_command_on_the_engine_queue(self):
        commands = mock.Mock()

        with mock.patch.object(audio_client, "_commands", commands):
            audio_client._send(("fake_command", "fake-argument"))

        commands.put.assert_called_once_with(("fake_command", "fake-argument"))

    def test_refuses_to_send_before_the_engine_starts(self):
        with mock.patch.object(audio_client, "_commands", None), self.assertRaises(RuntimeError):
            audio_client._send(("fake_command",))


class SetOutputTest(unittest.TestCase):
    def test_asks_the_engine_to_switch_to_the_card(self):
        with mock.patch.object(audio_client, "_send") as send:
            audio_client.set_output("fake-card")

        send.assert_called_once_with(("set_output", "fake-card"))


class AudioTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(audio_client, "_send")
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def test_asks_the_engine_to_preload_the_effect(self):
        audio_client.Audio("fake/effect.wav")

        self.send.assert_called_once_with(("preload_effect", "fake/effect.wav"))

    def test_start_effect_plays_the_effect(self):
        audio = audio_client.Audio("fake/effect.wav")

        audio.start_effect()

        self.send.assert_called_with(("play_effect", "fake/effect.wav"))

    def test_stop_effect_stops_the_effect(self):
        audio = audio_client.Audio("fake/effect.wav")

        audio.stop_effect()

        self.send.assert_called_with(("stop_effect", "fake/effect.wav"))

    def test_get_length_secs_reads_the_length_from_the_file(self):
        audio = audio_client.Audio("fake/effect.wav")

        with mock.patch.object(audio_client.wavfile, "read", return_value=(48000, [0] * 24000)) as read:
            result = audio.get_length_secs()

        read.assert_called_once_with("fake/effect.wav", mmap=True)
        self.assertEqual(result, 0.5)

    def test_start_effect_and_wait_plays_then_waits_for_the_effect_length(self):
        audio = audio_client.Audio("fake/effect.wav")
        calls = mock.Mock()
        calls.attach_mock(self.send, "send")

        with mock.patch.object(audio, "get_length_secs", return_value=1.5), \
             mock.patch.object(audio_client.time, "sleep") as sleep:
            calls.attach_mock(sleep, "sleep")
            audio.start_effect_and_wait()

        self.assertEqual(calls.mock_calls[-2:], [
            mock.call.send(("play_effect", "fake/effect.wav")),
            mock.call.sleep(1.5),
        ])


class MusicTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(audio_client, "_send")
        self.send = patcher.start()
        self.addCleanup(patcher.stop)
        self.music = audio_client.Music.__wrapped__("fake-music")

    def test_start_audio_loop_starts_the_loaded_songs_at_the_current_ratio(self):
        self.music.load_audio("fake/*.wav")
        self.music.change_ratio(1.2)

        self.music.start_audio_loop()

        self.send.assert_called_with(("start_music", "fake-music", "fake/*.wav", 1.2))

    def test_start_audio_loop_plays_at_normal_speed_by_default(self):
        self.music.load_audio("fake/*.wav")

        self.music.start_audio_loop()

        self.send.assert_called_once_with(("start_music", "fake-music", "fake/*.wav", 1.0))

    def test_start_audio_loop_does_nothing_before_songs_are_loaded(self):
        self.music.start_audio_loop()

        self.send.assert_not_called()

    def test_stop_audio_stops_the_track_and_keeps_its_songs_for_the_next_start(self):
        self.music.load_audio("fake/*.wav")

        self.music.stop_audio()
        self.music.start_audio_loop()

        self.assertEqual(self.send.call_args_list, [
            mock.call(("stop_music", "fake-music")),
            mock.call(("start_music", "fake-music", "fake/*.wav", 1.0)),
        ])

    def test_change_ratio_changes_the_playing_speed(self):
        self.music.change_ratio(1.4)

        self.send.assert_called_once_with(("set_music_ratio", "fake-music", 1.4))
        self.assertEqual(self.music.ratio, 1.4)

    def test_transition_ratio_steps_to_the_new_ratio(self):
        async def transition():
            await self.music.transition_ratio(2.0, transition_duration=0)

        with mock.patch.object(self.music, "change_ratio", wraps=self.music.change_ratio) as change_ratio:
            asyncio.run(transition())

        self.assertEqual(change_ratio.call_count, 20)
        self.assertEqual(change_ratio.call_args_list[-1], mock.call(2.0))

    def test_stop_audio_cancels_a_transition_in_progress(self):
        transition = mock.Mock()
        self.music.transition_future_ = transition

        self.music.stop_audio()

        transition.cancel.assert_called_once_with()

    def test_returns_one_music_object_per_name(self):
        self.assertIs(audio_client.Music("fake-shared-music"), audio_client.Music("fake-shared-music"))


class SpeakTest(unittest.TestCase):
    def test_plays_the_rendered_message(self):
        with mock.patch.object(audio_client, "_robot_voice_samples", return_value="fake-samples") as voice_samples, \
             mock.patch.object(audio_client, "_send") as send:
            audio_client.speak("fake message")

        voice_samples.assert_called_once_with("fake message")
        send.assert_called_once_with(("play_samples", "robot-voice", "fake-samples"))

    def test_stays_silent_without_a_speech_engine(self):
        with mock.patch.object(audio_client, "_robot_voice_samples", return_value=None), \
             mock.patch.object(audio_client, "_send") as send:
            audio_client.speak("fake message")

        send.assert_not_called()

    def test_logs_a_speech_failure_without_raising(self):
        for error in [OSError("fake-error"), subprocess.SubprocessError("fake-error"), ValueError("fake-error")]:
            with self.subTest(error=type(error).__name__), \
                 mock.patch.object(audio_client, "_robot_voice_samples", side_effect=error), \
                 mock.patch.object(audio_client, "_send") as send, \
                 self.assertLogs(audio_client.logger, level="WARNING"):
                audio_client.speak("fake message")

            send.assert_not_called()


class RobotVoiceSamplesTest(unittest.TestCase):
    def test_returns_the_rendered_voice_as_samples(self):
        with mock.patch.object(audio_client, "render_robot_voice", return_value="fake-wav") as render, \
             mock.patch.object(audio_client, "load_sample", return_value="fake-samples") as load_sample:
            result = audio_client._robot_voice_samples.__wrapped__("fake message")

        render.assert_called_once_with("fake message")
        load_sample.assert_called_once_with("fake-wav")
        self.assertEqual(result, "fake-samples")

    def test_returns_none_without_a_speech_engine(self):
        with mock.patch.object(audio_client, "render_robot_voice", return_value=None), \
             mock.patch.object(audio_client, "load_sample") as load_sample:
            result = audio_client._robot_voice_samples.__wrapped__("fake message")

        load_sample.assert_not_called()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
