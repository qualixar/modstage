"""Muse through `muse serve`: the Muse Session Protocol (JSON-RPC 2.0), steerable mid-turn."""

from __future__ import annotations

from . import __version__

import json
import os
import time
import uuid

from .coordination import agent_env, brief, mcp_server
from .images import b64
from .registry import argv
from .run import Run
from .stdio_rpc import StdioRpc

QUIET_KINDS = {"hookRun", "reminderChild", "userMessage"}


def _cid() -> str:
    """A UUIDv7 (time-ordered), which Muse requires; uuid.uuid7 exists only on Python 3.14+."""
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    ms = int(time.time() * 1000)
    raw = ms.to_bytes(6, "big") + os.urandom(10)
    raw = raw[:6] + bytes([0x70 | (raw[6] & 0x0F)]) + raw[7:8] + bytes([0x80 | (raw[8] & 0x3F)]) + raw[9:]
    return str(uuid.UUID(bytes=raw))


def _short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _args(raw) -> str:
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        return _short(raw, 160)
    if isinstance(data, dict):
        for key in ("command", "path", "file_path", "pattern", "query", "url"):
            if key in data:
                return _short(str(data[key]), 160)
    return _short(data, 160)


def _stage_tools(run: Run) -> list[str]:
    """The ModStage MCP server as a host setting. Muse 1.4.9 refuses mcpServers in session/start and
    takes one server per `-c mcpServers.<name>=<json>`; env values must be `${VAR}` references to
    variables already set, and agent_env puts them in Muse's own environment."""
    server = mcp_server(run)
    entry = {"mode": "optional", "command": server["command"], "args": server["args"],
             "env": {key: "${" + key + "}" for key in server["env"]}}
    return ["-c", "mcpServers.modstage=" + json.dumps(entry)]


