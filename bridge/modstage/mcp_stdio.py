"""The ModStage coordination tools as a stdio MCP server, started by each agent.

The bridge injects this into every agent session it starts:
  command: <python>  args: ["-m", "modstage.mcp_stdio"]
  env: MODSTAGE_RUN_TOKEN (this run's identity), MODSTAGE_URL, PYTHONPATH (the bridge folder)
Each tool call is forwarded to the bridge's /board API with the run's token, so an agent can only
act as itself. Standard library only; speaks MCP (JSON-RPC 2.0, newline-delimited) on stdin/stdout.
"""

from __future__ import annotations

from . import __version__

import json
import os
import sys
import urllib.error
import urllib.request

from .board_api import OPS

URL = os.environ.get("MODSTAGE_URL", "http://127.0.0.1:47321")
TOKEN = os.environ.get("MODSTAGE_RUN_TOKEN", "")
PROTOCOL = "2025-06-18"


def _board(op: str, args: dict) -> dict:
    req = urllib.request.Request(f"{URL}/board/{op}", data=json.dumps(args).encode(), method="POST",
                                 headers={"X-ModStage-Run-Token": TOKEN, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return {"error": json.loads(exc.read()).get("error", str(exc))}
        except ValueError:
            return {"error": str(exc)}
    except OSError as exc:
        return {"error": f"ModStage bridge unreachable: {exc}"}


def _tools() -> list[dict]:
    return [{"name": f"stage_{op}", "description": desc,
             "inputSchema": {"type": "object", "properties": props, "required": req}}
            for op, (desc, props, req) in OPS.items()]


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": version, "capabilities": {"tools": {}},
                "serverInfo": {"name": "modstage", "version": __version__},
                "instructions": "Coordination with other agents in this workspace: claim files before editing "
                                "(stage_claim), release them after, read stage_inbox, post progress with stage_board_post."}})
            _board("join", {"_via": "mcp"})  # proves the tools reached this agent
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": _tools()}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = str(params.get("name", ""))
            op = name[len("stage_"):] if name.startswith("stage_") else name
            if op not in OPS:
                _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}})
                continue
            out = _board(op, params.get("arguments") or {})
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, indent=1)}], "isError": "error" in out}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method {method} not found"}})


if __name__ == "__main__":
    main()
