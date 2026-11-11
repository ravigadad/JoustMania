# Updates

[Back to the main README](../../README.md)

## When JoustMania checks

On Linux, JoustMania checks its own git checkout for updates each time it starts. It compares the checked-out branch with that branch's upstream, the remote branch git has it set to track. A checkout of `master` cloned from GitHub tracks `origin/master`, so it follows the official repository. A checkout of another branch follows that branch's upstream. A branch with no upstream isn't checked, and the log says so.

JoustMania runs as root, but its directory belongs to an ordinary account, and git refuses to work in a repository another account owns. So every git command runs as the account that owns the JoustMania directory.

Updates only move the branch forward. If the checkout has commits its upstream doesn't, JoustMania doesn't update and logs why.

## Small and large updates

A small update is applied straight away and announced as "JoustMania updated". The new version runs the next time JoustMania starts.

An update that changes `setup.sh` is a large update. JoustMania announces it and waits until someone presses the start and select buttons on a controller. It then applies the update and runs `setup.sh`, which reboots the Pi once it succeeds. If either step fails, the checkout goes back to the commit it was on and JoustMania announces that the update failed.

If the access point is enabled, it may need to be disabled first so the Pi can reach the internet.

## Files edited on the Pi

The **Updating when files on this machine have been edited** setting, under Admin Settings, decides what happens when tracked files in the checkout have been edited:

- **Don't update** (the default): JoustMania skips the update and logs why.
- **Update if the edits don't conflict**: the update goes ahead when it doesn't touch the edited files. When it does, git stops and nothing changes.
- **Discard the edits and update**: edits to tracked files are reverted, then the update is applied.

New files that git doesn't track, such as added songs, don't count as edits and are never removed. Neither are files git ignores, such as `joustsettings.yaml`, `venv/` and `logs/`.

## When an update doesn't happen

Each reason JoustMania skips or fails an update is logged with git's own message. Under supervisor, that log is `/var/log/joustmania-out.log`.
