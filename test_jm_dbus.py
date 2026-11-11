import subprocess
import sys
import unittest
from unittest import mock

sys.modules.setdefault("dbus", mock.MagicMock())

import jm_dbus


class ResetAdapterTest(unittest.TestCase):
    def test_unblocks_bluetooth_then_resets_the_adapter(self):
        with mock.patch.object(jm_dbus, "_run_logged") as run_logged:
            jm_dbus.reset_adapter("fake-hci")

        self.assertEqual(run_logged.call_args_list, [
            mock.call(["sudo", "rfkill", "unblock", "bluetooth"]),
            mock.call(["sudo", "hciconfig", "fake-hci", "reset"]),
        ])


class RunLoggedTest(unittest.TestCase):
    def test_runs_the_command(self):
        with mock.patch.object(jm_dbus.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stderr="")) as run:
            jm_dbus._run_logged(["fake-command", "fake-argument"])

        run.assert_called_once_with(["fake-command", "fake-argument"], capture_output=True, text=True)

    def test_logs_a_failed_command_with_its_error(self):
        failure = subprocess.CompletedProcess([], 1, stderr="fake-error")
        with mock.patch.object(jm_dbus.subprocess, "run", return_value=failure), \
             self.assertLogs(jm_dbus.logger, level="WARNING") as logs:
            jm_dbus._run_logged(["fake-command", "fake-argument"])

        self.assertIn("fake-command fake-argument", logs.output[0])
        self.assertIn("fake-error", logs.output[0])


if __name__ == "__main__":
    unittest.main()