class MuseAdapter:
    def __init__(self, run: Run):
        self.run = run
        self.session_id: str | None = None
        self.turn_id: str | None = None
        self.rpc = StdioRpc(argv(run.spec, run.model) + _stage_tools(run), run.cwd,
                            on_notify=self._notify, on_request=self._request,
                            on_exit=self._exited, on_stderr=lambda line: None, jsonrpc=True,
                            env=agent_env(run))

    # ---- control ----

    def start(self) -> None:
        run = self.run
        self.rpc.call("initialize", {"clientInfo": {"name": "modstage", "version": __version__}})
        self.rpc.notify("initialized")
        started = self.rpc.call("session/start", {"commandId": _cid(), "workspaceRoot": run.cwd,
                                                  "approvalMode": "allowAll" if run.autonomy == "auto" else "promptUnmatched"})
        session = started.get("session") or {}
        self.session_id = session.get("sessionId")
        run.set(session_id=self.session_id, model=session.get("modelId") or run.model)
        self._turn(f"{brief(run)}\n\nTask:\n{run.prompt}", if_busy=None, images=run.start_images)

    def send(self, text: str, images: list[dict] | None = None) -> str:
        self.run.add("you", text + (f"  [+{len(images)} image(s)]" if images else ""))
        if self.turn_id and self.run.status == "running":
            self.rpc.call("turn/steer", {"commandId": _cid(), "sessionId": self.session_id,
                                         "expectedTurnId": self.turn_id, "input": _inputs(text, images)})
            return "steered the running turn"
        self._turn(text, if_busy="steer", images=images)
        return "started a new turn"

    def interrupt(self) -> str:
        if self.run.status != "running":
            return "nothing running"
        params = {"commandId": _cid(), "sessionId": self.session_id}
        if self.turn_id:
            params["turnId"] = self.turn_id
        self.rpc.call("turn/interrupt", params)
        return "interrupt sent"

    def close(self) -> None:
        self.rpc.close()

    def _turn(self, text: str, if_busy: str | None, images: list[dict] | None = None) -> None:
        self.run.set(status="running", activity="thinking", partial="")
        params = {"commandId": _cid(), "sessionId": self.session_id, "input": _inputs(text, images)}
        if if_busy:
            params["ifBusy"] = if_busy
        reply = self.rpc.call("turn/start", params)
        self.turn_id = reply.get("turnId", self.turn_id)

    # ---- what Muse reports ----

    def _notify(self, msg: dict) -> None:
        method, p = msg["method"], msg.get("params") or {}
        run = self.run
        if method == "turn/started":
            self.turn_id = p.get("turnId", self.turn_id)
            run.set(status="running")
        elif method in ("item/started", "item/completed"):
            self._item(p.get("item") or {}, done=method == "item/completed")
        elif method == "item/delta" and p.get("field") in (None, "text"):
            run.set(partial=run.partial + str(p.get("delta", "")), activity="writing")
        elif method == "session/contextUsage":
            run.set_usage(context_used=p.get("usedTokens"), context_window=p.get("windowTokens"))
            if p.get("pressure") not in (None, "normal"):
                run.add("warning", f"context pressure: {p.get('pressure')}")
        elif method == "session/tokenUsage":
            cum = p.get("cumulative") or {}
            usage = p.get("usage") or {}
            run.set_usage(input=cum.get("promptTokens"), output=cum.get("outputTokens"),
                          cached=cum.get("cacheReadTokens"),
                          reasoning=(run.usage.get("reasoning") or 0) + (usage.get("reasoningTokens") or 0),
                          cost_usd=(cum.get("cost") or {}).get("usd"))
            if p.get("modelId"):
                run.set(model=p["modelId"])
        elif method == "turn/completed":
            terminal = p.get("terminal")
            if terminal == "failed":
                error = (p.get("error") or {}).get("message", "turn failed")
                run.add("error", error)
                run.set(status="error", error=error, activity="failed")
            elif terminal == "cancelled":
                run.add("status", "interrupted")
                run.set(status="interrupted", activity="interrupted")
            else:
                run.add("status", "turn finished, waiting for Claude")
                run.set(status="idle", activity="idle")

    def _item(self, item: dict, done: bool) -> None:
        run, kind = self.run, item.get("kind")
        if kind in QUIET_KINDS:
            return
        if kind == "toolCall":
            tool = item.get("tool", "tool")
            if not done:
                run.add("tool", f"{tool} {_args(item.get('args'))}")
                run.set(activity=f"{tool}: {_args(item.get('args'))[:60]}")
            else:
                out = item.get("output") or item.get("result") or item.get("outputPreview") or ""
                status = item.get("toolStatus") or item.get("status")
                run.add("result", f"{tool} {status}", _short(out, 1500) if out else None)
                run.set(activity="thinking")  # the tool is over: do not keep showing it
                if tool in ("write_file", "edit_file", "apply_patch", "str_replace"):
                    run.add("edit", f"edited {_args(item.get('args'))}")
                    run.touch([_args(item.get("args"))])
        elif kind == "agentMessage" and done:
            text = item.get("text", "")
            run.add("message", text)
            run.set(final_text=text, partial="")  # the last message of the turn is its answer
        elif kind == "reasoning":
            text = item.get("text") or item.get("summary") or ""
            if done and text:
                run.add("thinking", _short(text, 1200))
            run.set(activity="thinking")
        elif kind and done and kind not in ("agentMessage",):
            label = item.get("label") or item.get("fallbackText") or kind
            run.add("status", _short(f"{kind}: {label}", 200))

    def _request(self, msg: dict) -> None:
        method, p = msg["method"], msg.get("params") or {}
        if method != "approval/request":
            self.run.add("warning", f"Muse asked {method}; declined (not supported yet)")
            self.rpc.answer(msg["id"], error="modstage does not serve this request")
            return
        self.rpc.answer(msg["id"], {})  # acknowledge; the decision goes back through approval/decide
        choices = p.get("availableChoices") or []
        pick = lambda *decisions: next((c["choiceId"] for c in choices if c.get("decision") in decisions), None)
        subject = p.get("subject") or {}
        what = subject.get("command") or subject.get("path") or subject.get("target") or _args(p.get("rawArgs"))
        title = f"{p.get('toolName', 'tool')} {_short(str(what), 160)}"
        paths = [subject["path"]] if subject.get("path") else []

        def answer(choice: str) -> None:
            choice_id = {"allow": pick("approved"), "allow_session": pick("approvedForSession", "approved")} \
                .get(choice) or pick("denied", "abort")
            if choice_id:
                self.rpc.call("approval/decide", {"commandId": _cid(), "sessionId": self.session_id,
                                                  "approvalId": p["approvalId"], "choiceId": choice_id,
                                                  "requirementId": p["currentRequirementId"]})

        self.run.request_approval(subject.get("kind") or "tool", title, f"{p.get('toolName', 'tool')}: {what}", answer, paths)

    def _exited(self, code: int) -> None:
        if self.run.adapter is not self:  # replaced by a restart or closed: not this run's news
            return
        if self.run.status in ("starting", "running"):
            self.run.add("error", f"muse serve exited with code {code}")
            self.run.set(status="error", error=f"exited {code}", activity="exited")
        elif self.run.status == "idle":
            self.run.set(status="done", activity="closed")


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _inputs(text: str, images: list[dict] | None) -> list[dict]:
    """Text plus images as MSP TurnInputPart {type: image, base64Data, mediaType} (muse schema, 1.4.x)."""
    return [_text(text)] + [{"type": "image", "base64Data": b64(i), "mediaType": i["media_type"]} for i in images or []]
