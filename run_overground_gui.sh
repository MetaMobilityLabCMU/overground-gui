#!/usr/bin/env bash
# Launch Overground GUI using the jinwoo-gui conda env (standalone entrypoint).
set -euo pipefail

ENV_NAME="jinwoo-gui"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer conda run so activation is not required in the caller shell.
if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  eval "$(conda shell.bash hook 2>/dev/null)" || true
  if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    exec conda run --no-capture-output -n "${ENV_NAME}" overground-gui "$@"
  fi
fi

# Fallback: local editable install / current python
if command -v overground-gui >/dev/null 2>&1; then
  exec overground-gui "$@"
fi

export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec python -m overground_gui "$@"
