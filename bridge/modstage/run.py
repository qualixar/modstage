"""A run: one external agent session and everything seen of it.

Holds the event log, usage, the Needs-you inbox (approval requests waiting on a person),
the files this run has touched (for claims), and when it last did anything (stuck detection).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

RUNS_DIR = Path(os.environ.get("MODSTAGE_HOME", Path.home() / ".modstage")) / "runs"
MAX_EVENTS = 4000
LIVE = ("starting", "running")
APPROVAL_TIMEOUT_S = float(os.environ.get("MODSTAGE_APPROVAL_TIMEOUT", "600"))
STUCK_AFTER_S = 300

# every run this bridge holds, by id (shared by the server, claims and the board API)
RUNS: dict[str, "Run"] = {}

# answer(choice) where choice is "allow", "allow_session" or "deny"
Answer = Callable[[str], None]


class Run:
    def __init__(self, spec: dict, prompt: str, cwd: str, model: str | None, label: str | None,
                 autonomy: str = "ask", owns: list[str] | None = None, owner: str = ""):
        self.id = uuid.uuid4().hex[:8]
        self.engine = spec["id"]
        self.spec = spec
        self.prompt = prompt
        self.cwd = cwd
        self.model = model
        self.label = label or prompt.strip().splitlines()[0][:80]
        self.autonomy = "auto" if autonomy == "auto" else "ask"
        self.owns = list(owns or [])
        # the Claude Code session that started this run: its panel, band and tools see it, others do not
        self.owner = owner or ""
        # set when the CLI refused an action it could not ask about (headless agy); cleared on the next turn
        self.blocked = ""
        # messages sent while a turn runs that the CLI holds until it ends (agents that cannot steer)
        self.queued = 0
        self.start_images: list[dict] = []  # images handed over with the task, sent with the first turn
        from .registry import _approval_note
        self.approval_note = _approval_note(spec)
        self.status = "starting"
        self.activity = "starting"
        self.started_at = time.time()
        self.last_activity = self.started_at
        self.ended_at: float | None = None
        self.final_text = ""
        self.partial = ""
        self.error: str | None = None
        self.session_id: str | None = None
        self.usage = {
            "input": 0, "cached": 0, "output": 0, "reasoning": 0,
            "context_used": 0, "context_window": None, "cost_usd": None,
        }
        self.touched: list[str] = []
        self.board_token = uuid.uuid4().hex + uuid.uuid4().hex
        self.coordination = "prompt"  # becomes "mcp" when the agent's ModStage tools connect
        self.pending: dict[str, dict] = {}
        self._answers: dict[str, Answer] = {}
        self._timers: dict[str, threading.Timer] = {}
        self.events: list[dict] = []
        self.seq = 0
        self.adapter = None
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._log = (RUNS_DIR / f"{self.id}.jsonl").open("a", encoding="utf-8")

    # ---- writes (adapters call these from their reader threads) ----

    def add(self, kind: str, text: str, detail: str | None = None) -> None:
        with self._changed:
            self.seq += 1
            self.last_activity = time.time()
            event = {"seq": self.seq, "ts": self.last_activity, "kind": kind, "text": text[:4000]}
            if detail:
                event["detail"] = detail[:4000]
            self.events.append(event)
            del self.events[:-MAX_EVENTS]
            if not self._log.closed:  # a closed run may still hear from its exiting process
                self._log.write(json.dumps(event) + "\n")
                self._log.flush()
            self._changed.notify_all()

    def set(self, **fields) -> None:
        with self._changed:
            for key, value in fields.items():
                setattr(self, key, value)
            if fields.get("status") in ("idle", "done", "error", "interrupted"):
                self.ended_at = time.time()
                self._expire_pending("the turn ended")
            elif fields.get("status") in LIVE:
                self.ended_at = None
            self.last_activity = time.time() if "activity" in fields or "partial" in fields else self.last_activity
            self._changed.notify_all()
        status = fields.get("status")
        if status:
            from .board import board_for
            from .claims import BOARD
            if status in ("done", "error"):
                BOARD.ended(self)
            else:
                board_for(self.cwd).heartbeat(self.id, "working" if status in LIVE else "idle")

    def set_usage(self, **fields) -> None:
        with self._changed:
            self.usage.update({k: v for k, v in fields.items() if v is not None})
            self._changed.notify_all()

    def add_usage(self, **deltas) -> None:
        """Live counting for agents that report usage per model call."""
        with self._changed:
            for key, value in deltas.items():
                if value:
                    self.usage[key] = (self.usage.get(key) or 0) + value
            self._changed.notify_all()

    def touch(self, paths: list[str]) -> None:
        """Record files this run changed; the board reports overlaps with other live runs."""
        from .claims import BOARD
        fresh = []
        with self._lock:
            for path in paths:
                full = os.path.normpath(os.path.join(self.cwd, path))
                if full not in self.touched:
                    self.touched.append(full)
                    fresh.append(full)
        for full in fresh:
            BOARD.touched(self, full)

    # ---- the Needs-you inbox ----

    def request_approval(self, kind: str, title: str, detail: str, answer: Answer,
                         paths: list[str] | None = None) -> None:
        """An agent wants permission. Auto runs are answered at once; ask runs wait for a person.
        No answer within APPROVAL_TIMEOUT_S is a deny."""
        from .claims import BOARD
        warning = BOARD.conflict_note(self, paths or [])
        if self.autonomy == "auto" and not warning:
            self.add("approval", f"auto-allowed: {title}", detail)
            answer("allow")
            return
        aid = uuid.uuid4().hex[:10]
        item = {"id": aid, "run_id": self.id, "engine": self.engine, "kind": kind, "title": title[:300],
                "detail": (detail or "")[:4000], "warning": warning, "asked_at": time.time()}
        with self._changed:
            self.pending[aid] = item
            self._answers[aid] = answer
            self._changed.notify_all()
        self.add("needs-you", title, (warning + "\n" if warning else "") + (detail or ""))
        # the auto-deny clock: daemon so it never holds the bridge open, cancelled when someone decides
        timer = threading.Timer(APPROVAL_TIMEOUT_S, lambda: self.decide(aid, "deny", why="no answer in time"))
        timer.daemon = True
        self._timers[aid] = timer
        timer.start()

    def decide(self, aid: str, choice: str, why: str = "", by: str = "") -> bool:
        with self._changed:
            item = self.pending.pop(aid, None)
            answer = self._answers.pop(aid, None)
            timer = self._timers.pop(aid, None)
            self._changed.notify_all()
        if timer is not None:
            timer.cancel()
        if not item or not answer:
            return False
        verb = {"allow": "allowed", "allow_session": "allowed for this session"}.get(choice, "denied")
        who = {"claude": "decided by the user in Claude chat", "panel": "decided by the user in the panel"}.get(by, "")
        self.add("approval", f"{verb}: {item['title']}", "; ".join(x for x in (who, why) if x) or None)
        try:
            answer(choice if choice in ("allow", "allow_session") else "deny")
        except Exception as exc:  # the agent may have moved on; show it, do not crash
            self.add("warning", f"could not deliver the decision: {exc}")
        return True

    def send_refusal(self) -> str:
        """Why a message must not go to this run now, or "". A message is never an approval: sending one
        while the agent waits on a decision would start a new turn over it (seen with Antigravity)."""
        with self._lock:
            waiting = list(self.pending.values())
        if not waiting:
            return ""
        return (f"Answer the approval above first ({waiting[0]['title']}): Allow, Allow for this run or Deny. "
                "A message is not an approval, and sending one now could cancel the waiting action.")

    def _expire_pending(self, why: str) -> None:
        for aid in list(self.pending):
            self.pending.pop(aid, None)
            self._answers.pop(aid, None)
            timer = self._timers.pop(aid, None)
            if timer is not None:
                timer.cancel()

    # ---- reads ----

    def wait(self, timeout: float, through_approvals: bool = False) -> bool:
        """Block until the run leaves a live status or needs a person; True if it did.
        through_approvals: keep waiting while the person decides, until the turn itself ends."""
        import time as _t
        deadline = _t.time() + timeout
        with self._changed:
            while self.status in LIVE and (through_approvals or not self.pending):
                left = deadline - _t.time()
                if left <= 0:
                    return False
                self._changed.wait(left)
        return True

    def summary(self) -> dict:
        with self._lock:
            now = time.time()
            end = self.ended_at or now
            quiet = round(now - self.last_activity) if self.status in LIVE else 0
            return {
                "id": self.id, "engine": self.engine, "name": self.spec.get("name", self.engine),
                "color": self.spec.get("color"), "steer": self.spec.get("steer", "queue"),
                "model": self.model, "label": self.label, "cwd": self.cwd,
                "status": self.status, "activity": self.activity, "autonomy": self.autonomy,
                "started_at": self.started_at, "elapsed_s": round(end - self.started_at, 1),
                "quiet_s": quiet, "stuck": quiet >= STUCK_AFTER_S,
                "usage": dict(self.usage), "events": self.seq, "error": self.error,
                "session_id": self.session_id, "pending": list(self.pending.values()),
                "owner": self.owner, "blocked": self.blocked, "queued": self.queued,
                "waiting_on_user": bool(self.pending),
                "touched": self.touched[-50:], "owns": self.owns, "approval_note": self.approval_note, "coordination": self.coordination,
            }

    def detail(self, after: int) -> dict:
        data = self.summary()
        with self._lock:
            data["prompt"] = self.prompt
            data["final_text"] = self.final_text
            data["partial"] = self.partial[-2000:]
            data["new_events"] = [e for e in self.events if e["seq"] > after]
        return data

    def recap(self, limit: int = 4000) -> str:
        """The conversation so far (what was asked, what the agent said), newest kept when long."""
        with self._lock:
            lines = [f"{'User' if e['kind'] == 'you' else 'You'}: {e['text'][:600]}"
                     for e in self.events if e["kind"] in ("you", "message")]
        text = "\n".join(lines)
        return text if len(text) <= limit else "…" + text[-limit:]

    def close_log(self) -> None:
        if not self._log.closed:
            self._log.close()
