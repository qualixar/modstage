# Changelog

All notable changes to ModStage are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions may change behaviour; the release notes say when.

## 0.0.6 - 2026-10-17

### Fixed

- **Agent model lists stay current.** The bridge outlives Claude Code sessions, so a list fetched when it started went stale when an agent's plan or catalog changed (a Muse subscription switch showed old models and the wrong default). Now every Claude Code session start asks every installed agent CLI (Codex, Muse, Grok, Antigravity, Kimi, Qwen Code, OpenCode) for its models again, and a list older than 10 minutes is fetched again in the background whenever it is read. Readers keep the old list until the new one arrives.
- **The agent's own config names the default.** Where the CLI's config sets a model (Codex, Muse, Antigravity, Kimi, Qwen Code, OpenCode), that is the default shown, ahead of the catalog's own pick. Antigravity's display label is matched to its model id.

### Added

- **`stage_start` checks the model.** A model id the agent does not list is refused with the ids it does offer; on a miss the bridge asks the CLI once more first, so a model added since the last fetch still starts. Agents that list no models (Qwen Code) take any id as before. Long lists are checked whole; only the listing shown is capped at 16.
- **Muse contributor ids fold into their model.** When Muse lists a model twice (plain and `-contributor`, the same model with your content usable for product improvement), ModStage shows it once and names the contributor id beside it; both ids start.

Tests: `bridge/tests/test_model_refresh.py`, `tests/models-refresh.test.ts`.

## 0.0.5 - 2026-10-17

### Added

- **Stale writes are rejected at the write.** The bridge checks a run's fence on every write it can intercept: Codex file changes (autonomous Codex runs now use approval policy `untrusted` so each edit comes through the bridge) and ACP `fs/write_text_file`, which ModStage now serves for Grok, Kimi, Qwen Code and OpenCode (`fs/read_text_file` too, both limited to the run's folder). A run whose lease lapsed and was taken over by another run is refused even if it was allowed to edit earlier; both runs get a conflict line. "Allow for this run" on a file edit is no longer carried forward for Codex, so each edit is checked. Muse and Antigravity are unchanged: they write files themselves, so conflicts are still detected afterwards. Test: `bridge/tests/test_write_fence.py`.

## 0.0.4 - 2026-10-17

### Security

- **`stage_decide` now needs the user to have spoken, enforced by code.** The mod records when you last submitted a message (only your own prompt counts: not a peer session, a plugin, a schedule or a task notification) and refuses to answer an approval unless you sent one after that approval was raised. Agent output, `stage_wait` results and file contents cannot satisfy the check; the refusal tells Claude to ask you to confirm in your own message. The ModStage panel is unaffected. The check proves you sent a message after the request, not what it said.

### Fixed

- **`PYTHONPATH` and `PYTHONSAFEPATH` no longer leak into the agent process environment.**

## 0.0.3 - 2026-10-17

### Fixed

- **The band above the message box now matches the panel.** It showed only the newest five runs, so earlier Codex and Muse runs vanished from it, and it marked ended runs ✓ like runs waiting for Claude. Both now use one set of marks (✓ waiting, ○ ended, ✗ failed, ◼ interrupted, ✻ working); the band lists working runs first, then waiting, failed and ended ones, and says "+N more" when some do not fit.
- **The panel header shows who is actually running.** It always read "codex · muse · grok", whatever ran. It now shows one dot per agent that has runs, in that agent's colour with a count: the dot pulses while one of its runs works, and turns ○ when all of its runs have ended. The empty-panel hint and the `/modstage` description no longer name only three agents, and the panel knows all eight agents' colours.

## 0.0.2 - 2026-10-17

### Fixed

- **Antigravity research in ask mode no longer stops at the first web read.** Headless agy cannot ask, and since agy began asking before every URL read, an ask run refused `read_url_content` and ended blocked. Each ask run now gets a ModStage-owned, read-only agy project (removed when the run ends): web pages, web search and files in its folder are allowed; writes, shell commands and files outside its folder are refused. A refusal names the refused step and says to restart with autonomy `auto`, ideally in an isolated folder, in `stage_wait`, `stage_status`, the run card and the message box. `stage_start` and `stage_agents` explain this before a run starts.

## 0.0.1 - 2026-10-17

First public release.

### Added

- **Eight agents in one Claude Code panel:** Codex (`app-server`), Muse (`serve`), Grok, Kimi, Qwen Code and OpenCode (Agent Client Protocol), Antigravity (stream-json print mode), and Claude Code's own subagents. Live tool calls, edits, messages and thinking per run, with tokens, context and cost where the CLI reports them.
- **Steering:** messages join a running turn on Codex and Muse; for the other agents a message is held and shown as queued, and **Interrupt and send now** ends the turn so it runs at once.
- **Needs-you inbox:** agents' permission requests wait for Allow, Allow for this run or Deny; the card scrolls into view on arrival, the band's "needs you" button jumps to it, and no answer in 10 minutes is a deny. The message box refuses free text while an approval waits.
- **Claude Code tools:** `stage_start`, `stage_wait` (reports `waiting_on_user`, can wait through approvals), `stage_send` (with images and `now`), `stage_decide` (answer an approval only on the user's own words), `stage_status`, `stage_agents`, `stage_interrupt`, `stage_close`.
- **Per-session runs:** each Claude Code session sees and controls only the runs it started.
- **Coordination board per folder:** file claims as leases with denied conflicts, messages between agents framed as information, `STATE.md`, `modstage-cli`, and an optional mirror to SuperLocalMemory's local mesh.
- **Claude as a board peer:** `stage_board`, `stage_post`, `stage_claim`, `stage_release`; agents can message Claude, and Claude's own Edit and Write stop at files an agent has claimed.
- **Model pickers** from each CLI's own list, including Muse (`model/list`), Kimi (its configured aliases) and OpenCode (ACP config option); a model a CLI's flag ignores is set through ACP.
- **Images** for Codex, Muse, Kimi, Qwen Code and OpenCode; Grok and Antigravity refuse with a reason.
- **Honest states:** Antigravity's headless refusals are shown and the run marked blocked; a turn where a CLI reports nothing is flagged; long quiet turns show "still running".
- **Conformance harness** (`bridge/tests/`) driving every adapter through protocol fakes, and `docs/PARITY-MATRIX.md` generated from it; `scripts/smoke_real_cli.py` for real CLIs.

### Security

- Localhost-only bridge with a per-install token (0600, in a 0700 folder) checked before any request body is read; bodies capped; socket timeouts.
- Python started inside an agent's folder never imports from that folder; board files refuse symlinks and are written without following links.
- Agent-written text is flattened or fenced before Claude reads it. See [SECURITY.md](SECURITY.md).
