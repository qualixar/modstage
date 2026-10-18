"""Any agent that speaks the Agent Client Protocol (ACP) over stdio: Grok, Kimi, Qwen Code,
OpenCode, Gemini CLI, Cursor, Copilot and the rest of the ACP registry.

ACP has no mid-turn steer: a prompt sent while a turn runs is queued and runs when the turn ends.
To redirect at once, interrupt (session/cancel), then send.
Permission requests go to the Needs-you inbox; auto runs answer them at once.
"""

from __future__ import annotations

from . import __version__

import json
import os
import threading

from .coordination import agent_env, brief, mcp_server
from .images import NoImages, b64
from .registry import argv
from .run import Run
from .stdio_rpc import StdioRpc

TICKS_PER_USD = 1e10  # Grok reports cost in ticks
EDIT_KINDS = {"edit", "delete", "move"}


from .detail import args_detail, clip, diff_blocks


def _short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _content_text(content) -> str:
    parts = []
    for block in content or []:
        inner = block.get("content") if isinstance(block, dict) else None
        if isinstance(inner, dict) and inner.get("type") == "text":
            parts.append(inner.get("text", ""))
    return "".join(parts)


def _what(raw: dict) -> str:
    for key in ("command", "cmd", "path", "file_path", "filePath", "query", "pattern", "url"):
        if raw.get(key):
            return str(raw[key])
    return _short(raw, 160)


