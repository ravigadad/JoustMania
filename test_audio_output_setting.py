import os
import tempfile
import unittest
from unittest import mock

import audio_output_setting

PI_5_WITH_USB_CARDS = (
    " 0 [vc4hdmi0       ]: vc4-hdmi - vc4-hdmi-0\n"
    "                      vc4-hdmi-0\n"
    " 1 [vc4hdmi1       ]: vc4-hdmi - vc4-hdmi-1\n"
    "                      vc4-hdmi-1\n"
    " 2 [Device         ]: USB-Audio - USB Audio Device\n"
    "                      C-Media Electronics Inc. USB Audio Device at usb-xhci-hcd.1-1, full speed\n"
    " 3 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones\n"
    "                      bcm2835 Headphones\n"
    " 4 [Loopback       ]: Loopback - Loopback\n"
    "                      Loopback 1\n"
)


class ProcAsoundTestCase(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.proc_asound = temporary_directory.name

    def write_cards(self, text):
        with open(os.path.join(self.proc_asound, "cards"), "w") as cards:
            cards.write(text)

    def write_playback_state(self, card_id, state):
        directory = os.path.join(self.proc_asound, card_id, "pcm0p", "sub0")
        os.makedirs(directory)
        with open(os.path.join(directory, "status"), "w") as status:
            status.write(f"state: {state}\nowner_pid   : 1\n" if state else "closed\n")


class ListOutputsTest(ProcAsoundTestCase):
    def test_lists_every_card_with_a_readable_label(self):
        self.write_cards(PI_5_WITH_USB_CARDS)

        self.assertEqual(audio_output_setting.list_outputs(self.proc_asound), [
            {"card": "vc4hdmi0", "driver": "vc4-hdmi", "label": "HDMI 0"},
            {"card": "vc4hdmi1", "driver": "vc4-hdmi", "label": "HDMI 1"},
            {"card": "Device", "driver": "USB-Audio", "label": "USB: USB Audio Device"},
            {"card": "Headphones", "driver": "bcm2835_headpho", "label": "Headphone jack"},
            {"card": "Loopback", "driver": "Loopback", "label": "Loopback"},
        ])

    def test_returns_no_outputs_without_a_card_list(self):
        self.assertEqual(audio_output_setting.list_outputs(self.proc_asound), [])


class PlayingCardTest(ProcAsoundTestCase):
    def test_returns_the_card_whose_playback_is_running(self):
        self.write_playback_state("vc4hdmi0", None)
        self.write_playback_state("Device", "RUNNING")

        self.assertEqual(audio_output_setting.playing_card(["vc4hdmi0", "Device"], self.proc_asound), "Device")

    def test_returns_none_when_no_playback_is_running(self):
        self.write_playback_state("vc4hdmi0", "PREPARED")

        self.assertIsNone(audio_output_setting.playing_card(["vc4hdmi0", "vc4hdmi1"], self.proc_asound))


class StatusTest(unittest.TestCase):
    def test_reports_the_outputs_the_selection_the_playing_card_and_a_message(self):
        outputs = [{"card": "fake-card-a", "label": "fake-label-a"}, {"card": "fake-card-b", "label": "fake-label-b"}]
        with mock.patch.object(audio_output_setting.runtime_platform, "is_linux", return_value=True), \
             mock.patch.object(audio_output_setting, "list_outputs", return_value=outputs), \
             mock.patch.object(audio_output_setting, "playing_card", return_value="fake-card-b") as playing_card, \
             mock.patch.object(audio_output_setting, "status_message", return_value="fake-message") as status_message:
            result = audio_output_setting.status("fake-card-b")

        playing_card.assert_called_once_with(["fake-card-a", "fake-card-b"])
        status_message.assert_called_once_with("fake-card-b", outputs, "fake-card-b")
        self.assertEqual(result, {
            "supported": True,
            "selected": "fake-card-b",
            "outputs": outputs,
            "playing": "fake-card-b",
            "message": "fake-message",
        })

    def test_reports_automatic_as_an_empty_selection(self):
        with mock.patch.object(audio_output_setting.runtime_platform, "is_linux", return_value=True), \
             mock.patch.object(audio_output_setting, "list_outputs", return_value=[]), \
             mock.patch.object(audio_output_setting, "playing_card", return_value=None), \
             mock.patch.object(audio_output_setting, "status_message", return_value="fake-message"):
            self.assertEqual(audio_output_setting.status(None)["selected"], "")

    def test_reports_unsupported_off_linux(self):
        with mock.patch.object(audio_output_setting.runtime_platform, "is_linux", return_value=False):
            self.assertEqual(audio_output_setting.status("fake-card"), {"supported": False})



class StatusMessageTest(unittest.TestCase):
    OUTPUTS = [
        {"card": "fake-hdmi", "driver": "vc4-hdmi", "label": "fake-hdmi-label"},
        {"card": "fake-usb", "driver": "USB-Audio", "label": "fake-usb-label"},
    ]

    def test_names_the_playing_output(self):
        self.assertEqual(
            audio_output_setting.status_message(None, self.OUTPUTS, "fake-usb"),
            "Playing through fake-usb-label",
        )

    def test_waits_for_a_chosen_output_that_is_not_playing(self):
        self.assertEqual(
            audio_output_setting.status_message("fake-usb", self.OUTPUTS, None),
            "Waiting for fake-usb-label",
        )

    def test_explains_that_a_chosen_hdmi_port_needs_a_display(self):
        message = audio_output_setting.status_message("fake-hdmi", self.OUTPUTS, None)

        self.assertTrue(message.startswith("Waiting for fake-hdmi-label"))
        self.assertIn("display", message)

    def test_names_a_chosen_output_that_is_no_longer_connected_by_its_card(self):
        message = audio_output_setting.status_message("fake-missing-card", self.OUTPUTS, None)

        self.assertTrue(message.startswith("Waiting for fake-missing-card"))
        self.assertIn("not connected", message)

    def test_reports_no_open_output_when_nothing_is_chosen_or_playing(self):
        self.assertEqual(audio_output_setting.status_message(None, self.OUTPUTS, None), "No output is open")


if __name__ == "__main__":
    unittest.main()
