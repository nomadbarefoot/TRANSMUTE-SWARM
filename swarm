#!/bin/bash
# swarm — CLI runner for TRANSMUTE-SWARM
# Usage: ./swarm [command] [options]  or  swarm [command] [options] (if in PATH)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"

# Activate venv if it exists and not already active
if [[ -d "$VENV_PATH" && -z "$VIRTUAL_ENV" ]]; then
    source "$VENV_PATH/bin/activate"
fi

# Run swarm CLI
exec swarm "$@"
