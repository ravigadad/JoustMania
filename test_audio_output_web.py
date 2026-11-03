import unittest
from types import SimpleNamespace
from unittest import mock

import webui

OUTPUTS = [{"card": "fake-hdmi", "label": "Fake HDMI"}, {"card": "fake-usb", "label": "Fake USB"}]


class AudioOutputWebTest(unittest.TestCase):
    def setUp(self):
        self.ns = SimpleNamespace(status={}, battery_status={}, settings={"audio_output": None})
        self.ui = webui.WebUI(ns=self.ns)
        self.client = self.ui.app.test_client()
        for target, name, value in [
            (webui.audio_output_setting, "list_outputs", OUTPUTS),
            (webui.audio_output_setting, "playing_card", "fake-hdmi"),
            (webui.runtime_platform, "is_linux", True),
        ]:
            patcher = mock.patch.object(target, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, name in [(webui, "audio_client"), (self.ui, "_save_settings")]:
            patcher = mock.patch.object(target, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_saves_and_applies_the_chosen_output(self):
        response = self.client.post("/debug/audio-output", data={"card": "fake-usb"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ns.settings["audio_output"], "fake-usb")
        self._save_settings.assert_called_once_with()
        self.audio_client.set_output.assert_called_once_with("fake-usb")
        self.assertEqual(response.json["selected"], "fake-usb")

    def test_saves_and_applies_automatic_for_an_empty_choice(self):
        self.ns.settings["audio_output"] = "fake-usb"

        response = self.client.post("/debug/audio-output", data={"card": ""})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.ns.settings["audio_output"])
        self.audio_client.set_output.assert_called_once_with(None)

    def test_rejects_an_output_that_is_not_present(self):
        response = self.client.post("/debug/audio-output", data={"card": "fake-missing"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("fake-missing", response.json["error"])
        self.assertIsNone(self.ns.settings["audio_output"])
        self._save_settings.assert_not_called()
        self.audio_client.set_output.assert_not_called()

    def test_refuses_off_linux(self):
        with mock.patch.object(webui.runtime_platform, "is_linux", return_value=False):
            response = self.client.post("/debug/audio-output", data={"card": "fake-usb"})

        self.assertEqual(response.status_code, 409)
        self.audio_client.set_output.assert_not_called()

    def test_accepts_only_post(self):
        self.assertEqual(self.client.get("/debug/audio-output").status_code, 405)

    def test_debug_page_and_data_show_the_outputs(self):
        self.ns.settings["audio_output"] = "fake-usb"

        with mock.patch.object(self.ui, "_controller_debug_data", return_value=[]), \
             mock.patch.object(webui.bluetooth_diagnostics, "get_adapters", return_value=[]):
            data = self.client.get("/debug/data").json["audio_output"]
            html = self.client.get("/debug").data

        self.assertEqual(data["selected"], "fake-usb")
        self.assertEqual(data["playing"], "fake-hdmi")
        self.assertIn(b'id="audio-output-heading"', html)
        self.assertIn(b"Fake USB", html)
        self.assertIn(b'<option value="fake-usb" selected>', html)
        self.assertIn(b"Playing through Fake HDMI", html)
        self.assertLess(html.index(b'id="audio-output-heading"'), html.index(b"Reset Bluetooth Controllers"))


if __name__ == "__main__":
    unittest.main()
