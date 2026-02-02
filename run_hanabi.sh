#!/bin/bash
# Wrapper script to run hanabi.py with required LD_PRELOAD for TBB
# Usage: ./run_hanabi.sh [arguments to hanabi.py]

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set LD_PRELOAD to load TBB library (required for hana_sim.so)
export LD_PRELOAD=/lib/x86_64-linux-gnu/libtbb.so.12

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run hanabi.py with all arguments
exec python hanabi.py "$@"

