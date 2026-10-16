"""Claude Code as a peer on a folder's board (Phase 3, option P1).

Each Claude Code session that works in a folder gets one board row, `claude-<first 8 of its session id>`.
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


def peer_id(session: str) -> str:
    return f"claude-{(session or 'unknown').replace('-', '')[:8]}"


class ClaudePeer:
    """Duck-types the parts of a Run the board operations use (id, engine, label, cwd, add)."""

    def __init__(self, session: str, cwd: str):
        self.session = session
        self.id = peer_id(session)
        self.engine = "claude"
        self.label = "Claude Code (orchestrator)"
        self.cwd = cwd
        self.owner = session
        self.coordination = "claude"
        self.events: list[dict] = []

    def add(self, kind: str, text: str, detail: str | None = None) -> None:
        self.events.append({"ts": time.time(), "kind": kind, "text": text[:400]})
        del self.events[:-100]


_PEERS: dict[tuple[str, str], ClaudePeer] = {}
_LOCK = threading.Lock()


def peer_for(session: str, cwd: str) -> ClaudePeer:
    """This session's row on this folder's board, joining it the first time."""
    cwd = os.path.abspath(os.path.expanduser(cwd))
    if not session:
        raise ValueError("session is required")
    if not os.path.isdir(cwd):
        raise ValueError(f"cwd {cwd} is not a folder")
    with _LOCK:
        peer = _PEERS.get((session, cwd))
        if peer is None:
            peer = _PEERS[(session, cwd)] = ClaudePeer(session, cwd)
            board_for(cwd).join(peer.id, "claude", peer.label, "orchestrating this folder's agents", via="claude")
    return peer


def perform(op: str, body: dict, wake: Callable) -> dict:
    if op not in OPS:
        raise ValueError(f"Claude cannot perform board operation '{op}'; allowed: {', '.join(OPS)}")
    peer = peer_for(str(body.get("session") or ""), str(body.get("cwd") or ""))
    if op == "inbox" and body.get("peek"):
        return {"messages": board_for(peer.cwd).inbox(peer.id, mark_read=False)}
    return board_api.perform(op, peer, body, wake)


def edit_conflicts(session: str, path: str) -> list[dict]:
    """Live exclusive claims by agents on `path`, in any folder board that contains it. Claude's own
    claims never conflict with Claude. An empty list means Claude may edit."""
    full = os.path.abspath(os.path.expanduser(path))
    me = peer_id(session)
    out = []
    for board in all_boards():
        root = os.path.abspath(board.cwd)
        if full == root or full.startswith(root + os.sep):
            rel = os.path.relpath(full, root)
            for held in board.holders(me, [rel], "exclusive"):
                out.append({**held, "workspace": root})
    return out
