"""Checks JoustMania's own git checkout for updates at startup and applies them.

JoustMania runs as root, but its checkout belongs to an ordinary account. Git refuses
to work in a repository another account owns, so every git command runs as the
checkout's owner."""
import logging
import os
import subprocess

from piaudio import Audio

logger = logging.getLogger(__name__)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_SCRIPT = os.path.join(APP_DIR, "setup.sh")

# What an update does when tracked files have been edited on this machine.
SKIP_LOCAL_CHANGES = "skip"
KEEP_LOCAL_CHANGES = "keep"
DISCARD_LOCAL_CHANGES = "discard"


def check_for_update(voice, local_changes):
    """Applies and announces a small update. Returns True when the update changes
    setup.sh, which waits for an admin to start it through big_update."""
    if not _has_upstream():
        logger.info("The checked-out branch has no upstream branch, so it isn't checked for updates")
        return False
    if not _fetch() or _commits_behind() == 0:
        return False
    if not _is_fast_forward():
        logger.warning("Not updating: the checkout has commits its upstream branch doesn't")
        return False
    if local_changes not in (KEEP_LOCAL_CHANGES, DISCARD_LOCAL_CHANGES) and _has_local_edits():
        logger.warning("Not updating: tracked files have local edits")
        return False
    if "setup.sh" in _changed_files():
        _announce(voice, "large_update.wav")
        return True
    if _apply_update(local_changes):
        _announce(voice, "joustmania_updated.wav")
    return False


def big_update(voice, local_changes):
    """Applies the update and runs setup.sh, which reboots the machine once it
    succeeds. On failure, the checkout goes back to the commit it was on."""
    _announce(voice, "update_started.wav")
    previous_commit = _head_commit()
    if _apply_update(local_changes) and _run_setup():
        return
    _restore(previous_commit)
    _announce(voice, "joustmania_failed.wav")


def current_commit():
    result = _git("rev-parse", "--short=7", "HEAD")
    if result.returncode != 0:
        logger.warning("Couldn't read the current commit: %s", result.stderr.strip())
        return ""
    return result.stdout.strip()


def _git(*arguments):
    owner = _checkout_owner()
    command = ["git", "-C", APP_DIR, *arguments]
    if os.geteuid() != owner.pw_uid:
        command = ["runuser", "-u", owner.pw_name, "--", *command]
    return subprocess.run(command, capture_output=True, text=True)


def _checkout_owner():
    # Imported here because pwd doesn't exist on Windows, where piparty still imports
    # this module for its setting values.
    import pwd
    return pwd.getpwuid(os.stat(APP_DIR).st_uid)


def _has_upstream():
    return _git("rev-parse", "--verify", "--quiet", "@{upstream}").returncode == 0


def _fetch():
    result = _git("fetch")
    if result.returncode != 0:
        logger.warning("Couldn't check for updates: %s", result.stderr.strip())
    return result.returncode == 0


def _commits_behind():
    result = _git("rev-list", "--count", "HEAD..@{upstream}")
    if result.returncode != 0:
        logger.warning("Couldn't compare with the upstream branch: %s", result.stderr.strip())
        return 0
    return int(result.stdout)


def _is_fast_forward():
    return _git("merge-base", "--is-ancestor", "HEAD", "@{upstream}").returncode == 0


def _has_local_edits():
    """Untracked files, such as added songs, don't count as edits."""
    result = _git("status", "--porcelain", "--untracked-files=no")
    if result.returncode != 0:
        logger.warning("Couldn't check for local edits, so assuming there are some: %s", result.stderr.strip())
        return True
    return bool(result.stdout.strip())


def _changed_files():
    """The three-dot range lists only what changed upstream, not commits made here."""
    return _git("diff", "--name-only", "HEAD...@{upstream}").stdout.split()


def _apply_update(local_changes):
    if local_changes == DISCARD_LOCAL_CHANGES and not _discard_local_edits():
        return False
    return _fast_forward()


def _fast_forward():
    return _git_action("Couldn't apply the update", "merge", "--ff-only", "@{upstream}")


def _discard_local_edits():
    return _git_action("Couldn't discard local edits", "reset", "--hard")


def _restore(commit):
    # --keep, unlike --hard, leaves local edits in place.
    _git_action("Couldn't restore the previous version", "reset", "--keep", commit)


def _head_commit():
    return _git("rev-parse", "HEAD").stdout.strip()


def _git_action(failure_message, *arguments):
    result = _git(*arguments)
    if result.returncode != 0:
        logger.error("%s: %s", failure_message, result.stderr.strip())
    return result.returncode == 0


def _run_setup():
    result = subprocess.run([SETUP_SCRIPT])
    if result.returncode != 0:
        logger.error("setup.sh failed with exit status %s", result.returncode)
    return result.returncode == 0


def _announce(voice, line):
    Audio("audio/Menu/vox/" + voice + "/" + line).start_effect_and_wait()
