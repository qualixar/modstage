#!/usr/bin/env bash
# Dev only: copy this repo into the session's hot-reloading mods folder.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --delete --exclude .git --exclude .claude-plugin/types --exclude node_modules "$here/" "$1/"
