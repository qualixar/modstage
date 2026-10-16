#!/usr/bin/env bash
# Starts the ModStage bridge on 127.0.0.1 if it is not already answering.
# Data (token, run logs, pid, log) lives in $MODSTAGE_HOME (default ~/.modstage).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
port="${MODSTAGE_PORT:-47321}"
data="${MODSTAGE_HOME:-$HOME/.modstage}"
mkdir -p "$data" && chmod 700 "$data"
health() { curl -sf --max-time 1 "http://127.0.0.1:$port/health" >/dev/null 2>&1; }
health && exit 0
command -v python3 >/dev/null || { echo "modstage needs python3 (3.10 or newer)" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "modstage needs Python 3.10 or newer" >&2; exit 1; }
cd "$here"
nohup python3 -m modstage.server >> "$data/bridge.log" 2>&1 &
for _ in $(seq 1 20); do health && exit 0; sleep 0.25; done
echo "modstage bridge did not start; see $data/bridge.log" >&2
exit 1
