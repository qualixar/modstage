"""Read-only "ask" runs for headless Antigravity (agy).

Headless agy cannot ask for permission: anything its rules leave at "ask" is refused and the turn
ends. Out of the box that includes reading web pages, so a research run in ask mode stopped after
its first read_url_content (run 120c4f36, 17 Oct 2026).

agy has no per-process grant flag (ANTIGRAVITY_PERM_GRANTS, --mode auto and --mode accept-edits
were tried; none let read_url through). Its project scope does: a project file in
~/.gemini/config/projects/<id>.json carries its own allow/ask lists, and `agy --project <id>`
applies them. So each ask run gets a ModStage-owned project for its folder, removed when the run
ends. Varun's own settings.json and shared config.json are never touched.

Rules (precedence in agy is deny > ask > allow, and "ask" means refused when headless):
  allow  read_url(*)            reading web pages (search_web needs no grant)
         read_file(<cwd>)       reading and listing files in the run's folder
  ask    write_file(<cwd>)      writes in its folder (agy's default would allow them)
         command(*)             shell commands, even ones the user's shared rules allow
Files outside the folder stay at agy's default, which asks, so they are refused too.
Probed on agy 1.4.0, 17 Oct 2026: read_url_content, search_web and view_file inside the folder
ran; write_to_file in the folder (write_file), view_file on /etc/hosts (read_file) and run_command,
including `ls` (command), were refused and listed in result.denied_actions.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

PREFIX = "modstage-"
STALE_AFTER_S = 2 * 24 * 3600  # a crashed bridge leaves its files; the next run sweeps them


def projects_dir() -> Path:
    return Path(os.environ.get("MODSTAGE_AGY_PROJECTS") or Path.home() / ".gemini" / "config" / "projects")


def grants(cwd: str) -> dict:
    folder = os.path.realpath(cwd)
    return {"allow": ["read_url(*)", f"read_file({folder})"],
            "ask": [f"write_file({folder})", "command(*)"]}


def create(run_id: str, cwd: str) -> str:
    """Write a project file for one agy process and return its id (for `agy --project`). Raises OSError.
    Unique per process: a restarted run must not share a file the old process's exit removes."""
    folder = os.path.realpath(cwd)
    pid = f"{PREFIX}{run_id}-{uuid.uuid4().hex[:6]}"
    data = {"id": pid, "name": f"ModStage run {run_id} (read-only, removed when the run ends)",
            "projectResources": {"resources": [{"folderUri": Path(folder).as_uri()}]},
            "permissionGrants": {"permissionGrants": grants(folder), "v2Migrated": True},
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    base = projects_dir()
    base.mkdir(parents=True, exist_ok=True)
    _sweep(base)
    tmp = base / f".{pid}.json.tmp"
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(base / f"{pid}.json")
    return pid


def remove(pid: str) -> None:
    if not pid.startswith(PREFIX):  # only ever delete our own files
        return
    try:
        (projects_dir() / f"{pid}.json").unlink()
    except OSError:
        pass


def _sweep(base: Path) -> None:
    cutoff = time.time() - STALE_AFTER_S
    for path in base.glob(f"{PREFIX}*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass
