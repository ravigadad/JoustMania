import subprocess
import unittest
from unittest import mock

import piparty


class ConfigureAsoundTest(unittest.TestCase):
    def test_runs_the_script_and_waits_for_it(self):
        with mock.patch.object(piparty.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            piparty.configure_asound()

        run.assert_called_once_with(["sudo", "./update_asound.sh"])

    def test_logs_a_failed_script(self):
        with mock.patch.object(piparty.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
             self.assertLogs(piparty.logger, level="WARNING") as logs:
            piparty.configure_asound()

        self.assertIn("update_asound.sh", logs.output[0])


if __name__ == "__main__":
    unittest.main()
