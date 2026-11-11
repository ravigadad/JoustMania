#!/bin/bash

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

source "$(dirname "$(readlink -f "$0")")/install_paths.sh"

export HOME="/root"
export PSMOVEAPI_LIBRARY_PATH="$HOMEDIR/psmoveapi/build"
export PYTHONPATH="$HOMEDIR/psmoveapi/bindings/python"
exec "$APP_DIR/venv/bin/python3" "$APP_DIR/piparty.py"