class AcpAdapter:
    def __init__(self, run: Run):
        self.run = run
        self.session_id: str | None = None
        self.message = ""
        self.thought = ""
        self.tools: dict[str, str] = {}
        self.diffs: dict[str, str] = {}  # a tool call's diff, when the agent sent it before the result
        self.in_flight = False  # a session/prompt is running
        self.held: list[tuple[str, list[dict] | None]] = []  # messages sent mid-turn, sent when it ends
        self.can_image = False
        self.cancelling = False  # a session/cancel was sent and its turn has not come back yet
        self.turn_said = False  # anything (text, thinking, a tool) reported since the last turn ended
        self.turn_base = dict(input=0, cached=0, output=0, reasoning=0)
        self.spent = {"input": 0, "cached": 0, "output": 0, "reasoning": 0, "cost": 0.0}
        self.rpc = StdioRpc(argv(run.spec, run.model), run.cwd, on_notify=self._notify,
                            on_request=self._request, on_exit=self._exited,
                            on_stderr=lambda line: None, jsonrpc=True,
                            env=agent_env(run))

    # ---- control ----

    def start(self) -> None:
        run = self.run
        init = self.rpc.call("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": False},
            "clientInfo": {"name": "modstage", "version": __version__},
        }, timeout=90)
        self.can_image = bool(((init.get("agentCapabilities") or {}).get("promptCapabilities") or {}).get("image"))
        if run.start_images and not self.can_image:
            raise NoImages(self._no_images())
        agent = (init.get("agentInfo") or {}).get("name")
        if agent:
            run.add("status", f"connected to {agent}")
        mcp = mcp_server(run)
        stage = {"name": "modstage", "command": mcp["command"], "args": mcp["args"],
                   "env": [{"name": k, "value": v} for k, v in mcp["env"].items()]}
        session = self.rpc.call("session/new", {"cwd": run.cwd, "mcpServers": [stage]}, timeout=180)
        self.session_id = session.get("sessionId")
        run.set(session_id=self.session_id)
        wanted = run.model
        self._context_from(session)
        self._pick_model(session, wanted)
        self._prompt(f"{brief(run)}\n\nTask:\n{run.prompt}", run.start_images)

    def _no_images(self) -> str:
        return (f"{self.run.spec.get('name', self.run.engine)} does not accept images: its ACP initialize says "
                "promptCapabilities.image is false. Describe the image in words, or use an agent that takes images.")

    def _pick_model(self, session: dict, wanted: str | None) -> None:
        """Make the session run on the model that was asked for. A model flag is not enough: `kimi -m X acp`
        ignores it and starts on its default (seen 16 Oct 2026). So whenever the session reports a different
        current model, or the agent has no model flag at all, set it through ACP: the model config option
        (OpenCode), else session/set_model. Say so when that fails instead of running on another model."""
        run = self.run
        if not wanted:
            return
        option = next((o for o in session.get("configOptions") or []
                       if o.get("category") == "model" or o.get("id") == "model"), None)
        current = option.get("currentValue") if option else (session.get("models") or {}).get("currentModelId")
        if current == wanted or (current is None and run.spec.get("model_args")):
            run.set(model=wanted)
            return
        try:
            if option:
                self.rpc.call("session/set_config_option", {"sessionId": self.session_id, "configId": option["id"],
                                                             "value": wanted}, timeout=30)
            else:
                self.rpc.call("session/set_model", {"sessionId": self.session_id, "modelId": wanted}, timeout=30)
            run.set(model=wanted)
            run.add("status", f"model set to {wanted}" + (f" (the CLI had started on {current})" if current else ""))
        except Exception as exc:
            run.add("warning", f"could not switch to model {wanted} ({exc}); running on {current or 'the CLI default'}")
            run.set(model=current)

    def send(self, text: str, images: list[dict] | None = None) -> str:
        if images and not self.can_image:
            raise NoImages(self._no_images())
        self.run.add("you", text + (f"  [+{len(images)} image(s)]" if images else ""))
        if self.in_flight:
            # ACP has no mid-turn input, and some agents (Kimi) reject a second session/prompt while one runs,
            # so ModStage holds the message and sends it when the running turn returns
            self.held.append((text, images))
            self.run.set(queued=len(self.held))
            return "queued: it runs when the current turn ends (interrupt first to redirect now)"
        self._prompt(text, images)
        return "started a new turn"

    def interrupt(self) -> str:
        if not self.in_flight:
            return "nothing running"
        self.cancelling = True
        self.rpc.notify("session/cancel", {"sessionId": self.session_id})
        return "cancel sent"

    def close(self) -> None:
        self.rpc.close()

    def _prompt(self, text: str, images: list[dict] | None = None) -> None:
        self.in_flight = True
        self.run.set(status="running", activity="thinking", queued=len(self.held))
        blocks = [{"type": "text", "text": text}] + [
            {"type": "image", "mimeType": i["media_type"], "data": b64(i)} for i in images or []]

        def go():
            try:
                reply = self.rpc.call("session/prompt", {"sessionId": self.session_id, "prompt": blocks},
                                      timeout=6 * 3600)
            except Exception as exc:
                if self.cancelling:
                    # Some agents (Kimi) answer a cancelled prompt with an error instead of stopReason "cancelled"
                    self._turn_done({"stopReason": "cancelled"})
                    return
                self.in_flight = False
                dropped = len(self.held)
                self.held.clear()
                self.run.add("error", f"{self.run.engine} prompt failed: {exc}" +
                             (f"; {dropped} queued message(s) were not sent" if dropped else ""))
                self.run.set(status="error", error=str(exc), activity="failed", queued=0)
                return
            self._turn_done(reply)

        threading.Thread(target=go, daemon=True).start()

    def _turn_done(self, reply: dict) -> None:
        run = self.run
        self.in_flight = False
        self._flush_thought()
        meta = reply.get("_meta") or {}
        usage = meta.get("usage") or {}
        if usage:  # authoritative per-turn totals (Grok); replaces the live per-call estimate
            for key, src in (("input", "inputTokens"), ("cached", "cachedReadTokens"),
                             ("output", "outputTokens"), ("reasoning", "reasoningTokens")):
                self.spent[key] = self.turn_base[key] + usage.get(src, 0)
            self.spent["cost"] += (usage.get("costUsdTicks") or 0) / TICKS_PER_USD
            run.set_usage(input=self.spent["input"], cached=self.spent["cached"], output=self.spent["output"],
                          reasoning=self.spent["reasoning"],
                          cost_usd=round(self.spent["cost"], 4) if self.spent["cost"] else None)
        self.turn_base = {k: run.usage.get(k) or 0 for k in ("input", "cached", "output", "reasoning")}
        if meta.get("modelId"):
            run.set(model=meta["modelId"])
        if self.message.strip():
            run.add("message", self.message.strip())
            run.set(final_text=self.message.strip(), partial="")
        self.message = ""
        said, self.turn_said = self.turn_said, False
        stop = reply.get("stopReason")
        if stop == "cancelled" or self.cancelling:
            self.cancelling = False
            run.add("status", "interrupted")
        elif not said:
            # e.g. Kimi on a model its provider no longer serves: the CLI ends the turn and reports nothing
            run.add("warning", f"{run.spec.get('name', run.engine)} ended the turn with no reply, no thinking and no tool call. "
                               "The CLI probably failed (its model or provider); try another model, or run the CLI directly to see why.")
        if self.held:
            text, images = self.held.pop(0)
            self._prompt(text, images)  # the next queued message starts now
            return
        if stop == "cancelled":
            run.set(status="interrupted", activity="interrupted", queued=0)
        elif not said:
            run.set(status="idle", activity="empty turn: the CLI reported nothing", queued=0)
        elif stop in ("refusal", "max_tokens", "max_turn_requests"):
            run.add("warning", f"turn stopped: {stop}")
            run.set(status="idle", activity=f"stopped ({stop})", queued=0)
        else:
            run.add("status", "turn finished, waiting for Claude")
            run.set(status="idle", activity="idle", queued=0)

    def _context_from(self, payload: dict) -> None:
        models = payload.get("models") or {}
        current = models.get("currentModelId")
        for model in models.get("availableModels") or []:
            if model.get("modelId") == current:
                window = (model.get("_meta") or {}).get("totalContextTokens")
                self.run.set_usage(context_window=window)
                self.run.set(model=current)

    # ---- what the agent reports ----

    def _notify(self, msg: dict) -> None:
        params = msg.get("params") or {}
        update = params.get("update") or params
        kind = update.get("sessionUpdate")
        run = self.run
        if msg["method"] == "_x.ai/models/update":
            self._context_from({"models": update})
        if kind in ("agent_message_chunk", "agent_thought_chunk", "tool_call", "plan"):
            self.turn_said = True
        if kind == "agent_message_chunk":
            self._flush_thought()
            self.message += (update.get("content") or {}).get("text", "")
            run.set(partial=self.message, activity="writing")
        elif kind == "agent_thought_chunk":
            self.thought += (update.get("content") or {}).get("text", "")
            run.set(activity="thinking")
        elif kind == "tool_call":
            self._flush_thought()
            if self.message.strip():
                run.add("message", self.message.strip())
                self.message = ""
            raw = update.get("rawInput") or {}
            title = update.get("title") or update.get("kind") or "tool"
            self.tools[update.get("toolCallId", "")] = title
            seen = diff_blocks(update.get("content"))   # some agents send the diff with the call itself
            if seen:
                self.diffs[update.get("toolCallId", "")] = seen
            run.add("tool", f"{title} {_short(_what(raw), 600)}".strip(), args_detail(raw, _what(raw)) or None)
            run.set(activity=f"{title}: {_short(_what(raw), 60)}")
        elif kind == "tool_call_update" and update.get("status") in ("completed", "failed"):
            title = self.tools.pop(update.get("toolCallId", ""), "tool")
            out = _content_text(update.get("content"))
            diff = diff_blocks(update.get("content")) or self.diffs.pop(update.get("toolCallId", ""), "")
            self.diffs.pop(update.get("toolCallId", ""), None)
            run.add("result", f"{title} {update['status']}", clip(out) if out else None)
            if update.get("kind") in EDIT_KINDS or diff:
                paths = [loc.get("path") for loc in update.get("locations") or [] if loc.get("path")]
                run.add("edit", _short(update.get("title", title), 200), diff or None)
                if paths:
                    run.touch(paths)
        elif kind == "plan":
            steps = [e.get("content", "") for e in update.get("entries") or []]
            run.add("plan", "  ".join(f"• {s}" for s in steps))
        elif kind == "usage_update":
            used, size = update.get("used"), update.get("size")
            run.set_usage(context_used=used, context_window=size)
            cost = update.get("cost") or {}
            if cost.get("amount") is not None:
                run.set_usage(cost_usd=round(float(cost["amount"]), 4))
        elif kind == "response_completed":
            # Grok: usage per model call. Count it live; the turn total replaces it at the end.
            usage = update.get("usage") or {}
            run.add_usage(input=usage.get("input_tokens"), cached=usage.get("cache_read_input_tokens"),
                          output=usage.get("output_tokens"), reasoning=usage.get("reasoning_tokens"))
            run.set_usage(context_used=(usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                          + (usage.get("output_tokens") or 0))

    def _flush_thought(self) -> None:
        if self.thought.strip():
            self.run.add("thinking", _short(self.thought.strip(), 3000))
        self.thought = ""

    def _request(self, msg: dict) -> None:
        method, params = msg["method"], msg.get("params") or {}
        if method in ("fs/write_text_file", "fs/read_text_file"):
            self._fs(msg["id"], method, params)
            return
        if method != "session/request_permission":
            self.run.add("warning", f"{self.run.engine} asked {method}; refused")
            self.rpc.answer(msg["id"], error="modstage does not serve this request")
            return
        options = params.get("options") or []
        call = params.get("toolCall") or {}
        raw = call.get("rawInput") or {}
        paths = [loc.get("path") for loc in call.get("locations") or [] if loc.get("path")]
        pick = {k: next((o["optionId"] for o in options if o.get("kind") == k), None)
                for k in ("allow_once", "allow_always", "reject_once", "reject_always")}

        def answer(choice: str) -> None:
            option = {"allow": pick["allow_once"] or pick["allow_always"],
                      "allow_session": pick["allow_always"] or pick["allow_once"]}.get(choice) \
                or pick["reject_once"] or pick["reject_always"]
            outcome = {"outcome": "selected", "optionId": option} if option else {"outcome": "cancelled"}
            self.rpc.answer(msg["id"], {"outcome": outcome})

        title = call.get("title") or call.get("kind") or "use a tool"
        what = _what(raw) if raw else ""
        if what and what not in title:  # the card and stage_status show the exact command, not just "bash"
            title = f"{title} `{_short(what, 160)}`"
        self.run.request_approval(call.get("kind") or "tool", title, _short(what, 600),
                                  answer, paths)

    def _confined(self, path: str) -> str | None:
        """The real path when it is inside the run's folder (links resolved, so a planted link cannot lead out)."""
        if not isinstance(path, str) or not os.path.isabs(path):
            return None
        root, full = os.path.realpath(self.run.cwd), os.path.realpath(path)
        return full if full == root or full.startswith(root + os.sep) else None

    def _fs(self, rid, method: str, params: dict) -> None:
        """The agent writes (or reads) through us. A write is made only after the board's fence check passes."""
        run = self.run
        full = self._confined(params.get("path"))
        if full is None:
            run.add("warning", f"{run.engine} asked to {method.split('/')[1].replace('_', ' ')} outside the run's folder; refused")
            self.rpc.answer(rid, error=f"{params.get('path')} is outside the run's folder")
            return
        try:
            if method == "fs/read_text_file":
                with open(full, encoding="utf-8") as f:
                    lines = f.read().splitlines(keepends=True)
                start = max(int(params.get("line") or 1) - 1, 0)
                end = start + int(params["limit"]) if params.get("limit") else None
                self.rpc.answer(rid, {"content": "".join(lines[start:end])})
                return
            content = params.get("content")
            if not isinstance(content, str):
                self.rpc.answer(rid, error="content must be a string")
                return
            ok, reason = run.guard_write(full)
            if not ok:
                self.rpc.answer(rid, error=f"write rejected by the ModStage board: {reason}")
                return
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            run.add("edit", f"wrote {os.path.relpath(full, run.cwd)}")
            run.touch([full])
            self.rpc.answer(rid, {})
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.rpc.answer(rid, error=f"{method}: {exc}")

    def _exited(self, code: int) -> None:
        if self.run.adapter is not self:  # replaced by a restart or closed: not this run's news
            return
        if self.run.status in ("starting", "running"):
            self.run.add("error", f"{self.run.engine} exited with code {code}")
            self.run.set(status="error", error=f"exited {code}", activity="exited")
        elif self.run.status == "idle":
            self.run.set(status="done", activity="closed")
