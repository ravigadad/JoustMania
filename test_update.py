import subprocess
import sys
import unittest
from unittest import mock

sys.modules.setdefault("piaudio", mock.MagicMock())

import update


def git_result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["fake-git"], returncode, stdout=stdout, stderr=stderr)


class CheckForUpdateTest(unittest.TestCase):
    def setUp(self):
        for name, value in {
            "_has_upstream": True,
            "_fetch": True,
            "_commits_behind": 2,
            "_is_fast_forward": True,
            "_has_local_edits": False,
            "_changed_files": ["fake-file.py"],
            "_apply_update": True,
        }.items():
            patcher = mock.patch.object(update, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(update, "_announce")
        self.announce = patcher.start()
        self.addCleanup(patcher.stop)

    def test_applies_a_small_update_and_announces_it(self):
        result = update.check_for_update("fake-voice", "fake-setting")

        self.assertFalse(result)
        self._apply_update.assert_called_once_with("fake-setting")
        self.announce.assert_called_once_with("fake-voice", "joustmania_updated.wav")

    def test_announces_a_large_update_without_applying_it(self):
        self._changed_files.return_value = ["fake-file.py", "setup.sh"]

        result = update.check_for_update("fake-voice", "fake-setting")

        self.assertTrue(result)
        self._apply_update.assert_not_called()
        self.announce.assert_called_once_with("fake-voice", "large_update.wav")

    def test_does_not_announce_an_update_that_failed(self):
        self._apply_update.return_value = False

        self.assertFalse(update.check_for_update("fake-voice", "fake-setting"))
        self.announce.assert_not_called()

    def test_skips_a_branch_without_an_upstream_and_logs_why(self):
        self._has_upstream.return_value = False

        with self.assertLogs(update.logger, level="INFO") as logs:
            result = update.check_for_update("fake-voice", "fake-setting")

        self.assertFalse(result)
        self.assertIn("no upstream", logs.output[0])
        self._fetch.assert_not_called()
        self.announce.assert_not_called()

    def test_stops_when_the_fetch_fails(self):
        self._fetch.return_value = False

        self.assertFalse(update.check_for_update("fake-voice", "fake-setting"))
        self._commits_behind.assert_not_called()
        self.announce.assert_not_called()

    def test_does_nothing_when_no_commits_have_arrived(self):
        self._commits_behind.return_value = 0

        self.assertFalse(update.check_for_update("fake-voice", "fake-setting"))
        self._apply_update.assert_not_called()
        self.announce.assert_not_called()

    def test_skips_a_checkout_with_commits_the_upstream_lacks_and_logs_why(self):
        self._is_fast_forward.return_value = False

        with self.assertLogs(update.logger, level="WARNING") as logs:
            result = update.check_for_update("fake-voice", "fake-setting")

        self.assertFalse(result)
        self.assertIn("commits", logs.output[0])
        self._apply_update.assert_not_called()
        self.announce.assert_not_called()

    def test_skips_local_edits_when_set_to_skip_and_logs_why(self):
        self._has_local_edits.return_value = True

        with self.assertLogs(update.logger, level="WARNING") as logs:
            result = update.check_for_update("fake-voice", update.SKIP_LOCAL_CHANGES)

        self.assertFalse(result)
        self.assertIn("local edits", logs.output[0])
        self._apply_update.assert_not_called()
        self.announce.assert_not_called()

    def test_treats_an_unrecognised_setting_as_skip(self):
        self._has_local_edits.return_value = True

        with self.assertLogs(update.logger, level="WARNING"):
            self.assertFalse(update.check_for_update("fake-voice", "fake-unrecognised-setting"))

        self._apply_update.assert_not_called()

    def test_updates_despite_local_edits_under_the_other_settings(self):
        self._has_local_edits.return_value = True

        update.check_for_update("fake-voice", update.KEEP_LOCAL_CHANGES)

        self._apply_update.assert_called_once_with(update.KEEP_LOCAL_CHANGES)


class BigUpdateTest(unittest.TestCase):
    def setUp(self):
        for name, value in {"_head_commit": "fake-previous-commit", "_apply_update": True, "_run_setup": True}.items():
            patcher = mock.patch.object(update, name, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        for name in ("_announce", "_restore"):
            patcher = mock.patch.object(update, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_applies_the_update_and_runs_setup(self):
        update.big_update("fake-voice", "fake-setting")

        self._announce.assert_called_once_with("fake-voice", "update_started.wav")
        self._apply_update.assert_called_once_with("fake-setting")
        self._run_setup.assert_called_once_with()
        self._restore.assert_not_called()

    def test_restores_the_previous_commit_when_setup_fails(self):
        self._run_setup.return_value = False

        update.big_update("fake-voice", "fake-setting")

        self._restore.assert_called_once_with("fake-previous-commit")
        self.assertEqual(self._announce.call_args_list, [
            mock.call("fake-voice", "update_started.wav"),
            mock.call("fake-voice", "joustmania_failed.wav"),
        ])

    def test_restores_without_running_setup_when_the_update_fails(self):
        self._apply_update.return_value = False

        update.big_update("fake-voice", "fake-setting")

        self._run_setup.assert_not_called()
        self._restore.assert_called_once_with("fake-previous-commit")
        self._announce.assert_called_with("fake-voice", "joustmania_failed.wav")


class CurrentCommitTest(unittest.TestCase):
    def test_returns_the_short_hash_of_the_checked_out_commit(self):
        with mock.patch.object(update, "_git", return_value=git_result(stdout="fake-hash\n")) as git:
            self.assertEqual(update.current_commit(), "fake-hash")

        git.assert_called_once_with("rev-parse", "--short=7", "HEAD")

    def test_returns_an_empty_hash_and_logs_when_git_fails(self):
        with mock.patch.object(update, "_git", return_value=git_result(128, stderr="fake-error")), \
             self.assertLogs(update.logger, level="WARNING") as logs:
            self.assertEqual(update.current_commit(), "")

        self.assertIn("fake-error", logs.output[0])


class GitTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(update, "_checkout_owner", return_value=mock.Mock(pw_uid=1000, pw_name="fake-owner"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_runs_git_as_the_checkout_owner_when_running_as_someone_else(self):
        with mock.patch.object(update.os, "geteuid", return_value=0), \
             mock.patch.object(update.subprocess, "run", return_value="fake-result") as run:
            result = update._git("fake-argument")

        run.assert_called_once_with(
            ["runuser", "-u", "fake-owner", "--", "git", "-C", update.APP_DIR, "fake-argument"],
            capture_output=True, text=True,
        )
        self.assertEqual(result, "fake-result")

    def test_runs_git_directly_when_already_the_checkout_owner(self):
        with mock.patch.object(update.os, "geteuid", return_value=1000), \
             mock.patch.object(update.subprocess, "run", return_value="fake-result") as run:
            update._git("fake-argument")

        run.assert_called_once_with(["git", "-C", update.APP_DIR, "fake-argument"], capture_output=True, text=True)


class CheckoutOwnerTest(unittest.TestCase):
    def test_returns_the_account_that_owns_the_checkout(self):
        with mock.patch.object(update.os, "stat", return_value=mock.Mock(st_uid=1000)) as stat, \
             mock.patch("pwd.getpwuid", return_value="fake-account") as getpwuid:
            self.assertEqual(update._checkout_owner(), "fake-account")

        stat.assert_called_once_with(update.APP_DIR)
        getpwuid.assert_called_once_with(1000)


class GitQueryTestCase(unittest.TestCase):
    def git_returns(self, result):
        patcher = mock.patch.object(update, "_git", return_value=result)
        git = patcher.start()
        self.addCleanup(patcher.stop)
        return git


class HasUpstreamTest(GitQueryTestCase):
    def test_reports_whether_the_branch_has_an_upstream(self):
        git = self.git_returns(git_result(0, stdout="fake-commit\n"))
        self.assertTrue(update._has_upstream())
        git.assert_called_once_with("rev-parse", "--verify", "--quiet", "@{upstream}")

        self.git_returns(git_result(1))
        self.assertFalse(update._has_upstream())


class FetchTest(GitQueryTestCase):
    def test_fetches_and_reports_success(self):
        git = self.git_returns(git_result(0))

        self.assertTrue(update._fetch())
        git.assert_called_once_with("fetch")

    def test_logs_a_failed_fetch(self):
        self.git_returns(git_result(1, stderr="fake-error"))

        with self.assertLogs(update.logger, level="WARNING") as logs:
            self.assertFalse(update._fetch())

        self.assertIn("fake-error", logs.output[0])


class CommitsBehindTest(GitQueryTestCase):
    def test_counts_upstream_commits_not_yet_checked_out(self):
        git = self.git_returns(git_result(0, stdout="3\n"))

        self.assertEqual(update._commits_behind(), 3)
        git.assert_called_once_with("rev-list", "--count", "HEAD..@{upstream}")

    def test_reports_none_and_logs_when_git_fails(self):
        self.git_returns(git_result(128, stderr="fake-error"))

        with self.assertLogs(update.logger, level="WARNING") as logs:
            self.assertEqual(update._commits_behind(), 0)

        self.assertIn("fake-error", logs.output[0])


class IsFastForwardTest(GitQueryTestCase):
    def test_reports_whether_the_checkout_is_an_ancestor_of_the_upstream(self):
        git = self.git_returns(git_result(0))
        self.assertTrue(update._is_fast_forward())
        git.assert_called_once_with("merge-base", "--is-ancestor", "HEAD", "@{upstream}")

        self.git_returns(git_result(1))
        self.assertFalse(update._is_fast_forward())


class HasLocalEditsTest(GitQueryTestCase):
    def test_reports_edits_to_tracked_files(self):
        git = self.git_returns(git_result(0, stdout=" M fake-file.py\n"))

        self.assertTrue(update._has_local_edits())
        git.assert_called_once_with("status", "--porcelain", "--untracked-files=no")

    def test_reports_no_edits_for_a_clean_checkout(self):
        self.git_returns(git_result(0, stdout=""))

        self.assertFalse(update._has_local_edits())

    def test_assumes_edits_when_git_status_fails(self):
        self.git_returns(git_result(128, stderr="fake-error"))

        with self.assertLogs(update.logger, level="WARNING"):
            self.assertTrue(update._has_local_edits())


class ChangedFilesTest(GitQueryTestCase):
    def test_lists_files_the_upstream_changed_since_the_checkout_diverged(self):
        git = self.git_returns(git_result(0, stdout="fake-a.py\nsetup.sh\n"))

        self.assertEqual(update._changed_files(), ["fake-a.py", "setup.sh"])
        git.assert_called_once_with("diff", "--name-only", "HEAD...@{upstream}")


class ApplyUpdateTest(unittest.TestCase):
    def setUp(self):
        for name in ("_discard_local_edits", "_fast_forward"):
            patcher = mock.patch.object(update, name, return_value=True)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_fast_forwards_without_touching_local_edits(self):
        self.assertTrue(update._apply_update(update.KEEP_LOCAL_CHANGES))

        self._discard_local_edits.assert_not_called()
        self._fast_forward.assert_called_once_with()

    def test_discards_local_edits_first_when_set_to_discard(self):
        self.assertTrue(update._apply_update(update.DISCARD_LOCAL_CHANGES))

        self._discard_local_edits.assert_called_once_with()
        self._fast_forward.assert_called_once_with()

    def test_stops_when_discarding_fails(self):
        self._discard_local_edits.return_value = False

        self.assertFalse(update._apply_update(update.DISCARD_LOCAL_CHANGES))
        self._fast_forward.assert_not_called()

    def test_reports_a_failed_fast_forward(self):
        self._fast_forward.return_value = False

        self.assertFalse(update._apply_update(update.SKIP_LOCAL_CHANGES))


class GitActionsTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(update, "_git_action", return_value="fake-success")
        self.git_action = patcher.start()
        self.addCleanup(patcher.stop)

    def test_fast_forward_merges_the_upstream(self):
        self.assertEqual(update._fast_forward(), "fake-success")
        self.git_action.assert_called_once_with(mock.ANY, "merge", "--ff-only", "@{upstream}")

    def test_discard_resets_tracked_files(self):
        self.assertEqual(update._discard_local_edits(), "fake-success")
        self.git_action.assert_called_once_with(mock.ANY, "reset", "--hard")

    def test_restore_moves_the_branch_back_keeping_local_edits(self):
        update._restore("fake-previous-commit")
        self.git_action.assert_called_once_with(mock.ANY, "reset", "--keep", "fake-previous-commit")


class HeadCommitTest(GitQueryTestCase):
    def test_returns_the_full_hash(self):
        git = self.git_returns(git_result(0, stdout="fake-full-hash\n"))

        self.assertEqual(update._head_commit(), "fake-full-hash")
        git.assert_called_once_with("rev-parse", "HEAD")


class GitActionTest(GitQueryTestCase):
    def test_runs_git_and_reports_success(self):
        git = self.git_returns(git_result(0))

        self.assertTrue(update._git_action("fake-failure-message", "fake-argument"))
        git.assert_called_once_with("fake-argument")

    def test_logs_the_failure_with_git_error_and_reports_it(self):
        self.git_returns(git_result(1, stderr="fake-error"))

        with self.assertLogs(update.logger, level="ERROR") as logs:
            self.assertFalse(update._git_action("fake-failure-message", "fake-argument"))

        self.assertIn("fake-failure-message", logs.output[0])
        self.assertIn("fake-error", logs.output[0])


class RunSetupTest(unittest.TestCase):
    def test_runs_setup_and_reports_success(self):
        with mock.patch.object(update.subprocess, "run", return_value=git_result(0)) as run:
            self.assertTrue(update._run_setup())

        run.assert_called_once_with([update.SETUP_SCRIPT])

    def test_logs_a_failed_setup(self):
        with mock.patch.object(update.subprocess, "run", return_value=git_result(1)), \
             self.assertLogs(update.logger, level="ERROR"):
            self.assertFalse(update._run_setup())


class AnnounceTest(unittest.TestCase):
    def test_plays_the_voice_line_and_waits_for_it(self):
        with mock.patch.object(update, "Audio") as audio:
            update._announce("fake-voice", "fake-line.wav")

        audio.assert_called_once_with("audio/Menu/vox/fake-voice/fake-line.wav")
        audio.return_value.start_effect_and_wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
