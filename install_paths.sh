# Sourced by JoustMania's scripts to find the install. It goes by where this file is
# and who owns it, not by who is logged in, because a headless boot running
# JoustMania under supervisor has nobody logged in.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
HOMENAME="$(stat -c %U "$APP_DIR")"
HOMEDIR="$(getent passwd "$HOMENAME" | cut -d: -f6)"
