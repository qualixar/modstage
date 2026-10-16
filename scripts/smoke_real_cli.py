#!/usr/bin/env python3
"""Manual smoke test against a REAL agent CLI, one agent per call. It costs tokens: tiny prompts only.

    python3 scripts/smoke_real_cli.py codex --model gpt-6-luna
    python3 scripts/smoke_real_cli.py grok --approval      # also checks an approval reaches the inbox

It starts its own throwaway bridge from this repo (port 47399, a temp MODSTAGE_HOME, mesh off), so it
never touches the bridge or the installed plugin you use day to day. Checks: start, a streamed reply,
a follow-up turn, interrupt, close; with --approval, a command that needs permission raises a Needs-you
item (or, for agents that cannot ask, a visible denial), which this script then DENIES.
Never run more than two of these at once.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
PORT = 47399


def call(token: str, method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-ModStage-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as reply:
            return json.loads(reply.read() or b"{}")
    except urllib.error.HTTPError as err:
        return {"http_error": err.code, **json.loads(err.read() or b"{}")}


def wait(token: str, rid: str, seconds: float) -> dict:
    end = time.time() + seconds
    while True:
        d = call(token, "GET", f"/runs/{rid}/wait?timeout=15", timeout=30)
        if not d.get("timed_out") or time.time() > end:
            return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--model")
    ap.add_argument("--approval", action="store_true")
    ap.add_argument("--budget-s", type=float, default=240)
    args = ap.parse_args()

    home = tempfile.mkdtemp(prefix="modstage-smoke-")
    work = tempfile.mkdtemp(prefix="modstage-smoke-work-")
    env = {**os.environ, "MODSTAGE_HOME": home, "MODSTAGE_PORT": str(PORT), "MODSTAGE_SLM_MESH": "0",
           "PYTHONPATH": str(BRIDGE)}
    server = subprocess.Popen([sys.executable, "-m", "modstage.server"], cwd=str(BRIDGE), env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results: dict[str, str] = {}
    try:
        for _ in range(50):
            if (Path(home) / "token").exists():
                break
            time.sleep(0.2)
        time.sleep(0.5)
        token = (Path(home) / "token").read_text().strip()
        started = call(token, "POST", "/runs", {"engine": args.agent, "cwd": work, "autonomy": "ask",
                                                "prompt": "Reply with the single word PONG and nothing else.",
                                                **({"model": args.model} if args.model else {})})
        if "id" not in started:
            print(json.dumps(started, indent=1))
            return 1
        rid = started["id"]
        results["start"] = "ok"
        d = wait(token, rid, args.budget_s)
        results["stream"] = "ok" if "PONG" in (d.get("final_text") or "").upper() else \
            f"no PONG ({d.get('status')}: {d.get('error') or ''}) last: " + " | ".join(
                f"{e['kind']} {e['text'][:120]}" for e in d.get("new_events", [])[-4:])
        call(token, "POST", f"/runs/{rid}/send", {"text": "Reply with the single word AGAIN."})
        d = wait(token, rid, args.budget_s)
        results["follow-up"] = "ok" if "AGAIN" in (d.get("final_text") or "").upper() else f"no AGAIN ({d.get('status')})"
        if args.approval:
            call(token, "POST", f"/runs/{rid}/send",
                 {"text": "Use your shell tool to run exactly: curl -sI https://example.com . If it is refused, say REFUSED."})
            d = wait(token, rid, args.budget_s)
            pending = d.get("pending") or []
            kinds = [e["kind"] for e in d.get("new_events", [])]
            if pending:
                results["approval"] = f"surfaced: {pending[0]['title']}"
                call(token, "POST", f"/runs/{rid}/decide", {"approval_id": pending[0]["id"], "choice": "deny"})
                wait(token, rid, args.budget_s)
            elif "denied" in kinds:
                results["approval"] = "CLI cannot ask: denial shown"
            else:
                results["approval"] = f"nothing surfaced (status {d.get('status')}, note: {d.get('approval_note')!r})"
        call(token, "POST", f"/runs/{rid}/send", {"text": "Count slowly from 1 to 200, one number per line."})
        time.sleep(4)
        results["interrupt"] = str(call(token, "POST", f"/runs/{rid}/interrupt").get("ok"))
        results["close"] = str(call(token, "POST", f"/runs/{rid}/close").get("ok"))
        usage = d.get("usage") or {}
        results["tokens"] = f"in {usage.get('input')} out {usage.get('output')}"
    finally:
        server.terminate()
    print(json.dumps({"agent": args.agent, "model": args.model, **results}, indent=1))
    return 0 if all(not v.startswith("no ") for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
