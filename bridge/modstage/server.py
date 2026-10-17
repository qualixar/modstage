"""ModStage bridge: holds Codex / Muse / Grok sessions open and serves them on localhost.

Every request needs the header X-ModStage-Token with the contents of $MODSTAGE_HOME/token
(default ~/.modstage/token, mode 0600).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import board_api, registry
from .board import all_boards, board_for
from .claims import BOARD
from .run import RUNS, Run
from .slm_mesh import MESH, bg

HOME = Path(os.environ.get("MODSTAGE_HOME", Path.home() / ".modstage"))
PORT = int(os.environ.get("MODSTAGE_PORT", "47321"))


def _adapter(run: Run):
    protocol = run.spec["protocol"]
    if protocol == "codex-app-server":
        from .codex import CodexAdapter
        return CodexAdapter(run)
    if protocol == "muse-msp":
        from .muse import MuseAdapter
        return MuseAdapter(run)
    if protocol == "stream-json":
        from .stream_json import StreamJsonAdapter
        return StreamJsonAdapter(run)
    from .acp import AcpAdapter
    return AcpAdapter(run)


def _token() -> str:
    path = HOME / "token"
    HOME.mkdir(parents=True, exist_ok=True)
    HOME.chmod(0o700)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # never readable by others, not even briefly
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(24))
    return path.read_text().strip()


def start_run(body: dict) -> Run:
    agents = registry.load()
    engine = body.get("engine", "")
    if engine not in agents:
        raise ValueError(f"unknown agent '{engine}'. Plugged in: {', '.join(agents)}")
    spec = agents[engine]
    if not shutil.which(spec["command"][0]):
        raise ValueError(f"{spec.get('name', engine)} is not installed ({spec['command'][0]} not found on PATH)")
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is empty")
    cwd = os.path.abspath(os.path.expanduser(body.get("cwd") or os.getcwd()))
    if not os.path.isdir(cwd):
        raise ValueError(f"cwd {cwd} is not a folder")
    owns = body.get("owns") or []
    if not isinstance(owns, list) or not all(isinstance(o, str) for o in owns):
        raise ValueError("owns must be a list of file paths or glob patterns")
    run = Run(spec, prompt, cwd, body.get("model"), body.get("label"), body.get("autonomy", "ask"), owns,
              owner=str(body.get("session") or ""))
    run.start_images = images_from(body)
    RUNS[run.id] = run
    BOARD.register(run)
    run.add("you", prompt)
    if run.autonomy == "auto":
        run.add("status", "autonomous: approvals are answered automatically (claimed-file conflicts still ask you)")
    _boot(run)
    return run


def _boot(run: Run) -> None:
    """Start the run's agent process in the background; failures land in the run's own log."""
    def boot():
        try:
            run.adapter = _adapter(run)
            run.adapter.start()
        except Exception as exc:  # shown in the panel and returned by status
            run.add("error", f"could not start {run.spec.get('name', run.engine)}: {exc}")
            run.set(status="error", error=str(exc), activity="failed to start")

    threading.Thread(target=boot, daemon=True).start()


ENDED = ("done", "error")


def _ended(run: Run) -> bool:
    """True when nothing is left to talk to: the run ended, or its agent process has exited
    (Antigravity stops its process to interrupt)."""
    if run.status in ENDED:
        return True
    adapter = run.adapter
    proc = getattr(adapter, "proc", None) or getattr(getattr(adapter, "rpc", None), "proc", None)
    return proc is not None and proc.poll() is not None


def revive(run: Run, text: str, echo: bool = True) -> str:
    """A message to a run whose agent process has ended starts a fresh process in the same folder,
    handed a recap of the run so far, so the conversation carries on instead of failing."""
    old = run.adapter
    run.adapter = None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    run.prompt = (f"You are picking up an earlier session in this folder that ended. What happened so far:\n"
                  f"{run.recap()}\n\nNew message from the user:\n{text}")
    if echo:
        run.add("you", text)
    run.add("status", "the agent had stopped: started it again with a recap of this run")
    run.set(status="starting", activity="restarting", error=None)
    BOARD.register(run)
    _boot(run)
    return "the agent had stopped; restarted it with a recap of this run"


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def images_from(body: dict) -> list[dict]:
    """Validated images for a turn: [{path, media_type}]. Paths must be absolute image files."""
    raw = body.get("images") or []
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        raise ValueError("images must be a list of absolute file paths")
    if len(raw) > 8:
        raise ValueError("at most 8 images per message")
    out = []
    for path in raw:
        full = os.path.realpath(os.path.expanduser(path))
        kind = IMAGE_TYPES.get(os.path.splitext(full)[1].lower())
        if not os.path.isabs(full) or not os.path.isfile(full):
            raise ValueError(f"image {path} is not an existing file (give an absolute path)")
        if not kind:
            raise ValueError(f"image {path} is not a png, jpg, gif or webp file")
        if os.path.getsize(full) > MAX_IMAGE_BYTES:
            raise ValueError(f"image {path} is larger than 10 MB")
        with open(full, "rb") as f:
            head = f.read(12)
        if not (head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or head[:4] == b"GIF8"
                or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")):
            raise ValueError(f"image {path} is not a png, jpg, gif or webp image")
        out.append({"path": full, "media_type": kind})
    return out


def send_now(run: Run) -> str:
    """'Interrupt and send now': end the running turn so the queued messages run at once."""
    adapter = run.adapter
    if not run.queued:
        return "nothing is queued"
    if getattr(adapter, "restarts_to_interrupt", False):
        # this CLI stops its process to interrupt: carry the queued messages into the restart
        texts = adapter.queued_texts()
        adapter.interrupt()
        run.set(queued=0)
        return revive(run, "\n\n".join(texts), echo=False)
    return adapter.interrupt() + "; the queued message runs now"


def send_refusal(run: Run) -> str:
    return run.send_refusal()


def mine(session: str):
    """Runs a Claude session may see: its own, or every run when no session is named (CLI, tests)."""
    return [r for r in RUNS.values() if not session or r.owner == session]


def decide(run: Run, body: dict) -> tuple[int, dict]:
    """Answer one pending approval. Only the session that owns the run may answer it."""
    session = str(body.get("session") or "")
    if run.owner and session != run.owner:  # an approval is answered only from the session that owns the run
        return 403, {"error": "this run belongs to another Claude Code session; answer it there"}
    choice = str(body.get("choice", ""))
    if choice not in ("allow", "allow_session", "deny"):
        return 400, {"error": "choice must be allow, allow_session or deny"}
    ok = run.decide(str(body.get("approval_id", "")), choice, by=str(body.get("by") or ""))
    return (200, {"ok": ok}) if ok else (404, {"error": "no such pending approval"})


def close_run(run: Run) -> None:
    """End the agent and forget the run: its tab goes away and its claims are released."""
    adapter, run.adapter = run.adapter, None  # its exit callback now sees it is no longer the run's
    if adapter is not None:
        try:
            adapter.close()
        except Exception:
            pass
    if run.status not in ENDED:
        run.set(status="done", activity="closed")
    RUNS.pop(run.id, None)
    run.close_log()


MAX_BODY = 4 * 1024 * 1024  # images travel as paths, so no real request comes near this


def _same(given: str, expected: str) -> bool:
    return secrets.compare_digest(given.encode("utf-8", "replace"), expected.encode("utf-8", "replace"))


def _not_yours(run: Run, session: str) -> bool:
    """True when a Claude session acts on a run another session started. Requests without a session
    (the CLI, tests) are allowed; the mod always names its session."""
    return bool(run.owner and session and session != run.owner)


class Handler(BaseHTTPRequestHandler):
    token = ""
    timeout = 60  # a client that stops sending mid-request does not hold a thread forever

    def log_message(self, *args):  # quiet
        pass

    def _reply(self, code: int, data) -> None:
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the panel gave up on a slow poll and hung up; nothing to deliver

    def _authorised(self) -> bool:
        if _same(self.headers.get("X-ModStage-Token", ""), self.token):
            return True
        self._reply(401, {"error": "bad or missing X-ModStage-Token"})
        return False

    def _caller(self, body: dict) -> Run | None:
        """The run making a board call: its own per-run token, or the main token plus run_id."""
        run_token = self.headers.get("X-ModStage-Run-Token", "")
        if run_token:
            for run in list(RUNS.values()):
                if _same(run_token, run.board_token):
                    return run
            self._reply(401, {"error": "unknown run token"})
            return None
        if _same(self.headers.get("X-ModStage-Token", ""), self.token):
            run = RUNS.get(str(body.get("run_id", "")))
            if run is None:
                self._reply(404, {"error": "run_id is required with the main token"})
            return run
        self._reply(401, {"error": "bad or missing token"})
        return None

    def _run(self, rid: str) -> Run | None:
        run = RUNS.get(rid)
        if run is None:
            self._reply(404, {"error": f"no run {rid}"})
        return run

    def _known_token(self) -> bool:
        """Any valid token, checked before the body is read: an unauthenticated caller (a web page's simple
        POST) never makes the bridge read or parse anything."""
        if _same(self.headers.get("X-ModStage-Token", ""), self.token):
            return True
        run_token = self.headers.get("X-ModStage-Run-Token", "")
        return bool(run_token) and any(_same(run_token, r.board_token) for r in list(RUNS.values()))

    def do_GET(self):
        try:
            self._get()
        except (ValueError, TypeError) as exc:
            self._reply(400, {"error": str(exc)[:300]})
        except Exception as exc:
            self._reply(500, {"error": str(exc)[:300]})

    def do_POST(self):
        try:
            self._post()
        except (ValueError, TypeError) as exc:
            self._reply(400, {"error": str(exc)[:300]})
        except Exception as exc:
            self._reply(500, {"error": str(exc)[:300]})

    def _get(self):
        url = urlparse(self.path)
        if url.path == "/health":
            return self._reply(200, {"ok": True, "runs": len(RUNS)})
        if not self._authorised():
            return
        query = parse_qs(url.query)
        parts = [p for p in url.path.split("/") if p]
        session = query.get("session", [""])[0]
        if parts == ["runs"]:
            own = mine(session)
            return self._reply(200, {"runs": [r.summary() for r in own], "others": len(RUNS) - len(own)})
        if parts == ["agents"]:
            return self._reply(200, registry.doctor())
        if parts == ["board"]:
            cwd = query.get("cwd", [""])[0]
            if cwd and not (os.path.isabs(cwd) and os.path.isdir(cwd)):
                return self._reply(400, {"error": "cwd must be an existing absolute folder"})
            boards = [board_for(os.path.normpath(cwd))] if cwd else all_boards()
            return self._reply(200, {"boards": [b.read() for b in boards]})
        if parts == ["coordination"]:
            return self._reply(200, {"board": "on", "slm_mesh": MESH.state, "slm_mesh_note": MESH.reason})
        if parts == ["inbox"]:
            items = [item for r in mine(session) for item in r.summary()["pending"]]
            return self._reply(200, {"pending": sorted(items, key=lambda i: i["asked_at"])})
        if len(parts) >= 2 and parts[0] == "runs" and (run := self._run(parts[1])):
            if _not_yours(run, session):
                return self._reply(403, {"error": "this run belongs to another Claude Code session"})
            if len(parts) == 2:
                return self._reply(200, run.detail(int(query.get("after", ["0"])[0])))
            if parts[2] == "wait":
                finished = run.wait(min(float(query.get("timeout", ["600"])[0]), 3600),
                                    through_approvals=query.get("until", [""])[0] == "turn_end")
                data = run.detail(int(query.get("after", ["0"])[0]))
                data["timed_out"] = not finished
                return self._reply(200, data)
        self._reply(404, {"error": "not found"})

    def _post(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if not self._known_token():
            return self._reply(401, {"error": "bad or missing token"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._reply(400, {"error": "bad Content-Length"})
        if length < 0 or length > MAX_BODY:
            return self._reply(413, {"error": f"body must be 0 to {MAX_BODY} bytes"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._reply(400, {"error": "body is not JSON"})
        if not isinstance(body, dict):
            return self._reply(400, {"error": "body must be a JSON object"})
        if len(parts) == 2 and parts[0] == "board":
            caller = self._caller(body)
            if caller is None:
                return
            try:
                return self._reply(200, board_api.perform(parts[1], caller, body, wake))
            except ValueError as exc:
                return self._reply(400, {"error": str(exc)})
            except Exception as exc:
                return self._reply(500, {"error": str(exc)})
        if not self._authorised():
            return
        try:
            if len(parts) == 2 and parts[0] == "claude":
                from . import claude_peer
                if parts[1] == "edit_check":
                    held = claude_peer.edit_conflicts(str(body.get("session") or ""), str(body.get("path") or ""))
                    return self._reply(200, {"held": held})
                return self._reply(200, claude_peer.perform(parts[1], body, wake))
            if parts == ["runs"]:
                images_from(body)  # refuse a bad path before starting anything
                return self._reply(200, start_run(body).summary())
            if len(parts) == 3 and parts[0] == "runs" and (run := self._run(parts[1])):
                if parts[2] != "decide" and _not_yours(run, str(body.get("session") or "")):
                    return self._reply(403, {"error": "this run belongs to another Claude Code session"})
                if parts[2] == "close":
                    close_run(run)
                    return self._reply(200, {"ok": "closed"})
                if parts[2] == "decide":
                    return self._reply(*decide(run, body))
                text = str(body.get("text", "")).strip()
                if parts[2] == "send" and not text:
                    return self._reply(400, {"error": "message is empty"})
                if parts[2] == "send" and (refusal := send_refusal(run)):
                    return self._reply(409, {"error": refusal})
                if parts[2] == "send" and _ended(run):
                    return self._reply(200, {"ok": revive(run, text)})
                if run.adapter is None:
                    return self._reply(409, {"error": "the agent is still starting; try again in a moment"})
                if parts[2] == "send":
                    pics = images_from(body)
                    ok = run.adapter.send(with_digest(run, text), images=pics) if pics else run.adapter.send(with_digest(run, text))
                    if body.get("now") and run.queued:
                        ok += "; " + send_now(run)
                    return self._reply(200, {"ok": ok})
                if parts[2] == "jump":
                    return self._reply(200, {"ok": send_now(run)})
                if parts[2] == "interrupt":
                    if run.status not in ("starting", "running"):
                        return self._reply(200, {"ok": "nothing to interrupt: the run is not working"})
                    return self._reply(200, {"ok": run.adapter.interrupt()})
            elif len(parts) == 3:
                return
            self._reply(404, {"error": "not found"})
        except ValueError as exc:
            self._reply(400, {"error": str(exc)})
        except Exception as exc:
            self._reply(500, {"error": str(exc)})


def with_digest(run: Run, text: str) -> str:
    """Prepend unread messages from other agents to a new turn's text."""
    digest = board_for(run.cwd).digest(run.id)
    return f"{digest}\n{text}" if digest else text


