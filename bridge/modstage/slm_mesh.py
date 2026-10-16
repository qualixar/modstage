"""Optional mirror to SuperLocalMemory's SLM-mesh, for people who run SLM.

When the SLM daemon answers on 127.0.0.1:8765 and the `slm` CLI is installed, each ModStage run is
registered as a mesh peer, board messages are mirrored to the mesh, and exclusive claims are
mirrored as mesh locks, so Claude Code windows and bots outside ModStage see the same picture.
The local board stays the source of truth: every call here is best-effort with short timeouts,
and the mirror switches itself off on the first failure it cannot recover from.

Turn it off with MODSTAGE_SLM_MESH=0. The install token is read once from `slm token show`,
kept in memory, and never logged.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

SLM = os.environ.get("MODSTAGE_SLM_URL", "http://127.0.0.1:8765")


class Mesh:
    def __init__(self):
        self._token: str | None = None
        self._peers: dict[str, str] = {}  # run_id -> peer_id
        self._lock = threading.Lock()
        self.state = "off"  # off | on | unavailable
        self.reason = ""

    def enable(self) -> None:
        if os.environ.get("MODSTAGE_SLM_MESH", "1") == "0":
            self.state, self.reason = "off", "disabled by MODSTAGE_SLM_MESH=0"
            return
        if not shutil.which("slm"):
            self.state, self.reason = "unavailable", "SuperLocalMemory is not installed"
            return
        try:
            with urllib.request.urlopen(f"{SLM}/health", timeout=8) as resp:
                ok = json.loads(resp.read() or b"{}").get("status") == "ok"
        except (OSError, ValueError):
            ok = False
        if not ok:
            self.state, self.reason = "unavailable", "the SLM daemon is not running"
            return
        try:
            out = subprocess.run(["slm", "token", "show"], capture_output=True, text=True, timeout=10)
            token = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else ""
        except (OSError, subprocess.TimeoutExpired, IndexError):
            token = ""
        if not token:
            self.state, self.reason = "unavailable", "could not read the SLM install token"
            return
        self._token = token
        self.state, self.reason = "on", "mirroring to SLM-mesh"

    def _post(self, path: str, body: dict) -> dict | None:
        if self.state != "on":
            return None
        req = urllib.request.Request(f"{SLM}/mesh{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Install-Token": self._token or ""})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 503):
                self.state, self.reason = "unavailable", f"SLM-mesh refused the mirror ({exc.code})"
            return None
        except (OSError, ValueError):
            return None

    # ---- mirror hooks (called by the board API and the bridge keeper) ----

    def joined(self, run) -> None:
        res = self._post("/register", {"session_id": f"modstage-{run.id}", "summary": f"{run.engine}: {run.label}"[:200],
                                       "project_path": run.cwd, "agent_type": f"modstage-{run.engine}"})
        peer = (res or {}).get("peer_id")
        if peer:
            with self._lock:
                self._peers[run.id] = peer

    def heartbeat(self, run) -> None:
        peer = self._peers.get(run.id)
        if peer:
            self._post("/heartbeat", {"peer_id": peer})

    def message(self, run, to: str, body: str) -> None:
        peer = self._peers.get(run.id)
        if peer:
            target = self._peers.get(to) or ("broadcast" if to == "all" else None)
            if target is None:
                return  # only mirror to ModStage runs or as a broadcast, never to an arbitrary mesh peer
            self._post("/send", {"from_peer": peer, "to": target, "content": f"[modstage {run.engine} {run.id}] {body}"[:4000]})

    def lock(self, run, path: str, acquire: bool) -> None:
        if self._peers.get(run.id):
            full = os.path.normpath(os.path.join(run.cwd, path))
            if not full.startswith(os.path.normpath(run.cwd) + os.sep):
                return  # never lock a path outside the run's folder
            self._post("/lock", {"file_path": full, "locked_by": f"modstage-{run.id}",
                                 "action": "acquire" if acquire else "release"})

    def left(self, run) -> None:
        with self._lock:
            peer = self._peers.pop(run.id, None)
        if peer:
            self._post("/deregister", {"peer_id": peer})


MESH = Mesh()


def bg(fn, *args) -> None:
    """Run a mirror call off the request path: SLM must never slow an agent down."""
    if MESH.state == "on":
        threading.Thread(target=fn, args=args, daemon=True).start()
