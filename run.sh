#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/smanenv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Virtual environment not found at $VENV_DIR"
  echo "Create it with: python3 -m venv smanenv"
  echo "Install deps with: ./smanenv/bin/pip install -r requirements.txt"
  exit 1
fi

exec "$VENV_DIR/bin/python" "$ROOT_DIR/main.py" "$@"