def wake(run: Run) -> None:
    """Start a turn for an idle run that received a message meant to wake it."""
    try:
        run.adapter.send(with_digest(run, "You have new messages from other agents above. Act on them if they concern your task."))
    except Exception as exc:
        run.add("warning", f"could not wake this run: {exc}")


def _renew_working() -> None:
    """Renew the leases of runs that are working right now. An idle, interrupted or finished run is NOT renewed:
    its leases lapse, which is what lets another run take the file and makes the write-time fence meaningful."""
    for run in list(RUNS.values()):
        if run.status in ("starting", "running"):
            try:
                board_for(run.cwd).renew(run.id)
                board_for(run.cwd).heartbeat(run.id, "working")
                bg(MESH.heartbeat, run)
            except Exception:
                pass


def _keeper() -> None:
    """Every 30 s: renew leases of working runs, heartbeat them, and sweep old board rows."""
    import time
    while True:
        time.sleep(30)
        _renew_working()
        tick = getattr(_keeper, "tick", 0) + 1
        _keeper.tick = tick
        if MESH.state == "unavailable" and tick % 10 == 0:  # retry SLM every 5 minutes
            MESH.enable()
        for board in all_boards():
            try:
                board.sweep()
                board.write_state()
            except Exception:
                pass


def main() -> None:
    threading.Thread(target=_keeper, daemon=True).start()
    threading.Thread(target=MESH.enable, daemon=True).start()
    registry.prefetch_models()
    Handler.token = _token()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "bridge.pid").write_text(str(os.getpid()))
    print(f"modstage bridge on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
