"""Codex through `codex app-server`: JSON-RPC threads and turns, steerable mid-turn."""

from __future__ import annotations

import os

from . import __version__

from .coordination import agent_env, brief, mcp_server
from .registry import argv
from .run import Run
from .stdio_rpc import StdioRpc


from .detail import LIMIT, args_detail, clip


def _short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _tool_output(item: dict) -> str:
    """A tool call's result as text: MCP `result.content` blocks, a dynamic tool's `contentItems`, or an error message."""
    err = item.get("error")
    if err:
        return clip(err.get("message") if isinstance(err, dict) else err)
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    blocks = result.get("content") or item.get("contentItems") or []
    texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("text")]
    if texts:
        return clip("\n".join(texts))
    structured = result.get("structuredContent")
    return clip(structured) if structured else ""


class CodexAdapter:
    def __init__(self, run: Run):
        self.run = run
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.item_paths: dict[str, list[str]] = {}  # fileChange item id -> files it will change (v2 approvals carry no paths)
        self.rpc = StdioRpc(
            argv(run.spec, None), run.cwd,
            on_notify=self._notify, on_request=self._request,
            on_exit=self._exited, on_stderr=lambda line: None, env=agent_env(run),
        )

    # ---- control ----

    def start(self) -> None:
        run = self.run
        self.rpc.call("initialize", {"clientInfo": {"name": "modstage", "version": __version__},
                                     "capabilities": None})
        self.rpc.notify("initialized")
        # ask runs: Codex asks before anything outside its sandbox, and those asks go to the Needs-you inbox.
        # auto runs: "untrusted" makes Codex send every file change (and every command) through the bridge, which
        # answers at once but runs the board's write fence first; "never" would let edits bypass it. Checked against
        # codex 0.156 on 17 Oct 2026: an in-workspace apply_patch sends item/fileChange/requestApproval.
        params = {"cwd": run.cwd, "approvalPolicy": "untrusted" if run.autonomy == "auto" else "on-request",
                  "sandbox": "workspace-write", "developerInstructions": brief(run),
                  # our board tools only touch the coordination board, so they never need a prompt
                  "config": {"mcp_servers": {"modstage": {**mcp_server(run), "default_tools_approval_mode": "approve"}}}}
        if run.model:
            params["model"] = run.model
        started = self.rpc.call("thread/start", params)
        self.thread_id = started["thread"]["id"]
        run.set(model=started.get("model") or run.model, session_id=self.thread_id)
        self._start_turn(run.prompt, run.start_images)

    def send(self, text: str, images: list[dict] | None = None) -> str:
        self.run.add("you", text + (f"  [+{len(images)} image(s)]" if images else ""))
        if self.turn_id and self.run.status == "running":
            self.rpc.call("turn/steer", {"threadId": self.thread_id, "expectedTurnId": self.turn_id,
                                         "input": _inputs(text, images)})
            return "steered the running turn"
        self._start_turn(text, images)
        return "started a new turn"

    def interrupt(self) -> str:
        if not self.turn_id or self.run.status != "running":
            return "nothing running"
        self.rpc.call("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id})
        return "interrupt sent"

    def close(self) -> None:
        self.rpc.close()

    def _start_turn(self, text: str, images: list[dict] | None = None) -> None:
        self.run.set(status="running", activity="thinking", partial="")
        reply = self.rpc.call("turn/start", {"threadId": self.thread_id, "input": _inputs(text, images)})
        self.turn_id = reply.get("turn", {}).get("id", self.turn_id)

    # ---- what Codex reports ----

    def _notify(self, msg: dict) -> None:
        method, p = msg["method"], msg.get("params") or {}
        run = self.run
        if method == "turn/started":
            self.turn_id = p.get("turn", {}).get("id", self.turn_id)
        elif method == "item/started":
            self._item(p.get("item") or {}, done=False)
        elif method == "item/completed":
            self._item(p.get("item") or {}, done=True)
        elif method == "item/agentMessage/delta":
            run.set(partial=run.partial + p.get("delta", ""), activity="writing")
        elif method == "thread/tokenUsage/updated":
            usage = p.get("tokenUsage") or {}
            total, last = usage.get("total") or {}, usage.get("last") or {}
            run.set_usage(input=total.get("inputTokens"), cached=total.get("cachedInputTokens"),
                          output=total.get("outputTokens"), reasoning=total.get("reasoningOutputTokens"),
                          context_used=(last.get("inputTokens") or 0) + (last.get("outputTokens") or 0),
                          context_window=usage.get("modelContextWindow"))
        elif method == "turn/completed":
            turn = p.get("turn") or {}
            status = turn.get("status")
            if status == "failed":
                error = (turn.get("error") or {}).get("message", "turn failed")
                run.add("error", error)
                run.set(status="error", error=error, activity="failed")
            elif status == "interrupted":
                run.add("status", "interrupted")
                run.set(status="interrupted", activity="interrupted")
            else:
                run.add("status", "turn finished, waiting for Claude")
                run.set(status="idle", activity="idle")
        elif method == "error":
            run.add("error", _short(p.get("error") or p, 600))
        elif method in ("warning", "configWarning"):
            run.add("warning", _short(p.get("message") or p))

    def _item(self, item: dict, done: bool) -> None:
        run, kind = self.run, item.get("type")
        if kind == "commandExecution":
            command = item.get("command", "")
            if not done:
                run.add("tool", f"$ {command}")
                run.set(activity=f"running: {_short(command, 60)}")
            else:
                output = item.get("aggregatedOutput") or ""
                run.add("result", f"exit {item.get('exitCode')}", clip(output) if output.strip() else None)
                run.set(activity="thinking")  # the command is over: do not keep showing it
        elif kind == "fileChange" and not done:
            self.item_paths[item.get("id", "")] = [c.get("path") for c in item.get("changes") or [] if c.get("path")]
        elif kind == "fileChange" and done:
            self.item_paths.pop(item.get("id", ""), None)
            changed = [c.get("path") for c in item.get("changes") or [] if c.get("path")]
            # each change carries its own diff; show them all, a change without one at least says what kind it was
            diffs = "\n".join(str(c.get("diff") or f"{c.get('path')}: {c.get('kind') or 'changed'}")
                              for c in item.get("changes") or [] if c.get("path"))
            run.add("edit", f"edited {', '.join(changed) or '?'}", clip(diffs) if diffs.strip() else None)
            run.touch(changed)
        elif kind == "mcpToolCall":
            name = f"{item.get('server')}.{item.get('tool')}"
            if not done:
                run.add("tool", f"mcp {name}", args_detail(item.get("arguments")) or None)
                run.set(activity=f"mcp {name}")
            else:
                run.add("result", f"mcp {name} {item.get('status')}", _tool_output(item) or None)
        elif kind == "dynamicToolCall" and not done:
            run.add("tool", f"tool {item.get('tool')}", args_detail(item.get("arguments")) or None)
        elif kind == "dynamicToolCall" and done:
            run.add("result", f"tool {item.get('tool')} {'ok' if item.get('success') is not False else 'failed'}",
                    _tool_output(item) or None)
        elif kind == "webSearch" and not done:
            run.add("tool", "web search", _short(item.get("query", ""), 200))
        elif kind == "reasoning" and not done:
            run.set(activity="thinking")
        elif kind == "reasoning" and done:
            summary = " ".join(item.get("summary") or [])
            if summary.strip():
                run.add("thinking", _short(summary, 3000))
            run.set(activity="thinking")
        elif kind == "plan" and done:
            run.add("plan", _short(item.get("text", ""), 3000))
        elif kind == "agentMessage" and done:
            text = item.get("text", "")
            run.add("message", text)
            run.set(final_text=text, partial="")
        elif kind == "subAgentActivity" and not done:
            run.add("subagent", f"{item.get('kind')} {item.get('agentPath')}")
        elif kind == "contextCompaction" and done:
            run.add("status", "context compacted")

    def _request(self, msg: dict) -> None:
        method, p = msg["method"], msg.get("params") or {}
        rid = msg["id"]
        if method in ("item/commandExecution/requestApproval", "execCommandApproval"):
            cmd = p.get("command")
            command = " ".join(cmd) if isinstance(cmd, list) else (cmd or "a command")
            title = f"run `{_short(command, 160)}`"
            # the full command always: a harmless-looking start must not hide a long tail
            reason = p.get("reason") or (f"in {p.get('cwd')}" if p.get("cwd") else "")
            detail = f"command: {command}" + (f"\nwhy: {reason}" if reason else "")
            paths: list[str] = []
        elif method in ("item/fileChange/requestApproval", "applyPatchApproval"):
            paths = list((p.get("fileChanges") or {}).keys()) or list(self.item_paths.get(p.get("itemId", ""), []))
            title = f"change {', '.join(paths[:3]) or 'files'}" + (f" (+{len(paths) - 3} more)" if len(paths) > 3 else "")
            detail = p.get("reason") or (f"write access under {p['grantRoot']}" if p.get("grantRoot") else "")
        else:
            self.run.add("warning", f"Codex asked {method}; declined (not supported yet)")
            self.rpc.answer(rid, error="modstage does not serve this request")
            return
        legacy = method in ("execCommandApproval", "applyPatchApproval")
        fenced = [x for x in paths if self._inside(x)]

        def answer(choice: str) -> None:
            if choice != "deny" and fenced:
                # the fence at the write: re-checked now, whatever was allowed before and however long a person took
                for path in fenced:
                    ok, _ = self.run.guard_write(path)
                    if not ok:
                        choice = "deny"
                        break
                else:
                    choice = "allow"  # never "for session": the next edit must pass the fence again
            if legacy:
                decision = {"allow": "approved", "allow_session": "approved_for_session"}.get(choice, "denied")
            else:
                decision = {"allow": "accept", "allow_session": "acceptForSession"}.get(choice, "decline")
            self.rpc.answer(rid, {"decision": decision})

        self.run.request_approval("command" if not paths else "edit", title, detail, answer, paths)

    def _inside(self, path: str) -> bool:
        """Only files in the run's folder are on its board; others (a temp file) are not fenced."""
        root = os.path.realpath(self.run.cwd)
        full = os.path.realpath(os.path.join(self.run.cwd, path))
        return full == root or full.startswith(root + os.sep)

    def _exited(self, code: int) -> None:
        if self.run.adapter is not self:  # replaced by a restart or closed: not this run's news
            return
        if self.run.status in ("starting", "running"):
            self.run.add("error", f"codex app-server exited with code {code}")
            self.run.set(status="error", error=f"exited {code}", activity="exited")
        elif self.run.status == "idle":
            self.run.set(status="done", activity="closed")


def _text(text: str) -> dict:
    return {"type": "text", "text": text, "text_elements": []}


def _inputs(text: str, images: list[dict] | None) -> list[dict]:
    """Text plus local images, as app-server's LocalImageUserInput {type: localImage, path}."""
    return [_text(text)] + [{"type": "localImage", "path": i["path"]} for i in images or []]
