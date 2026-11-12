import sys
import unittest
from unittest import mock

sys.modules.setdefault("psmoveapi", mock.MagicMock())

import common


class AllowEveryoneToEditTest(unittest.TestCase):
    def test_makes_the_file_readable_and_writable_by_everyone(self):
        with mock.patch.object(common.os, "chmod") as chmod:
            common.allow_everyone_to_edit("fake/path.yaml")

        chmod.assert_called_once_with("fake/path.yaml", 0o666)

    def test_logs_a_failure(self):
        with mock.patch.object(common.os, "chmod", side_effect=OSError("fake-error")), \
             self.assertLogs(common.logger, level="WARNING") as logs:
            common.allow_everyone_to_edit("fake/path.yaml")

        self.assertIn("fake-error", logs.output[0])


if __name__ == "__main__":
    unittest.main()
