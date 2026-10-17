"""The board operations agents can perform, shared by the HTTP API, the MCP server and the CLI.

Identity is the caller's run, resolved from its per-run token by the server, never from arguments.
"""

from __future__ import annotations

import os

from typing import Callable

from .board import KINDS, MODES, STATES, board_for
from .run import RUNS, Run
from .slm_mesh import MESH, bg

# op -> (description, input JSON schema properties, required)
OPS: dict[str, tuple[str, dict, list[str]]] = {
    "join": ("Register on the workspace board and get the roster, active claims and open threads. Call once at the start.",
             {"doing": {"type": "string", "description": "One line: what you are working on"}}, []),
    "board_read": ("Read the workspace board: who is working on what, active file claims, open questions and handoffs.",
                   {}, []),
    "board_post": ("Update your row on the board.",
                   {"state": {"type": "string", "enum": list(STATES)}, "doing": {"type": "string"}}, ["state", "doing"]),
    "claim": ("Claim files before editing them. Exclusive conflicts are denied: if denied, pick other files or ask the holder.",
              {"paths": {"type": "array", "items": {"type": "string"}, "description": "Files or globs, workspace-relative"},
               "mode": {"type": "string", "enum": list(MODES), "description": "exclusive (default), shared, or advisory"},
               "ttl_s": {"type": "number", "description": "Lease seconds, default 300, max 3600; renewed while you work"},
               "reason": {"type": "string"}}, ["paths"]),
    "renew": ("Extend your claims (they are also renewed automatically while you work).",
              {"claim_id": {"type": "string", "description": "A claim id, or 'all'"}, "ttl_s": {"type": "number"}}, []),
    "release": ("Release a claim when you are done with those files.",
                {"claim_id": {"type": "string", "description": "A claim id, a path, or 'all'"}}, []),
    "check_paths": ("Check whether files are held by another agent, without claiming them.",
                    {"paths": {"type": "array", "items": {"type": "string"}}}, ["paths"]),
    "send": ("Message another agent (by run id) or 'all' agents in this workspace.",
             {"to": {"type": "string", "description": "A run id, or 'all'"},
              "kind": {"type": "string", "enum": list(KINDS)}, "body": {"type": "string"},
              "thread": {"type": "string"}, "wake": {"type": "boolean", "description": "Start a turn for an idle receiver"}},
             ["to", "body"]),
    "inbox": ("Read messages other agents sent you (marks them read).", {}, []),
    "handoff": ("Hand work to another agent: sends a handoff message and releases your claims on those files.",
                {"to": {"type": "string"}, "summary": {"type": "string"},
                 "files": {"type": "array", "items": {"type": "string"}},
                 "next": {"type": "array", "items": {"type": "string"}}}, ["to", "summary"]),
}


def perform(op: str, run: Run, body: dict, wake: Callable[[Run], None]) -> dict:
    board = board_for(run.cwd)
    board.heartbeat(run.id)
    if op == "join":
        if run.coordination != "mcp" and body.get("_via") == "mcp":
            run.coordination = "mcp"
            run.add("status", "coordination tools connected")
        return board.join(run.id, run.engine, run.label, body.get("doing", ""), via=body.get("_via", "tool"), owner=run.owner)
    if op == "board_read":
        return board.read(run.owner)
    if op == "board_post":
        return board.post(run.id, str(body.get("state", "working")), str(body.get("doing", "")))
    if op == "claim":
        paths = [str(p) for p in body.get("paths") or []]
        if not paths:
            raise ValueError("paths is empty")
        if len(paths) > 50:
            raise ValueError("claim at most 50 paths at a time")
        wide = [p for p in paths if p.strip("/ ") in ("*", "**", "**/*", ".", "") or p.strip().startswith("..")]
        if wide:
            raise ValueError(f"claims must name files or folders inside the workspace, not {', '.join(wide)}")
        res = board.claim(run.id, paths, str(body.get("mode") or "exclusive"), float(body.get("ttl_s") or 300),
                          str(body.get("reason", "")))
        if res["granted"]:
            run.add("claim", f"claimed {', '.join(g['path'] for g in res['granted'])}")
            for g in res["granted"]:
                if g["mode"] == "exclusive" and not g.get("renewed"):
                    bg(MESH.lock, run, g["path"], True)
        for d in res["denied"]:
            run.add("conflict", f"denied {d['path']}: held by {d['holder_name']}")
        return res
    if op == "renew":
        return {"renewed": board.renew(run.id, str(body.get("claim_id") or "all"), float(body.get("ttl_s") or 300))}
    if op == "release":
        target = str(body.get("claim_id") or "all")
        n = board.release(run.id, target)
        if n and target != "all" and not target.startswith("c0"):
            bg(MESH.lock, run, target, False)
        if n:
            run.add("claim", f"released {n} claim(s)")
        return {"released": n}
    if op == "check_paths":
        return {"held": board.holders(run.id, [str(p) for p in body.get("paths") or []])}
    if op == "send":
        to = _recipient(run, str(body.get("to") or "all"))
        res = board.send(run.id, to, str(body.get("kind") or "info"), str(body.get("body", "")), str(body.get("thread", "")),
                         owner=run.owner)
        run.add("sent", f"→ {to}: {str(body.get('body', ''))[:160]}")
        _notify(run, to, str(body.get("body", "")), bool(body.get("wake")), wake)
        return res
    if op == "inbox":
        return {"messages": board.inbox(run.id, owner=run.owner)}
    if op == "handoff":
        to = _recipient(run, str(body.get("to") or "all"))
        files = [str(f) for f in body.get("files") or []]
        nxt = [str(n) for n in body.get("next") or []]
        text = str(body.get("summary", "")) + (f"\nFiles: {', '.join(files)}" if files else "") + \
            ("\nNext:\n" + "\n".join(f"- {n}" for n in nxt) if nxt else "")
        res = board.send(run.id, to, "handoff", text, owner=run.owner)
        released = sum(board.release(run.id, f) for f in files)
        run.add("sent", f"handoff → {to}: {str(body.get('summary', ''))[:140]}")
        _notify(run, to, text, True, wake)
        return {**res, "released": released}
    raise ValueError(f"unknown board operation {op}")


def _recipient(sender, to: str) -> str:
    """'all', or a run or Claude peer of the sender's own session in this folder. Another session's agents
    are not reachable: a session's children take messages only from their own family."""
    if to == "all":
        return to
    from .claude_peer import peer_ids
    here = os.path.realpath(sender.cwd)
    family = {r.id for r in RUNS.values() if r.owner == sender.owner and os.path.realpath(r.cwd) == here} \
        | peer_ids(sender.owner, sender.cwd)
    if to not in family or to == sender.id:
        raise ValueError(f"no agent {to} of this Claude Code session works in this folder; "
                         "messages reach only this session's own agents")
    return to


def _notify(sender: Run, to: str, body: str, wake_idle: bool, wake: Callable[[Run], None]) -> None:
    """Show the message on the receivers' feeds; optionally wake idle receivers. Receivers are the sender's
    own session's runs in this folder; another session's agents are never shown it or woken by it."""
    here = os.path.realpath(sender.cwd)
    targets = [r for r in RUNS.values() if os.path.realpath(r.cwd) == here and r is not sender and r.owner == sender.owner
               and (to == "all" or r.id == to)]
    for target in targets:
        target.add("inbox", f"from {sender.engine} {sender.id}: {body[:200]}")
        if wake_idle and target.status == "idle" and target.adapter is not None:
            wake(target)
