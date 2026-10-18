"""Protocol-level fakes for the conformance harness: every adapter runs against a scripted
transport instead of a real CLI, so the harness costs no tokens and runs in CI.

FakeRpc stands in for StdioRpc (Codex, Muse, every ACP agent); FakeProc stands in for the
stream-json child process (Antigravity). Both record what the adapter sent, so a test can assert
the exact protocol message (a steer call, a cancel notify, an approval answer).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("MODSTAGE_HOME", tempfile.mkdtemp())
os.environ.setdefault("MODSTAGE_AGY_PROJECTS", tempfile.mkdtemp())  # never the real ~/.gemini
os.environ["MODSTAGE_SLM_MESH"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modstage import acp, codex, muse, registry, stream_json  # noqa: E402
from modstage.run import RUNS, Run  # noqa: E402

AGENTS = ["claude", "codex", "muse", "grok", "antigravity", "kimi", "qwen", "opencode"]
BRIDGE_AGENTS = AGENTS[1:]


class FakeProc:
    """A child process that is alive until terminated or told to exit."""

    def __init__(self, stdout_lines: list[str] | None = None):
        self.code: int | None = None
        self.written: list[str] = []
        self.stdin = mock.Mock(write=self.written.append, flush=lambda: None)
        self.stdout = iter(stdout_lines or [])
        self.stderr = iter([])

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return self.code if self.code is not None else 0

    def terminate(self):
        self.code = -15

    kill = terminate

    def lines(self) -> list[dict]:
        return [json.loads(line) for line in "".join(self.written).splitlines() if line.strip()]


class FakeRpc:
    """Records calls, notifies and answers; replies to calls from a per-method script."""

    replies: dict = {}
    image = True

    def __init__(self, argv, cwd, on_notify, on_request, on_exit, on_stderr, jsonrpc=False, env=None):
        self.argv, self.cwd = list(argv), cwd
        self.on_notify, self.on_request, self.on_exit = on_notify, on_request, on_exit
        self.proc = FakeProc()
        self.calls: list[tuple[str, dict]] = []
        self.notes: list[tuple[str, dict | None]] = []
        self.answers: list[tuple[object, object, object]] = []

    def call(self, method, params, timeout=120):
        self.calls.append((method, params))
        reply = self.replies.get(method, {})
        return reply(params) if callable(reply) else reply

    def notify(self, method, params=None):
        self.notes.append((method, params))

    def answer(self, rid, result=None, error=None):
        self.answers.append((rid, result, error))

    def close(self):
        self.proc.terminate()

    def methods(self) -> list[str]:
        return [m for m, _ in self.calls]


REPLIES = {
    "thread/start": {"thread": {"id": "th1"}, "model": "gpt-test"},
    "turn/start": lambda p: {"turn": {"id": "tu1"}} if "threadId" in p else {"turnId": "tu1"},
    "session/start": {"session": {"sessionId": "ms1", "modelId": "muse-test"}},
    "session/new": {"sessionId": "acp1", "configOptions": [{"id": "model", "category": "model", "type": "select",
                                                            "currentValue": "default-m"}]},
    # what each ACP agent's own initialize said on 16 Oct 2026 (grok: image false; kimi, qwen, opencode: true)
    "initialize": lambda p: {"agentCapabilities": {"promptCapabilities": {"image": FakeRpc.image}}},
    # an ACP prompt call returns when its turn ends; Harness holds it until end_turn()
    "session/prompt": {"stopReason": "end_turn"},
}


def spec(agent: str) -> dict:
    return dict(registry.load()[agent])


def make_run(agent: str, prompt: str = "say hi", model: str | None = None, autonomy: str = "ask") -> Run:
    cwd = tempfile.mkdtemp()
    run = Run(spec(agent), prompt, cwd, model, None, autonomy)
    RUNS[run.id] = run
    return run


class Harness:
    """One agent's adapter wired to fakes. `started()` runs start(); `rpc`/`proc` hold what was sent."""

    def __init__(self, agent: str, model: str | None = None, autonomy: str = "ask"):
        self.agent = agent
        self.run = make_run(agent, model=model, autonomy=autonomy)
        self.protocol = self.run.spec["protocol"]
        self._patches = []
        self.held: list = []
        FakeRpc.replies = REPLIES
        FakeRpc.image = agent != "grok"
        if self.protocol == "stream-json":
            self.proc = FakeProc()
            self._patch(stream_json.subprocess, "Popen", lambda cmd, **kw: self._popen(cmd))
            self._patch(stream_json, "threading", _threads(lambda target: None))
            self.adapter = stream_json.StreamJsonAdapter(self.run)
            self.rpc = None
        else:
            module = {"codex-app-server": codex, "muse-msp": muse, "acp": acp}[self.protocol]
            self._patch(module, "StdioRpc", FakeRpc)
            if self.protocol == "acp":
                # each prompt runs on a thread that returns when its turn ends; hold them, end_turn() runs one
                self._patch(acp, "threading", _threads(self.held.append))
            cls = {"codex-app-server": codex.CodexAdapter, "muse-msp": muse.MuseAdapter, "acp": acp.AcpAdapter}[self.protocol]
            self.adapter = cls(self.run)
            self.rpc = self.adapter.rpc
            self.proc = self.rpc.proc
        self.run.adapter = self.adapter

    def _popen(self, cmd):
        self.argv = list(cmd)
        return self.proc

    def _patch(self, target, name, value):
        p = mock.patch.object(target, name, value)
        p.start()
        self._patches.append(p)

    def started(self) -> "Harness":
        self.adapter.start()
        return self

    def stop(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        RUNS.pop(self.run.id, None)

    def argv_used(self) -> list[str]:
        return self.argv if self.protocol == "stream-json" else self.rpc.argv

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.run.events]

    # ---- drive the fake agent: the protocol-native shape of each kind of report ----

    def say(self, text: str) -> None:
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "item/agentMessage/delta", "params": {"delta": text}})
            self.adapter._notify({"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": text}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "item/delta", "params": {"delta": text}})
            self.adapter._notify({"method": "item/completed", "params": {"item": {"kind": "agentMessage", "text": text}}})
        elif self.protocol == "acp":
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}}})
        else:
            self.adapter._event({"event": "step_update", "step_update": {
                "step_type": "agent_response", "state": "ACTIVE", "text_delta": text}})

    def think(self, text: str) -> None:
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "item/completed", "params": {"item": {"type": "reasoning", "summary": [text]}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "item/completed", "params": {"item": {"kind": "reasoning", "text": text}}})
        elif self.protocol == "acp":
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": text}}}})
            self.adapter._flush_thought()
        else:
            # agy's stream carries no thinking text; a step with thinking tokens is all it reports
            self.adapter._event({"event": "step_update", "step_update": {
                "step_type": "agent_response", "state": "DONE", "usage": {"thinking_tokens": 40}}})

    def tool(self, command: str) -> None:
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "item/started", "params": {"item": {"type": "commandExecution", "command": command}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "item/started", "params": {"item": {"kind": "toolCall", "tool": "bash",
                                                                                 "args": {"command": command}}}})
        elif self.protocol == "acp":
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call", "toolCallId": "t1", "title": "bash", "rawInput": {"command": command}}}})
        else:
            self.adapter._event({"event": "step_update", "step_update": {
                "step_type": "tool", "state": "ACTIVE", "tool_info": {"name": "run_command",
                                                                      "parameters": {"CommandLine": command}}}})

    def tool_result(self, command: str, output: str) -> None:
        """The tool started by tool(command) finishes with this output."""
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "item/completed", "params": {"item": {
                "type": "commandExecution", "command": command, "exitCode": 0, "aggregatedOutput": output}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "item/completed", "params": {"item": {
                "kind": "toolCall", "tool": "bash", "toolStatus": "ok", "args": {"command": command}, "output": output}}})
        elif self.protocol == "acp":
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "t1", "status": "completed",
                "content": [{"type": "content", "content": {"type": "text", "text": output}}]}}})
        else:
            self.adapter._event({"event": "step_update", "step_update": {
                "step_type": "tool", "state": "DONE", "tool_info": {"name": "run_command", "output": output,
                                                                    "parameters": {"CommandLine": command}}}})

    def edit(self, path: str, old: str, new: str) -> None:
        """The agent changes one file, reported the way its protocol reports edits."""
        from modstage.detail import unified
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "item/completed", "params": {"item": {"type": "fileChange", "id": "f1", "changes": [
                {"path": path, "kind": "update", "diff": unified(path, old, new)}]}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "item/completed", "params": {"item": {
                "kind": "toolCall", "tool": "str_replace", "toolStatus": "ok",
                "args": {"path": path, "old_str": old, "new_str": new}}}})
        elif self.protocol == "acp":
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call", "toolCallId": "e1", "title": f"Edit {path}", "kind": "edit", "rawInput": {"path": path}}}})
            self.adapter._notify({"method": "session/update", "params": {"update": {
                "sessionUpdate": "tool_call_update", "toolCallId": "e1", "status": "completed", "kind": "edit",
                "locations": [{"path": path}], "content": [{"type": "diff", "path": path, "oldText": old, "newText": new}]}}})
        else:
            info = {"name": "replace_file_content", "parameters": {"TargetFile": path, "TargetContent": old, "ReplacementContent": new}}
            self.adapter._event({"event": "step_update", "step_update": {"step_type": "tool", "state": "ACTIVE", "tool_info": info}})
            self.adapter._event({"event": "step_update", "step_update": {"step_type": "tool", "state": "DONE", "tool_info": info}})

    def ask(self, command: str = "pip install x") -> None:
        """The agent asks permission to run a command, in its own protocol."""
        if self.protocol == "codex-app-server":
            self.adapter._request({"id": 77, "method": "item/commandExecution/requestApproval",
                                   "params": {"command": command, "reason": "network"}})
        elif self.protocol == "muse-msp":
            self.adapter._request({"id": 77, "method": "approval/request", "params": {
                "approvalId": "ap1", "currentRequirementId": "rq1", "toolName": "bash",
                "subject": {"kind": "command", "command": command},
                "availableChoices": [{"choiceId": "c-ok", "decision": "approved"},
                                     {"choiceId": "c-sess", "decision": "approvedForSession"},
                                     {"choiceId": "c-no", "decision": "denied"}]}})
        elif self.protocol == "acp":
            self.adapter._request({"id": 77, "method": "session/request_permission", "params": {
                "toolCall": {"title": "bash", "kind": "execute", "rawInput": {"command": command}},
                "options": [{"optionId": "o-once", "kind": "allow_once"}, {"optionId": "o-always", "kind": "allow_always"},
                            {"optionId": "o-no", "kind": "reject_once"}]}})
        else:
            # agy in headless stream-json mode cannot prompt: it auto-denies, ends the turn and lists
            # what it refused in the result (probe on agy 1.4.0, 16 Oct 2026, see docs/PARITY-MATRIX.md)
            self.tool(command)
            self.adapter._event({"event": "step_update", "step_update": {
                "step_type": "tool", "state": "DONE", "tool_info": {"name": "run_command",
                                                                    "parameters": {"CommandLine": command}}}})
            self.adapter._event({"event": "result", "result": {"status": "SUCCESS", "response": "",
                                 "denied_actions": [{"action": "command", "display_name": "RunCommand"}]}})

    def answered(self) -> object:
        """What the adapter sent back to the agent for its approval request, or None."""
        if self.protocol in ("codex-app-server", "acp"):
            return self.rpc.answers[-1][1] if self.rpc.answers else None
        if self.protocol == "muse-msp":
            decided = [p for m, p in self.rpc.calls if m == "approval/decide"]
            return decided[-1] if decided else None
        return None

    def end_turn(self) -> None:
        if self.protocol == "codex-app-server":
            self.adapter._notify({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
        elif self.protocol == "muse-msp":
            self.adapter._notify({"method": "turn/completed", "params": {"terminal": "completed"}})
        elif self.protocol == "acp":
            self.held.pop(0)()
        else:
            self.adapter._event({"event": "result", "result": {"status": "SUCCESS", "response": ""}})

    def exit(self, code: int = 0) -> None:
        self.proc.code = code



def _threads(on_start):
    """A stand-in for an adapter module's `threading`: Thread(target).start() calls on_start(target)
    instead of running it, and the real threading module (Timer, locks) stays untouched."""
    import threading as real
    return mock.Mock(Thread=lambda target, daemon=False: mock.Mock(start=lambda: on_start(target)),
                     Lock=real.Lock, RLock=real.RLock)
