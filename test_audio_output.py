import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy

# pyalsaaudio only builds on Linux. Every test patches the attributes it uses, so a
# placeholder module is enough to import audio_output elsewhere.
sys.modules.setdefault("alsaaudio", mock.MagicMock())

import audio_output


class FakeAlsaError(Exception):
    pass


class ChooseCardTest(unittest.TestCase):
    def test_returns_the_configured_card(self):
        self.assertEqual(audio_output.choose_card("fake-card"), "fake-card")

    def test_returns_a_usb_card_when_none_is_configured(self):
        with mock.patch.object(audio_output.alsaaudio, "cards", return_value=["fake-card-a", "Headphones"]), \
             mock.patch.object(audio_output, "find_usb_card", return_value="fake-card-a") as find_usb_card:
            result = audio_output.choose_card(None)

        find_usb_card.assert_called_once_with(["fake-card-a", "Headphones"])
        self.assertEqual(result, "fake-card-a")

    def test_returns_the_pi_headphone_jack_without_a_usb_card(self):
        with mock.patch.object(audio_output.alsaaudio, "cards", return_value=["fake-hdmi", "Headphones"]), \
             mock.patch.object(audio_output, "find_usb_card", return_value=None):
            self.assertEqual(audio_output.choose_card(None), "Headphones")

    def test_returns_none_for_the_system_default_without_usb_or_headphones(self):
        with mock.patch.object(audio_output.alsaaudio, "cards", return_value=["fake-hdmi"]), \
             mock.patch.object(audio_output, "find_usb_card", return_value=None):
            self.assertIsNone(audio_output.choose_card(None))

    def test_treats_an_empty_setting_as_not_configured(self):
        with mock.patch.object(audio_output.alsaaudio, "cards", return_value=[]), \
             mock.patch.object(audio_output, "find_usb_card", return_value="fake-usb-card"):
            self.assertEqual(audio_output.choose_card(""), "fake-usb-card")


class FindUsbCardTest(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.proc_asound = temporary_directory.name

    def make_card(self, card_id, usb):
        os.mkdir(os.path.join(self.proc_asound, card_id))
        if usb:
            open(os.path.join(self.proc_asound, card_id, "usbid"), "w").close()

    def test_returns_the_first_card_with_a_usb_id(self):
        self.make_card("fake-hdmi", usb=False)
        self.make_card("fake-usb-a", usb=True)
        self.make_card("fake-usb-b", usb=True)

        result = audio_output.find_usb_card(["fake-hdmi", "fake-usb-a", "fake-usb-b"], self.proc_asound)

        self.assertEqual(result, "fake-usb-a")

    def test_returns_none_without_a_usb_card(self):
        self.make_card("fake-hdmi", usb=False)

        self.assertIsNone(audio_output.find_usb_card(["fake-hdmi"], self.proc_asound))


class DeviceNameTest(unittest.TestCase):
    def test_names_the_card_default_device(self):
        self.assertEqual(audio_output.device_name("fake-card"), "default:CARD=fake-card")

    def test_names_the_system_default_without_a_card(self):
        self.assertEqual(audio_output.device_name(None), "default")


class AlsaOutputTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(audio_output, "alsaaudio")
        self.alsaaudio = patcher.start()
        self.addCleanup(patcher.stop)
        self.pcm = self.alsaaudio.PCM.return_value

    def test_opens_the_card_for_16_bit_stereo_at_the_output_rate(self):
        with mock.patch.object(audio_output, "device_name", return_value="fake-device"):
            audio_output.AlsaOutput("fake-card", period_frames=1024)

        self.alsaaudio.PCM.assert_called_once_with(
            type=self.alsaaudio.PCM_PLAYBACK,
            device="fake-device",
            channels=2,
            rate=audio_output.OUTPUT_RATE,
            format=self.alsaaudio.PCM_FORMAT_S16_LE,
            periodsize=1024,
            periods=4,
        )

    def test_reports_a_device_that_cannot_be_opened_as_an_output_error(self):
        self.alsaaudio.ALSAAudioError = FakeAlsaError
        self.alsaaudio.PCM.side_effect = FakeAlsaError("fake-open-failure")

        with self.assertRaisesRegex(audio_output.OutputError, "fake-open-failure"):
            audio_output.AlsaOutput("fake-card", period_frames=1024)

    def test_reports_a_failed_write_as_an_output_error(self):
        self.alsaaudio.ALSAAudioError = FakeAlsaError
        self.pcm.write.side_effect = FakeAlsaError("fake-write-failure")
        output = audio_output.AlsaOutput("fake-card", period_frames=1024)

        with self.assertRaisesRegex(audio_output.OutputError, "fake-write-failure"):
            output.write(numpy.zeros((1, 2), dtype=numpy.int16))

    def test_writes_the_block_bytes(self):
        block = numpy.array([[1, 2]], dtype=numpy.int16)
        self.pcm.write.return_value = 1

        audio_output.AlsaOutput("fake-card", period_frames=1024).write(block)

        self.pcm.write.assert_called_once_with(block.tobytes())

    def test_logs_an_underrun(self):
        self.pcm.write.return_value = -32

        with self.assertLogs(audio_output.logger, level="WARNING") as logs:
            audio_output.AlsaOutput("fake-card", period_frames=1024).write(numpy.zeros((1, 2), dtype=numpy.int16))

        self.assertIn("underrun", logs.output[0])

    def test_close_closes_the_device(self):
        audio_output.AlsaOutput("fake-card", period_frames=1024).close()

        self.pcm.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
