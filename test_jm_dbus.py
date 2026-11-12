import subprocess
import sys
import unittest
from unittest import mock

sys.modules.setdefault("dbus", mock.MagicMock())

import jm_dbus


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


RFKILL_LIST = (
    "0: hci0: Bluetooth\n"
    "\tSoft blocked: yes\n"
    "\tHard blocked: no\n"
    "1: phy0: Wireless LAN\n"
    "\tSoft blocked: no\n"
    "\tHard blocked: no\n"
    "12: hci1: Bluetooth\n"
    "\tSoft blocked: yes\n"
    "\tHard blocked: no\n"
)


class EnableAdapterTest(unittest.TestCase):
    def setUp(self):
        self.properties = mock.Mock()
        self.properties.Get.return_value = mock.Mock(real=False)
        self.blocked = type("FakeDBusException", (Exception,), {})
        patcher = mock.patch.object(jm_dbus.dbus.exceptions, "DBusException", self.blocked)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in [("get_adapter_proxy", "fake-proxy"), ("rfkill_unblock", True)]:
            patcher = mock.patch.object(jm_dbus, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(jm_dbus.dbus, "Interface", return_value=self.properties)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_powers_on_an_adapter_that_is_off(self):
        self.assertTrue(jm_dbus.enable_adapter("fake-hci"))
        self.properties.Set.assert_called_once_with("org.bluez.Adapter1", "Powered", True)

    def test_leaves_an_adapter_that_is_already_on(self):
        self.properties.Get.return_value = mock.Mock(real=True)

        self.assertFalse(jm_dbus.enable_adapter("fake-hci"))
        self.properties.Set.assert_not_called()

    def test_unblocks_a_blocked_adapter_and_powers_it_on(self):
        self.properties.Set.side_effect = [self.blocked("fake rfkill block"), None]

        self.assertTrue(jm_dbus.enable_adapter("fake-hci"))
        self.rfkill_unblock.assert_called_once_with("fake-hci")
        self.assertEqual(self.properties.Set.call_count, 2)

    def test_raises_when_the_adapter_is_still_blocked_after_unblocking(self):
        self.properties.Set.side_effect = self.blocked("fake rfkill block")

        with self.assertRaises(self.blocked):
            jm_dbus.enable_adapter("fake-hci")
        self.rfkill_unblock.assert_called_once_with("fake-hci")
        self.assertEqual(self.properties.Set.call_count, 2)

    def test_raises_without_retrying_when_unblocking_fails(self):
        self.properties.Set.side_effect = self.blocked("fake rfkill block")
        self.rfkill_unblock.return_value = False

        with self.assertRaises(self.blocked):
            jm_dbus.enable_adapter("fake-hci")
        self.properties.Set.assert_called_once()

    def test_raises_other_errors_without_unblocking(self):
        self.properties.Set.side_effect = self.blocked("fake other failure")

        with self.assertRaises(self.blocked):
            jm_dbus.enable_adapter("fake-hci")
        self.rfkill_unblock.assert_not_called()


class RfkillUnblockTest(unittest.TestCase):
    def test_unblocks_the_radio_listed_for_the_hci(self):
        with mock.patch.object(jm_dbus.subprocess, "run", side_effect=[completed(stdout=RFKILL_LIST), completed()]) as run:
            self.assertTrue(jm_dbus.rfkill_unblock("hci1"))

        self.assertEqual(run.call_args_list, [
            mock.call(["rfkill", "list"], capture_output=True, text=True),
            mock.call(["rfkill", "unblock", "12"], capture_output=True, text=True),
        ])

    def test_logs_and_fails_when_rfkill_lists_no_radio_for_the_hci(self):
        with mock.patch.object(jm_dbus.subprocess, "run", return_value=completed(stdout=RFKILL_LIST)) as run, \
             self.assertLogs(jm_dbus.logger, level="WARNING") as logs:
            self.assertFalse(jm_dbus.rfkill_unblock("hci7"))

        run.assert_called_once()
        self.assertIn("hci7", logs.output[0])

    def test_logs_and_fails_when_rfkill_list_fails(self):
        with mock.patch.object(jm_dbus.subprocess, "run", return_value=completed(1, stderr="fake-list-error")) as run, \
             self.assertLogs(jm_dbus.logger, level="WARNING") as logs:
            self.assertFalse(jm_dbus.rfkill_unblock("hci0"))

        run.assert_called_once()
        self.assertIn("fake-list-error", logs.output[0])

    def test_logs_and_fails_when_the_unblock_fails(self):
        with mock.patch.object(jm_dbus.subprocess, "run", side_effect=[completed(stdout=RFKILL_LIST), completed(1, stderr="fake-unblock-error")]), \
             self.assertLogs(jm_dbus.logger, level="WARNING") as logs:
            self.assertFalse(jm_dbus.rfkill_unblock("hci0"))

        self.assertIn("fake-unblock-error", logs.output[0])


if __name__ == "__main__":
    unittest.main()
