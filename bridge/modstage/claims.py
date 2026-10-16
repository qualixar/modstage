"""File claims, backed by the workspace board (see board.py).

A run claims files three ways: up front (`owns`, globs Claude passes to stage_start), explicitly
(stage_claim tool or the modstage CLI), and by editing them (every edit an adapter reports becomes
an exclusive lease). Before an approval the board says whether the files are held by another run;
after an edit it warns both runs. Works with nothing else installed.
"""

from __future__ import annotations

import os

from .board import board_for
from .slm_mesh import MESH, bg


class ClaimBoard:
    def register(self, run) -> None:
        board = board_for(run.cwd)
        board.join(run.id, run.engine, run.label, run.label)
        bg(MESH.joined, run)
        if run.owns:
            res = board.claim(run.id, run.owns, "exclusive", reason="declared at start")
            for d in res["denied"]:
                run.add("conflict", f"{d['path']} is already held by {d['holder_name']}; this run was told not to edit it")

    def touched(self, run, full: str) -> None:
        board = board_for(run.cwd)
        rel = os.path.relpath(full, run.cwd)
        blockers = board.holders(run.id, [rel])
        if blockers:
            other = blockers[0]
            run.add("conflict", f"{rel} is held by {other['holder_name']} ({other['mode']})")
            from .run import RUNS
            if other["holder"] in RUNS:
                RUNS[other["holder"]].add("conflict", f"{run.engine} run {run.id} changed {rel}, which this run holds")
            return
        board.claim(run.id, [rel], "exclusive", reason="edited")

    def conflict_note(self, run, paths: list[str]) -> str:
        if not paths:
            return ""
        held = board_for(run.cwd).holders(run.id, paths)
        return "; ".join(f"{h['path']} is held by {h['holder_name']}" for h in held)

    def owners_brief(self, run) -> str:
        return board_for(run.cwd).brief_claims(run.id)

    def ended(self, run) -> None:
        board_for(run.cwd).leave(run.id)
        bg(MESH.left, run)


BOARD = ClaimBoard()
