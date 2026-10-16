"""Write docs/PARITY-MATRIX.md from the conformance harness.

Every bridge cell is the result of actually running its check now, so the page cannot claim more
than the tests show. Usage:  python3 bridge/tests/parity_matrix.py [--check]
--check exits 1 when a cell's run disagrees with the table (a gap that now passes, a works that fails).
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import conformance as C  # noqa: E402
from fakes import BRIDGE_AGENTS  # noqa: E402

OUT = HERE.parents[1] / "docs" / "PARITY-MATRIX.md"
NAMES = {"claude": "Claude", "codex": "Codex", "muse": "Muse", "grok": "Grok", "antigravity": "Antigravity",
         "kimi": "Kimi", "qwen": "Qwen Code", "opencode": "OpenCode"}
MARK = {"works": "✅ works", "degraded": "🟡 degraded", "gap": "❌ gap", "n/a": "➖ n/a"}

# Claude subagents start through the mod API ($.agent.spawn), not the bridge, so the fake harness
# does not cover them. These cells are read from hooks/register.tsx, and say so.
CLAUDE = {
    "start": ("works", "$.agent.spawn from the launcher or the Agent tool; tests/panel.test.tsx draws it"),
    "model": ("works", "haiku / sonnet / opus / any id, passed to $.agent.spawn"),
    "stream": ("degraded", "tool calls and the final message via hooks; no partial text stream"),
    "long_turn": ("degraded", "the tab shows the current tool; no thinking stream"),
    "approval": ("degraded", "Claude Code's own permission prompts apply, not the Needs-you inbox"),
    "steer": ("works", "SendMessage to the subagent ($.session.send)"),
    "queued": ("n/a", "messages reach the subagent after its current step"),
    "interrupt": ("n/a", "Claude stops its own subagents; the tab offers no interrupt"),
    "resume": ("works", "SendMessage continues a finished subagent"),
    "close": ("degraded", "closing the tab stops showing it; the subagent is Claude's to stop"),
    "images": ("n/a", "the Agent tool takes text; Claude passes files by path"),
}


def run_one(test_name: str) -> str:
    """'pass', 'fail' or 'xfail-ok' / 'xpass' for one generated test."""
    import test_conformance as T
    suite = unittest.defaultTestLoader.loadTestsFromName(test_name, T)
    result = unittest.TestResult()
    suite.run(result)
    if result.unexpectedSuccesses:
        return "xpass"
    if result.expectedFailures:
        return "xfail-ok"
    return "pass" if result.wasSuccessful() else "fail"


def cell_text(agent: str, control: str, problems: list[str]) -> tuple[str, str]:
    state, why = C.cell(agent, control)
    if state == "n/a" and (agent, control) not in C.NA_CHECKED:
        return MARK[state], why
    got = run_one(f"ParityTest.test_{agent}_{control}")
    expected = "xfail-ok" if state == "gap" else "pass"
    if got != expected:
        problems.append(f"{agent}/{control}: table says {state}, run gave {got}")
        return f"⚠ {state}? run gave {got}", why
    return MARK[state], why


def main() -> int:
    problems: list[str] = []
    header = "| Agent | " + " | ".join(C.TITLES[c] for c in C.CONTROLS) + " |"
    rule = "|---" * (len(C.CONTROLS) + 1) + "|"
    rows, notes = [], []
    for agent in ["claude", *BRIDGE_AGENTS]:
        cells = []
        for control in C.CONTROLS:
            if agent == "claude":
                state, why = CLAUDE[control]
                mark = MARK[state]
            else:
                mark, why = cell_text(agent, control, problems)
            if why:
                notes.append((agent, control, why))
                mark += f" [{len(notes)}]"
            cells.append(mark)
        rows.append(f"| {NAMES[agent]} | " + " | ".join(cells) + " |")

    shared = []
    for key, (title, state, ref) in C.SHARED.items():
        if key in C.SHARED_CHECKS:
            got = run_one(f"ParityTest.test_shared_{key}")
            expected = "xfail-ok" if state == "gap" else "pass"
            if got != expected:
                problems.append(f"shared/{key}: table says {state}, run gave {got}")
        shared.append(f"| {title} | {MARK[state]} | {ref or 'bridge/tests/conformance.py'} |")

    lines = [
        "# ModStage parity matrix",
        "",
        f"Generated {date.today().isoformat()} by `python3 bridge/tests/parity_matrix.py` from the conformance harness "
        "(`bridge/tests/conformance.py`, protocol fakes, zero tokens). Every bridge cell was produced by running its check; "
        "a gap is an expected failure, so fixing one fails the suite until the table is updated. "
        "The Claude row is read from `hooks/register.tsx`, not run through the fakes.",
        "",
        "What the fakes prove: ModStage sends and reads each CLI's protocol messages correctly, as we understand the "
        "protocol. What they do not prove: that the real CLI still speaks that protocol. That is the job of "
        "`scripts/smoke-real-cli.sh` (manual, one agent at a time, tiny prompts).",
        "",
        "✅ works · 🟡 degraded (works within a limit the CLI sets; the note says which) · ❌ gap (a defect we own) · ➖ n/a (the CLI has no such channel; ModStage must say so)",
        "",
        header, rule, *rows,
        "",
        "## Checked once for every agent",
        "",
        "| Control | State | Where |", "|---|---|---|", *shared,
        "",
        "## Notes",
        "",
        *[f"{i}. **{NAMES[a]} · {C.TITLES[c]}**: {why}" for i, (a, c, why) in enumerate(notes, 1)],
        "",
        "## What the tests cannot show",
        "",
        "- The test kit has no implementation of `$.ui.scroll`, so no test moves a real pane. Tests prove that a new "
        "approval reaches the code that asks the pane to scroll to the `inbox` key, and the arguments it asks with. "
        "Whether the desktop app then shows the card is checked only by looking at the real panel.",
        "- Images: the fakes prove each protocol's shape (Codex localImage path, Muse image part with base64Data, ACP image "
        "block) and the per-agent capability as each CLI's own initialize reported it on 16 Oct 2026. No real CLI has yet "
        "been handed an image through ModStage.",
        "- Queued messages: for ACP agents 'Interrupt and send now' sends session/cancel and the queued prompt runs next; "
        "the fakes show the cancel and the count, not that every ACP CLI starts the queued prompt after a cancel.",
        "- Long turns: Antigravity's stream carries step events but no thinking text. What agy did during the ~6 quiet "
        "minutes of one demo run is still unknown; the panel now shows 'no new output for Nm, still running' instead "
        "of looking frozen.",
        "- Resume: Grok, Kimi, Qwen Code and OpenCode advertise ACP loadSession, so a native resume is possible; ModStage "
        "still restarts with a recap. That is listed as degraded, not built.",
        "- Claude Code's own approvals for its subagents are outside ModStage: Claude Code asks for those itself.",
        "",
        "## Live checks with real CLIs (October 2026)",
        "",
        "Run against an installed build with tiny prompts, one agent at a time (`scripts/smoke_real_cli.py` does the same):",
        "",
        "- Codex network approval: the card is raised and `stage_wait` reports `waiting_on_user`; a typed \"yes\" is refused "
        "(409); another Claude session cannot answer it (403); an invalid choice is refused (400); a decision passed from "
        "Claude chat is logged as \"decided by the user in Claude chat\".",
        "- In the desktop panel: the band's \"needs you\" button opens the panel with the card at the top, and each Claude "
        "session lists only the runs it started.",
        "- Codex takes a PNG through `images` and describes it.",
        "- Antigravity in ask mode ends a turn that needed a command as `blocked: refused …`, with the refusal in the feed.",
        "- Muse lists its models through `model/list`; OpenCode switches model through its ACP config option.",
        "- Kimi: a message sent mid-turn shows \"1 queued\"; \"Interrupt and send now\" ends the turn and the held message "
        "runs next. This needed three fixes found live: `kimi -m X acp` ignores the flag (ModStage now sets the model through "
        "ACP), Kimi rejects a second prompt while one runs (ModStage now holds queued messages), and Kimi answers a cancel "
        "with an error (ModStage treats it as the interrupt).",
        "- A CLI that ends a turn without reporting anything (for example on a model its provider no longer serves) is "
        "flagged as an empty turn instead of a clean finish.",
        "- Not seen on screen yet: the message box refusing free text while a card waits (covered by the bridge's 409 and "
        "tests/panel.test.tsx).",
        "- A Claude Code session that loaded an older ModStage keeps that version's tool schemas; start a new session after "
        "updating.",
        "",
        "## Why some rows read the way they do",
        "",
        "- **Antigravity approvals are n/a**: probed on agy 1.4.0 in stream-json print mode without the skip-permissions "
        "flag. A command that needs permission is auto-denied, the turn ends with `result.denied_actions`, and stderr says "
        "headless mode cannot prompt. There is no stream-json input that answers a permission, so ModStage shows the refusal "
        "and says so before Start.",
        "- **Approvals time out after 10 minutes**: an unanswered card is denied with the reason \"no answer in time\". "
        "Typing \"yes\" in the message box is not an answer, which is why the box refuses text while a card waits.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}")
    for p in problems:
        print("MISMATCH", p)
    return 1 if problems and "--check" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
