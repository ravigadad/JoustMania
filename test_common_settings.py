import sys
import unittest
from unittest import mock

sys.modules.setdefault("psmoveapi", mock.MagicMock())

import common


class KnownSettingsTest(unittest.TestCase):
    def test_keeps_required_settings_and_drops_every_other_key(self):
        with mock.patch.object(common, "REQUIRED_SETTINGS", ["fake-a", "fake-b"]):
            result = common.known_settings({"fake-a": 1, "fake-unknown-1": 2, "fake-b": 3, "fake-unknown-2": 4})

        self.assertEqual(result, {"fake-a": 1, "fake-b": 3})


class RandomModeChoicesTest(unittest.TestCase):
    def test_drops_unknown_modes_and_modes_random_play_cannot_pick(self):
        modes = ["JoustFFA", "fake-unknown-1", "fake-unknown-2", "JoustTeams", "Random", "Werewolf"]

        self.assertEqual(common.random_mode_choices(modes), ["JoustFFA", "Werewolf"])

    def test_falls_back_to_joust_ffa_when_no_mode_is_left(self):
        self.assertEqual(common.random_mode_choices(["fake-unknown", "Random"]), ["JoustFFA"])


if __name__ == "__main__":
    unittest.main()
