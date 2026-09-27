#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")/.."
VGET_WORKSPACE="${VGET_DATA_DIR:-.vget}"
if [[ ! -f "$VGET_WORKSPACE/state.json" ]]; then
  ./vget-cli --workspace "$VGET_WORKSPACE" init >/dev/null
fi
exec ./vget-cli --workspace "$VGET_WORKSPACE" serve --port "${VGET_PORT:-8766}"
