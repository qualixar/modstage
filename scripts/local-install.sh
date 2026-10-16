#!/usr/bin/env bash
# Dev only: install this working copy for every new Claude Code session on this machine,
# the same way a user installs from GitHub, but from a local marketplace folder.
# The copy lives outside ~/Documents so the desktop app is allowed to run it.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
market="${MODSTAGE_MARKET:-$HOME/.local/share/modstage-marketplace}"
mkdir -p "$market"
rsync -a --delete --exclude .git --exclude __pycache__ --exclude node_modules \
  --exclude assets/logo/options --exclude .claude-plugin/types "$here/" "$market/"
claude plugin validate "$market"
claude plugin marketplace list | grep -q "$market" || claude plugin marketplace add "$market"
claude plugin marketplace update modstage
claude plugin uninstall modstage@modstage >/dev/null 2>&1 || true
claude plugin install modstage@modstage
echo "Installed. Open a NEW session to load it."
