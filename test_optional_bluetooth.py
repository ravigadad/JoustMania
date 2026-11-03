import json
import unittest
from types import SimpleNamespace
from unittest import mock

import jm_dbus
import pair
import webui


class OptionalBluetoothTest(unittest.TestCase):
    @mock.patch.object(jm_dbus, 'ensure_process_bus')
    def test_absent_service_does_not_attempt_activation(self, connect):
        connect.return_value.name_has_owner.return_value = False
        self.assertEqual(jm_dbus.get_hci_dict(), {})
        connect.return_value.get_object.assert_not_called()

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict', return_value={})
    @mock.patch.object(pair.controller_manager, 'pair_controller')
    def test_no_adapter_skips_native_pairing(self, native_pair, discover):
        pairing = pair.Pair()
        controller = SimpleNamespace(serial='test', usb=True, bluetooth=False)
        self.assertFalse(pairing.pair_move(controller))
        native_pair.assert_not_called()

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict')
    def test_service_failure_does_not_prevent_initialization(self, discover):
        discover.side_effect = jm_dbus.dbus.DBusException('Service unavailable')
        self.assertEqual(pair.Pair().bt_devices, {})

    @mock.patch.object(pair.jm_dbus, 'get_hci_dict')
    @mock.patch.object(pair.Pair, 'pre_existing_devices')
    def test_adapter_can_be_added_after_startup(self, enumerate_devices, discover):
        discover.side_effect = [{}, {'hci0': 'AA:BB:CC:DD:EE:FF'}]
        pairing = pair.Pair()
        pairing.update_adapters()
        self.assertEqual(pairing.get_lowest_bt_device(), 'AA:BB:CC:DD:EE:FF')

    @mock.patch.object(webui.jm_dbus, 'get_hci_dict')
    def test_web_warning_clears_when_adapter_returns(self, discover):
        ui = webui.WebUI.__new__(webui.WebUI)
        ui.ns = SimpleNamespace(status={'game_status': 'menu'})
        discover.side_effect = [{}, {'hci0': 'AA:BB:CC:DD:EE:FF'}]
        self.assertIn('No Bluetooth', json.loads(ui.update())['bluetooth_message'])
        self.assertEqual(json.loads(ui.update())['bluetooth_message'], '')
        self.assertEqual(ui.ns.status, {'game_status': 'menu'})

class RobotVoiceTest(unittest.TestCase):
    def test_real_espeak_generates_bounded_playable_audio(self):
        import shutil
        import audio_client
        from audio_samples import OUTPUT_RATE
        if not (shutil.which('espeak') or shutil.which('espeak-ng')):
            self.skipTest('Speech engine not installed')
        try:
            samples = audio_client._robot_voice_samples('Robot voice regression test.')
            self.assertGreater(len(samples), 0)
            self.assertLess(len(samples), OUTPUT_RATE * 10)
            self.assertTrue(samples[:int(OUTPUT_RATE * 0.3)].any())
            self.assertFalse(samples[int(OUTPUT_RATE * 0.35):int(OUTPUT_RATE * 0.65)].any())
            self.assertTrue(samples[int(OUTPUT_RATE * 0.7):].any())
        finally:
            audio_client._robot_voice_samples.cache_clear()


if __name__ == '__main__':
    unittest.main()
