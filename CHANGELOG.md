# Changelog

All notable changes to ModStage are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions may change behaviour; the release notes say when.

## 0.0.13 - 2026-10-18

### Fixed

- **The black gap between the run's card and the tabs.** The animated head was given a fixed 16 rows while its content used about 12. It now takes the height of what it draws; nothing in it depends on the room it is given, which is what made the old stage unmount.

### Added

- **Every agent now shows what it did in full, not a short cut of it.** Edits show the change as a diff (Codex, Grok, Kimi, Qwen Code, OpenCode, Muse, Antigravity and Claude subagents); a command is shown whole (it was cut at 160 to 200 characters); a tool call's other arguments are listed; command and tool output reaches the panel up to 4,000 characters (it was cut at 1,500); Codex MCP and dynamic tool results are recorded, which they were not before; reasoning shows up to 3,000 characters (was 1,200).
- **Claude reads the same detail.** `stage_status` and `stage_wait` summarise each step by what came of it (`edited a.py (+3 -1)`, a result's last line), and take `detail: true` to include the full detail of each step, fenced as the agent's own words.
- Two new rows in the parity matrix (tool input and output in full; edits show what changed), checked for every agent against its own protocol shapes. The diff fields of Codex and the ACP agents follow each protocol as documented and are marked as not yet confirmed against the real CLIs.

### Known limits

- A Codex command's output appears when the command ends, not while it runs.

## 0.0.12 - 2026-10-18

### Fixed

- **0.0.11 squeezed the panel to a few rows you could not scroll.** The stage was given a fixed height worked out from an estimate of the pane's size; in a pane where that estimate came out small, the run's card was cut off and the transcript was gone. The stage no longer has a computed height at all: the card and the transcript take the room they need and the whole pane scrolls.

### Added

- **The run's transcript scrolls like a terminal.** It is drawn in the pane body, so the mouse wheel, arrow keys and Page Up/Down move through it. Messages wrap in full (they were cut at 400 characters), a tool call's result expands to its whole output and an edit to its diff (`▸ N lines` / `▾ collapse`), and `↑ N earlier events` pages back through the run's history (up to 1,000 events kept in the panel). New output is followed while you are at the bottom and stops following when you scroll up; scroll back to the end to follow again.
- Only the animated title bar and robot card stay in the animated region, at a fixed size; everything you read is ordinary pane content.

## 0.0.11 - 2026-10-18

### Fixed

- **Approvals can no longer push the stage past the engine's size limit.** The stage received every run whole, including each waiting approval's full detail (up to 4,000 characters) and file lists; a few approvals across several agents passed the 100,000-character limit and the engine refused to draw the pane. The stage now receives only what it draws, capped.
- **The animated stage no longer vanishes when an approval arrives.** Its height followed its own measured region, so the approval card above it shrank the region, which shrank the content, until the engine unmounted it ("changed its own size after each of 3 draws") and the panel showed a hole until it was reopened. The pane now gives the stage a fixed height computed from its own size and the cards around it, and if the engine ever unmounts the stage anyway, the pane draws it from the plugin and says why.
- **The start panel no longer stacks the "not installed" buttons flush under the installed ones.** Installed and missing agents now share one wrapping row, so the gaps between buttons are the same everywhere.

## 0.0.10 - 2026-10-18

### Fixed

- **One message can no longer approve two actions.** Two `stage_decide` calls made at the same time both saw the user's message as unused and each sent a decision. The message is now reserved in one step before anything is sent, so exactly one call goes through. If the send fails, the message is given back only while it is still the one that was spent. Found in review of the awesome-list submission (karanb192/awesome-claude-code-mods#309); new tests cover two approvals at once and a retry after a failed send.
- **The Bash guard no longer reads a quoted `|` as a pipe, and lets `command -v` through.** `grep -E "muse|grok"` and `command -v grok` were refused as if they started an agent. Real launches after `&&`, `;` or a real pipe are still refused.

### Added

- **A missing agent CLI tells you how to install it.** The start panel now shows every agent as a button; one that is not installed answers the click with the install line instead of doing nothing. The setup list, `stage_agents` and the "not installed" error carry the same line. Each install URL or package was checked live before it went in: Codex, Qwen Code and OpenCode by npm package, Muse, Grok and Antigravity by installer script, Kimi by its project page.

## 0.0.9 - 2026-10-17

### Fixed

- **`stage_board` names this session's own board peer.** Registering a session now returns its peer id alongside the key, so Claude sees "you are claude-<id>" instead of a placeholder.
- **The bridge guard no longer blocks text that only mentions the bridge.** Heredoc bodies (text being written to a file) and header names on their own are not bridge calls, so writing or searching ModStage's own code works again. Reading the token file and calling the bridge port from Bash are still refused.

## 0.0.8 - 2026-10-17

A full session-isolation audit, run as two independent reviews plus live attacks against a test bridge, found that a ModStage agent could act as its own parent and that one session's agents could reach another's. Every finding, from critical to low, is fixed here. `scripts/isolation-gate.py` now runs all 37 attacks against a real bridge before each release.

### Security

- **Runs belong to a session secret, not a session id (critical).** An agent runs as you, so it could read `~/.modstage/token`, learn its parent's session id from its own run summary, and approve its own permission request. The bridge now issues each Claude Code session a random secret (`POST /sessions`). The mod holds it in host memory, never on disk, and sends it as `X-ModStage-Session`. Runs, approvals, the inbox and Claude's board seat belong to the secret's hash. Re-registering a known session id gives a new, empty scope. Run summaries no longer carry the owner.
- **No "see every run" over HTTP (critical).** A caller that named no session (an old mod copy, or anyone holding the install token) used to see and control every run. Now every `/runs`, `/inbox` and `/claude/*` call needs a registered session; the install token alone reaches nothing. Another session's run answers 404, the same as a run that does not exist.
- **Agents can no longer message or wake another session's agents (high).** Board messages, `all`, wakes, handoffs and digests reach only the sender's own session's runs and its Claude peer. A message to another session's run is refused.
- **The board keeps each session's words to itself (high).** Every session in a folder still shares the roster and the claims, so agents never write over each other. Messages, threads, what an agent says it is doing, and log lines that quote them are visible only to their own session. `STATE.md` holds only the shared part, and the route that dumped every board is gone. Existing `board.db` files are migrated in place.
- **Ownerless runs belong to no one (medium).** They used to be drivable by any session that knew their id.
- **The install token cannot act as a run on the board (medium).** Only the run's own token can.
- **Nothing private goes to the SLM mesh (medium).** Only peers (engine and run id) and file locks are mirrored; messages and prompt text no longer are.
- **The decide gate needs a stated decision (medium).** Any message used to open it ("what time is it?" passed an `allow_session` on `curl … | sh`). Now the user's latest message must state that decision (allow, allow for the rest of the run, or deny), and one message answers one approval. The prompt's text is no longer kept in `$.state`, only the decision it states.
- **`/clear` no longer orphans runs (medium).** The session's secret stays with the process, so its agents stay attached. The old conversation's Claude subagent tabs, feed and stale hook-envelope id are cleared.
- **Claude peer ids use 16 hex characters of the scope (low).** They used 8 characters of the session id, and two sessions sharing a prefix shared an inbox.
- **No counts of other sessions' runs (low).** They are gone from listings, the panel and `stage_status`, and `/health` reports no run count.
- **The Bash guard covers every engine and wrapper (low).** It tokenizes the command and peels off `env`, `sudo`, `timeout`, `nice`, `xargs`, `npx`/`bunx`, `sh -c` and backticks. It now covers all seven CLIs (Codex, Muse, Grok, Antigravity, Kimi, Qwen Code, OpenCode). Help, version and housekeeping commands still pass, and heredoc text is no longer mistaken for a command. Bash and Read access to the bridge's token and port is refused.
- **One board per real folder (low).** `/tmp` and `/private/tmp`, or a linked folder, now share leases.
- **An empty session id fails closed.** When `$.session.id()` gives nothing, the mod uses the `session_id` from the classic hook envelope. With neither, it refuses to start a run rather than leave it ownerless.

### Fixed

- Stale per-session development copies of the mod (`~/.claude/dev-mods/<session>/modstage`) shadowed the installed plugin in some sessions and sent no session id. They are removed. If a session still shows other sessions' runs, start a new session.

Tests: the bridge suite and `claude plugin test .` cover every item above, and `python3 scripts/isolation-gate.py` checks them live (37/37).

## 0.0.7 - 2026-10-17

### Fixed

- **Muse runs start again.** Muse 1.4.10 refuses to start when its MCP setting references an environment variable it was not given ("secret leaves need exactly one whole-value `${VAR}` naming a set variable"). Since 0.0.3 the ModStage tools setting referenced `${PYTHONPATH}` and `${PYTHONSAFEPATH}`, which ModStage deliberately keeps out of agent environments, so every Muse run failed at start with "muse serve exited with code 2". The setting now references only the `MODSTAGE_*` variables Muse is given; the tool server keeps its shadowing protection through the safe launcher plus Python's `-P` (3.11+).
- **A failed Muse start says why.** The run log now carries Muse's last error lines after "muse serve exited with code N".

Tests: `bridge/tests/test_muse_args.py` (every reference names a variable Muse is given; a live `muse serve` accepts the setting).

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
