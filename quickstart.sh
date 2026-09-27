#!/usr/bin/env bash
# Backward-compatible convenience entrypoint.
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  ./setup_macos.sh
fi
exec ./run_macos.sh
