import unittest
import wave
from unittest import mock

import numpy

import robot_voice

SPEECH_RATE = 22050


def write_fake_speech(command, **_):
    output_path = command[command.index("-w") + 1]
    with wave.open(output_path, "wb") as speech:
        speech.setnchannels(1)
        speech.setsampwidth(2)
        speech.setframerate(SPEECH_RATE)
        speech.writeframes(numpy.full(SPEECH_RATE // 10, 1000, dtype="<i2").tobytes())


class RenderRobotVoiceTest(unittest.TestCase):
    def test_returns_a_wav_of_attention_tone_then_silence_then_speech(self):
        with mock.patch.object(robot_voice.shutil, "which", return_value="/fake/espeak"), \
             mock.patch.object(robot_voice.subprocess, "run", side_effect=write_fake_speech) as run:
            result = robot_voice.render_robot_voice("fake message")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/fake/espeak")
        self.assertEqual(command[-1], "fake message")
        with wave.open(result, "rb") as rendered:
            self.assertEqual(rendered.getframerate(), SPEECH_RATE)
            frames = numpy.frombuffer(rendered.readframes(rendered.getnframes()), dtype="<i2")
        tone_end = int(SPEECH_RATE * 0.3)
        silence_end = tone_end + int(SPEECH_RATE * 0.4)
        self.assertTrue(frames[:tone_end].any())
        self.assertFalse(frames[tone_end:silence_end].any())
        self.assertTrue((frames[silence_end:] == 1000).all())

    def test_returns_none_without_a_speech_engine(self):
        with mock.patch.object(robot_voice.shutil, "which", return_value=None):
            self.assertIsNone(robot_voice.render_robot_voice("fake message"))


if __name__ == "__main__":
    unittest.main()
