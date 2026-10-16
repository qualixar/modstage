"""Agents with a stream-json print mode (Antigravity's `agy`): one long-lived process,
one NDJSON user message per turn on stdin, step events on stdout.

agy: `agy --input-format stream-json --output-format stream-json --print=`
  in:  {"event":"user","message":{"role":"user","content":"..."}}
  out: {"event":"init"} · {"event":"step_update","step_update":{step_type, state, tool_info, text_delta, usage}}
       · {"event":"result","result":{status, response, usage}} at the end of each turn.
No mid-turn steer (messages queue); interrupt ends the process.
Approvals: headless agy cannot prompt. Without its skip-permissions flag ("ask" runs) it refuses any
action that needs permission, ends the turn and lists the refusals in result.denied_actions; ModStage
shows each refusal and keeps the run marked blocked. "auto" runs pass the flag and allow everything.
(Probed on agy 1.4.0, 16 Oct 2026; there is no stream-json input that answers a permission.)
"""

from __future__ import annotations

import json
import os
import subprocess
import threading

from .coordination import agent_env, brief
from .images import NoImages
from .registry import argv
from .run import Run


def _short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "…"


NO_IMAGES = ("Antigravity's print mode takes text only: ModStage has no verified way to hand agy an image. "
             "Describe it in words, or use Codex, Muse, Kimi, Qwen Code or OpenCode for images.")


class StreamJsonAdapter:
    def __init__(self, run: Run):
        self.run = run
        self.message = ""
        self.turns_queued = 0
        self.closed = False
        self.last_tool = ""  # the command or path of the latest tool step, named in a refusal
        self.texts: list[str] = []  # turns sent and not yet finished; [0] is the running one
        self.restarts_to_interrupt = True
        cmd = argv(run.spec, run.model)
        if run.autonomy == "auto":
            cmd += list(run.spec.get("auto_args") or [])
        self.proc = subprocess.Popen(cmd, cwd=run.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1,
                                     env={**os.environ, "NO_COLOR": "1", **agent_env(run)})
        self._write = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_err, daemon=True).start()

    def start(self) -> None:
        if self.run.start_images:
            raise NoImages(NO_IMAGES)
        self._turn(f"{brief(self.run)}\n\nTask:\n{self.run.prompt}")

    def queued_texts(self) -> list[str]:
        return self.texts[1:]

    def send(self, text: str, images: list[dict] | None = None) -> str:
        if images:
            raise NoImages(NO_IMAGES)
        self.run.add("you", text)
        queued = self.run.status == "running"
        self._turn(text)
        return "queued: it runs when the current turn ends" if queued else "started a new turn"

    def interrupt(self) -> str:
        if self.run.status != "running":
            return "nothing running"
        self.close()
        self.run.add("status", "interrupted (this agent stops its process to interrupt)")
        self.run.set(status="interrupted", activity="interrupted")
        return "stopped"

    def close(self) -> None:
        self.closed = True
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _turn(self, text: str) -> None:
        if self.proc.poll() is not None:
            raise RuntimeError("the agent process has ended; start a new run")
        self.turns_queued += 1
        self.texts.append(text)
        self.run.set(status="running", activity="thinking", blocked="", queued=max(0, self.turns_queued - 1))
        line = json.dumps({"event": "user", "message": {"role": "user", "content": text}})
        with self._write:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()

    def _read(self) -> None:
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                self._event(msg)
            except Exception as exc:  # one odd event must not stop the stream
                self.run.add("warning", f"could not read an event: {exc}")
        code = self.proc.wait()
        if self.run.adapter is not self:  # replaced by a restart or closed: not this run's news
            return
        if self.run.status in ("starting", "running") and not self.closed:
            self.run.add("error", f"{self.run.engine} exited with code {code}")
            self.run.set(status="error", error=f"exited {code}", activity="exited")
        elif self.run.status == "idle":
            self.run.set(status="done", activity="closed")

    def _drain_err(self) -> None:
        for _ in self.proc.stderr:
            pass

    def _event(self, msg: dict) -> None:
        run, ev = self.run, msg.get("event")
        if ev == "init":
            init = msg.get("init") or {}
            run.set(session_id=msg.get("conversation_id"), model=init.get("model") or run.model)
        elif ev == "step_update":
            step = msg.get("step_update") or {}
            kind, state = step.get("step_type"), step.get("state")
            usage = step.get("usage") or {}
            if kind == "agent_response" and not step.get("text_delta"):
                # agy streams no thinking text; a response step is still proof the turn is alive
                run.set(activity="thinking" if state != "DONE" or usage.get("thinking_tokens") else run.activity)
            elif kind not in ("tool", "agent_response") and state == "ACTIVE":
                run.set(activity="working")
            if usage:
                run.add_usage(input=usage.get("input_tokens"), cached=usage.get("cache_read_tokens"),
                              output=usage.get("output_tokens"), reasoning=usage.get("thinking_tokens"))
                run.set_usage(context_used=(usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
            if kind == "agent_response":
                delta = step.get("text_delta") or ""
                if delta:
                    self.message += delta
                    run.set(partial=self.message, activity="writing")
            elif kind == "tool":
                info = step.get("tool_info") or {}
                params = info.get("parameters") or {}
                what = next((str(v) for k, v in params.items() if k.lower() in
                             ("commandline", "command", "path", "absolutepath", "targetfile", "query")), "")
                name = info.get("name") or step.get("tool_name") or "tool"
                if state == "ACTIVE":
                    self.last_tool = f"{name} {what}".strip()
                    if self.message.strip():
                        run.add("message", self.message.strip())
                        self.message = ""
                    run.add("tool", f"{name} {_short(what, 200)}".strip())
                    run.set(activity=f"{name}: {_short(what, 60)}")
                elif state == "DONE":
                    out = info.get("output") or ""
                    run.add("result", f"{name} done", _short(out, 1500) if out else None)
                    if any(w in name for w in ("write", "edit", "replace", "create")) and what:
                        run.add("edit", f"edited {what}")
                        run.touch([what])
        elif ev == "result":
            res = msg.get("result") or {}
            self.turns_queued = max(0, self.turns_queued - 1)
            if self.texts:
                self.texts.pop(0)
            run.set(queued=max(0, self.turns_queued - 1))
            text = (res.get("response") or self.message).strip()
            if text:
                run.add("message", text)
                run.set(final_text=text, partial="")
            self.message = ""
            refused = [f"{d.get('display_name') or d.get('action') or 'an action'}" for d in res.get("denied_actions") or []]
            if refused:
                what = self.last_tool or ", ".join(refused)
                run.add("denied", f"Antigravity refused: {what}",
                        "Headless agy cannot ask you for permission, so it refused this itself. To allow it, "
                        "start the run in auto mode, or add an allow rule to agy's settings.json (permissions.allow).")
            if res.get("status") == "ERROR":
                err = res.get("error") or "the turn failed"
                run.add("error", err)
                run.set(status="error", error=err, activity="failed")
            elif self.turns_queued == 0 and refused:
                blocked = f"refused {what} (agy cannot ask for permission)"
                run.add("status", f"turn ended blocked: {blocked}")
                run.set(status="idle", activity=f"blocked: {blocked}"[:120], blocked=blocked)
            elif self.turns_queued == 0:
                run.add("status", "turn finished, waiting for Claude")
                run.set(status="idle", activity="idle")
