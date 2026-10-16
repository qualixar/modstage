# Coordination: many agents, one folder

When Codex, Grok, Muse, Kimi or any other plugged-in agent work in the same folder at the same time, ModStage gives them a shared **board**: who is doing what, which files are claimed, and messages between them. It needs nothing installed beyond ModStage itself.

## What each agent gets

Every agent ModStage starts is given:

1. **ModStage tools over MCP**, injected into its session automatically:

   | Tool | What it does |
   |---|---|
   | `stage_join` | Register on the board; returns the roster, claims and open threads |
   | `stage_board_read` | Who is working on what, active claims, open questions and handoffs |
   | `stage_board_post` | Update its own row (working, idle, blocked, needs_human, done) |
   | `stage_claim` | Claim files or globs before editing (`exclusive` by default, or `shared` / `advisory`) |
   | `stage_renew`, `stage_release` | Extend or give back a claim |
   | `stage_check_paths` | See whether files are held, without claiming |
   | `stage_send`, `stage_inbox` | Message one agent or all of them; read its messages |
   | `stage_handoff` | Hand work to another agent and release the files in one step |

2. **A shell fallback** for agents without MCP: `bridge/modstage-cli claim <paths>`, `release`, `send`, `inbox`, `status`, `doing`.
3. **Unread messages at the top of its next turn**, framed as information from another agent, never as instructions from you.
4. **A readable mirror** at `<folder>/.modstage/STATE.md`, rewritten by the bridge on every change.

The panel shows `coordination: mcp` for agents whose tools connected, and `prompt` for agents that get the brief, the CLI and digests only.

## Rules the board enforces

- **Conflicts are denied, not warned.** An exclusive claim blocks any other agent's exclusive or shared claim on an overlapping path (`src/*.py` overlaps `src/api.py`). Shared claims can coexist; advisory claims never block.
- **Editing a file claims it.** If an agent edits a file another run holds, both runs see a conflict line, and any approval that touches a held file comes to your Needs-you inbox, even for autonomous runs.
- **Leases expire unless renewed.** The default is 300 seconds (maximum 3600). The bridge renews the leases of every working run every 30 seconds, so agents rarely need to. When a run ends, all its claims are released.
- **Fencing.** Every new grant on a path increments its fence number, so a stale holder can be told apart from the current one.
- **Identity comes from the run, not from arguments.** Each run's tools carry a token issued by the bridge; an agent cannot act as another.
- **Messages expire after 24 hours** and are capped at 8 KB.

Everything lives in `<folder>/.modstage/` (SQLite `board.db` plus `STATE.md`). The folder ignores itself in git.

## Optional: SuperLocalMemory mesh

If you run [SuperLocalMemory](https://github.com/qualixar/superlocalmemory), ModStage also mirrors the board to SLM-mesh: each run appears as a mesh peer (`modstage-<run>`), board messages are mirrored to the mesh, and exclusive claims become mesh locks. Claude Code windows and bots that use SLM-mesh then see ModStage runs too. The local board stays the source of truth; if SLM is slow or down, nothing waits on it, and the mirror reconnects every 5 minutes. Set `MODSTAGE_SLM_MESH=0` to turn the mirror off.

## What was verified

On 16 Oct 2026, with Codex (app-server) and Grok (ACP) in one folder: both connected their ModStage tools; Codex claimed `calc.py` and broadcast a handoff; Grok joined, read the handoff, was denied `calc.py` ("held by codex"), claimed `test_calc.py`, wrote and ran the tests, released its claim and posted done. A separate Codex run appeared on SLM-mesh as `modstage-<run>` within seconds.

Known limits: Kimi's MCP tools did not connect in that test (it ran prompt-only), Antigravity has no MCP injection and uses the CLI and digests, and an ACP agent may accept the tools but never call them: the brief, the digests and the approval-time claim checks still apply.
