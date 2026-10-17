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
   | `stage_send`, `stage_inbox` | Message one agent or all of them in its own Claude Code session; read its messages |
   | `stage_handoff` | Hand work to another agent and release the files in one step |

2. **A shell fallback** for agents without MCP: `bridge/modstage-cli claim <paths>`, `release`, `send`, `inbox`, `status`, `doing`.
3. **Unread messages at the top of its next turn**, framed as information from another agent, never as instructions from you.
4. **A readable mirror** at `<folder>/.modstage/STATE.md`, rewritten by the bridge on every change. It holds the roster and the claims only, never messages or what an agent says it is doing.

## Two Claude Code sessions in one folder

Each session's agents are a family of their own, the way Claude Code's own subagents belong to one session:

- **Shared, because file safety needs it:** the roster (engine, run id, state) and every claim and fence. Agents of different sessions never write over each other.
- **Kept per session:** messages, threads, wakes, what an agent says it is doing, and the log lines that quote them. `stage_send` to another session's agent is refused, `all` means "all of this session's agents here", and `stage_board_read` lists other sessions' agents as "another session" with no label or doing text.

The panel shows `coordination: mcp` for agents whose tools connected, and `prompt` for agents that get the brief, the CLI and digests only.

## Rules the board enforces

- **Conflicts are denied, not warned.** An exclusive claim blocks any other agent's exclusive or shared claim on an overlapping path (`src/*.py` overlaps `src/api.py`). Shared claims can coexist; advisory claims never block.
- **Editing a file claims it.** If an agent edits a file another run holds, both runs see a conflict line, and any approval that touches a held file comes to your Needs-you inbox, even for autonomous runs.
- **Leases expire unless renewed.** The default is 300 seconds (maximum 3600). The bridge renews the leases of every working run every 30 seconds, so agents rarely need to. A run that is idle, interrupted or paused is not renewed, so its leases lapse and another run may take the files; this is what makes the fence meaningful. When a run ends, all its claims are released.
- **Fencing is checked at the write.** Every new grant on a path increments its fence number. For the agents below, the bridge checks the fence on every write it can intercept, not only when a lease is claimed or an approval is given: a write goes through only if the run holds a live lease on the path whose fence is the path's newest, or nobody else holds the path and this run has not been overtaken (then the write claims it with a new fence). So if A is paused, its lease expires, B claims and edits the file, and A then resumes with a permission it was given earlier, A's write is rejected and the file keeps B's content. Both runs get a conflict line, and a stale writer must claim the file again and re-read it. An "allow for this run" on a file edit is not carried forward: each edit is checked again.
- **Which agents get write-time fencing.** Codex: every file change it sends for approval (in autonomous runs ModStage starts Codex with approval policy `untrusted`, so every edit comes through the bridge and is answered at once after the check; in ask runs Codex only asks for edits outside its sandbox, so in-sandbox edits there are still detected afterwards). Grok, Kimi, Qwen Code, OpenCode and other ACP agents: ModStage now serves `fs/write_text_file` and `fs/read_text_file` (limited to the run's folder), so an agent that writes through its client is checked and the file is written only if the check passes; an agent that writes files with its own shell or editor tools is not intercepted. Muse and Antigravity write files themselves: for them ModStage still detects the change afterwards and flags both runs, it does not block it. Claude's own edits are blocked by the hook at a file another agent holds.
- **Identity comes from the run, not from arguments.** Each run's tools carry a token issued by the bridge; an agent cannot act as another run, and the install token cannot act as a run on the board.
- **Messages expire after 24 hours** and are capped at 8 KB.

Everything lives in `<folder>/.modstage/` (SQLite `board.db` plus `STATE.md`). The folder ignores itself in git.

## Optional: SuperLocalMemory mesh

If you run [SuperLocalMemory](https://github.com/qualixar/superlocalmemory), ModStage also mirrors the shared part of the board to SLM-mesh: each run appears as a mesh peer (`modstage-<run>`, engine and run id only) and exclusive claims become mesh locks, so Claude Code windows and bots that use SLM-mesh see which files are held. Messages and prompt text are never mirrored, since the mesh is machine-wide and messages belong to one session. The local board stays the source of truth; if SLM is slow or down, nothing waits on it, and the mirror reconnects every 5 minutes. Set `MODSTAGE_SLM_MESH=0` to turn the mirror off.

## What was verified

On 16 Oct 2026, with Codex (app-server) and Grok (ACP) in one folder: both connected their ModStage tools; Codex claimed `calc.py` and broadcast a handoff; Grok joined, read the handoff, was denied `calc.py` ("held by codex"), claimed `test_calc.py`, wrote and ran the tests, released its claim and posted done. A separate Codex run appeared on SLM-mesh as `modstage-<run>` within seconds.

Known limits: Kimi's MCP tools did not connect in that test (it ran prompt-only), Antigravity has no MCP injection and uses the CLI and digests, and an ACP agent may accept the tools but never call them: the brief, the digests and the approval-time claim checks still apply.
