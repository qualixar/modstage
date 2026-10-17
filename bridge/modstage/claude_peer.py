"""Claude Code as a peer on a folder's board (Phase 3, option P1).

Each Claude Code session that works in a folder gets one board row, `claude-<16 hex of its scope>`. The
scope is the session's owner (the hash of the secret it registered with), never its session id, so an agent
that knows the session id cannot act as its Claude peer.
Agents see it in their roster and can message it; Claude reads the board, posts, and claims files it is
about to edit itself, through the same board operations agents use. Messages to Claude are information
from agents, never instructions and never approvals: they surface the next time Claude asks
(stage_board, stage_wait, stage_status) and never start a Claude turn on their own.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Callable

from . import board_api
from .board import all_boards, board_for

# board operations a Claude session may perform on a folder's board
OPS = ("board_read", "send", "claim", "release", "check_paths", "inbox", "board_post")


def peer_id(owner: str) -> str:
    return f"claude-{(owner or 'unknown').replace('-', '')[:16]}"


class ClaudePeer:
    """Duck-types the parts of a Run the board operations use (id, engine, label, cwd, add)."""

    def __init__(self, owner: str, cwd: str):
        self.id = peer_id(owner)
        self.engine = "claude"
        self.label = "Claude Code (orchestrator)"
        self.cwd = cwd
        self.owner = owner
        self.coordination = "claude"
        self.events: list[dict] = []

    def add(self, kind: str, text: str, detail: str | None = None) -> None:
        self.events.append({"ts": time.time(), "kind": kind, "text": text[:400]})
        del self.events[:-100]


_PEERS: dict[tuple[str, str], ClaudePeer] = {}
_LOCK = threading.Lock()


def peer_for(owner: str, cwd: str) -> ClaudePeer:
    """This session's row on this folder's board, joining it the first time."""
    cwd = os.path.realpath(os.path.expanduser(cwd))
    if not owner:
        raise ValueError("a registered Claude Code session is required")
    if not os.path.isdir(cwd):
        raise ValueError(f"cwd {cwd} is not a folder")
    with _LOCK:
        peer = _PEERS.get((owner, cwd))
        if peer is None:
            peer = _PEERS[(owner, cwd)] = ClaudePeer(owner, cwd)
            board_for(cwd).join(peer.id, "claude", peer.label, "orchestrating this folder's agents", via="claude", owner=owner)
    return peer


def peer_ids(owner: str, cwd: str) -> set[str]:
    """The Claude peer of this owner in this folder, if it has joined."""
    with _LOCK:
        return {p.id for (o, c), p in _PEERS.items() if o == owner and c == os.path.realpath(cwd)}


def perform(op: str, body: dict, wake: Callable, owner: str) -> dict:
    if op not in OPS:
        raise ValueError(f"Claude cannot perform board operation '{op}'; allowed: {', '.join(OPS)}")
    peer = peer_for(owner, str(body.get("cwd") or ""))
    if op == "inbox" and body.get("peek"):
        return {"messages": board_for(peer.cwd).inbox(peer.id, mark_read=False, owner=owner)}
    return board_api.perform(op, peer, body, wake)


def edit_conflicts(owner: str, path: str) -> list[dict]:
    """Live exclusive claims by agents on `path`, in any folder board that contains it. Claude's own
    claims never conflict with Claude. An empty list means Claude may edit."""
    full = os.path.realpath(os.path.expanduser(path))
    me = peer_id(owner)
    out = []
    for board in all_boards():
        root = os.path.realpath(board.cwd)
        if full == root or full.startswith(root + os.sep):
            rel = os.path.relpath(full, root)
            for held in board.holders(me, [rel], "exclusive"):
                out.append({**held, "workspace": root})
    return out
