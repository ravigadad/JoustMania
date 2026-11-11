#!/bin/bash

#for debugging the webui without starting the whole app

#root needed since psmove still gets imported
if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

source "$(dirname "$(readlink -f "$0")")/install_paths.sh"

export HOME="$APP_DIR"
export PSMOVEAPI_LIBRARY_PATH="$HOMEDIR/psmoveapi/build"
export PYTHONPATH="$HOMEDIR/psmoveapi/bindings/python"
"$APP_DIR/venv/bin/python3" "$APP_DIR/webui.py"
