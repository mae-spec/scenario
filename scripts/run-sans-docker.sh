#!/bin/sh
# Lancement sans Docker (Python 3.10+ requis), par ex. sur un NAS avec Python ou un PC du réseau.
#   ./scripts/run-sans-docker.sh
# Variables utiles : SCENARIO_HOST (défaut 10.10.30.56), SCENARIO_PORT (8765),
#                    SCENARIO_DATA_DIR (./data), SCENARIO_PASSWORD
set -eu
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
export SCENARIO_HOST="${SCENARIO_HOST:-10.10.30.56}"
export SCENARIO_PORT="${SCENARIO_PORT:-8765}"
export SCENARIO_DATA_DIR="${SCENARIO_DATA_DIR:-$(pwd)/data}"
exec .venv/bin/python -m app.main
