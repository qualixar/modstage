"""What every agent is told and given so it works as one of Claude Code's subagents beside the others."""

from __future__ import annotations

import os
import sys

BRIDGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(BRIDGE_DIR, "modstage-cli")


def agent_env(run) -> dict[str, str]:
    """Environment for the agent process and its ModStage tools: identity is the run's own token.
    Only MODSTAGE_* variables: this env is the agent's own, so it must not touch the agent's Python
    (PYTHONPATH / PYTHONSAFEPATH would break sibling imports in its scripts). Shadowing protection for
    Python that ModStage starts itself lives in mcp_server / safe_python."""
    return {"MODSTAGE_RUN_TOKEN": run.board_token, "MODSTAGE_RUN_ID": run.id,
            "MODSTAGE_URL": f"http://127.0.0.1:{os.environ.get('MODSTAGE_PORT', '47321')}"}


# Start a modstage module so the working folder (an agent's repository) can never shadow a standard-library
# or modstage module: drop "" and "." from sys.path before anything else is imported. Works on 3.10, where
# -P and PYTHONSAFEPATH do not exist yet. argv: [python, "-c", SAFE_LAUNCH, <bridge dir>, <module>, args...]
SAFE_LAUNCH = ("import sys; sys.path[:] = [p for p in sys.path if p not in ('', '.')]; "
               "sys.path.insert(0, sys.argv.pop(1)); m = sys.argv.pop(1); import runpy; "
               "runpy.run_module(m, run_name='__main__', alter_sys=True)")


def safe_python(module: str) -> list[str]:
    return ["-c", SAFE_LAUNCH, BRIDGE_DIR, module]


def mcp_server(run) -> dict:
    """The ModStage MCP server for this run: {command, args, env}."""
    return {"command": sys.executable, "args": safe_python("modstage.mcp_stdio"), "env": {**agent_env(run), "PYTHONPATH": BRIDGE_DIR, "PYTHONSAFEPATH": "1"}}


# agents whose shell runs in a sandbox that blocks the loopback bridge: they must use the board tools
SANDBOXED_SHELL = {"codex"}


def brief(run) -> str:
    from .claims import BOARD
    lines = [
        f"You are running as a subagent of Claude Code (run {run.id}, {run.spec.get('name', run.engine)}).",
        "Claude Code or the user may send you new instructions while you work: follow the newest one.",
        "Other agents may be working in this same folder at the same time.",
    ]
    if run.owns:
        lines.append(f"You own these files or patterns; change only these unless told otherwise: {', '.join(run.owns)}.")
    others = BOARD.owners_brief(run)
    if others:
        lines.append("Other runs have claimed these files; do not edit them:\n" + others)
    tools = ("Coordinate through the workspace board with your stage_join, stage_claim, stage_release, stage_send and "
             "stage_inbox tools: call stage_join first, stage_claim files before editing them, stage_release them when done, "
             "and read stage_inbox between steps. ")
    if run.engine in SANDBOXED_SHELL:
        # Their shell sandbox cannot reach the local bridge (the CLI fails with "Operation not permitted"); only the tools can.
        shell = "Do not use the shell for this: your shell cannot reach the board, only those tools can. "
    else:
        shell = (f"Without those tools, use the shell: {CLI} claim <paths> | release <path|all> | send <run|all> <text> | "
                 "inbox | status. ")
    lines += [
        tools + shell + "The board is mirrored at .modstage/STATE.md (read it, never edit it).",
        "Do not touch git branches, worktrees, or files outside the task.",
        "End with a short summary: what you changed, what you verified, what is left.",
    ]
    return "\n".join(lines)
