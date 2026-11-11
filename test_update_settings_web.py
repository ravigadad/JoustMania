import unittest
from types import SimpleNamespace

from werkzeug.datastructures import MultiDict

import update
import webui


class UpdateLocalChangesSettingTest(unittest.TestCase):
    def test_settings_page_offers_each_choice_and_selects_the_saved_one(self):
        ns = SimpleNamespace(status={}, settings={
            'color_lock_choices': {2: ['Magenta', 'Green'], 3: ['Orange', 'Turquoise', 'Purple'],
                                   4: ['Yellow', 'Green', 'Blue', 'Purple']},
            'sensitivity': 2, 'red_on_kill': True, 'random_team_size': 4, 'force_all_start': False,
            'update_local_changes': update.DISCARD_LOCAL_CHANGES})
        client = webui.WebUI(ns=ns).app.test_client()

        page = client.get('/settings').data.decode()

        for choice in (update.SKIP_LOCAL_CHANGES, update.KEEP_LOCAL_CHANGES, update.DISCARD_LOCAL_CHANGES):
            self.assertIn(f'value="{choice}"', page)
        self.assertIn(f'selected value="{update.DISCARD_LOCAL_CHANGES}"', page)

    def test_form_passes_the_posted_choice_to_the_saved_settings(self):
        form = webui.SettingsForm(MultiDict({'update_local_changes': update.KEEP_LOCAL_CHANGES}))

        self.assertEqual(form.data['update_local_changes'], update.KEEP_LOCAL_CHANGES)


if __name__ == "__main__":
    unittest.main()
