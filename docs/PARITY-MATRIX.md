# ModStage parity matrix

Generated 2026-10-18 by `python3 bridge/tests/parity_matrix.py` from the conformance harness (`bridge/tests/conformance.py`, protocol fakes, zero tokens). Every bridge cell was produced by running its check; a gap is an expected failure, so fixing one fails the suite until the table is updated. The Claude row is read from `hooks/register.tsx`, not run through the fakes.

What the fakes prove: ModStage sends and reads each CLI's protocol messages correctly, as we understand the protocol. What they do not prove: that the real CLI still speaks that protocol. That is the job of `scripts/smoke-real-cli.sh` (manual, one agent at a time, tiny prompts).

✅ works · 🟡 degraded (works within a limit the CLI sets; the note says which) · ❌ gap (a defect we own) · ➖ n/a (the CLI has no such channel; ModStage must say so)

| Agent | 1 Start | 1b Pick a model | 1c Pick a thinking effort | 2 Stream text + tools | 2b Long turn looks alive | 2c Tool input and output in full | 2d Edits show what changed | 3 Approval round trip | 4 Steer mid-turn | 4b Queued-message feedback | 5 Interrupt | 6 Resume after exit | 7 Close | 8 Images |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude | ✅ works [1] | ✅ works [2] | ➖ n/a [3] | 🟡 degraded [4] | 🟡 degraded [5] | 🟡 degraded [6] | 🟡 degraded [7] | 🟡 degraded [8] | ✅ works [9] | ➖ n/a [10] | ➖ n/a [11] | ✅ works [12] | 🟡 degraded [13] | ➖ n/a [14] |
| Codex | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | 🟡 degraded [15] | ✅ works | ✅ works | ➖ n/a [16] | ✅ works | 🟡 degraded [17] | ✅ works | ✅ works |
| Muse | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | 🟡 degraded [18] | ✅ works | ✅ works | ➖ n/a [19] | ✅ works | 🟡 degraded [20] | ✅ works | ✅ works |
| Grok | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | ✅ works | 🟡 degraded [21] | 🟡 degraded [22] | 🟡 degraded [23] | ✅ works | ✅ works | 🟡 degraded [24] | ✅ works | ➖ n/a [25] |
| Antigravity | ✅ works | ✅ works | ➖ n/a [26] | ✅ works | 🟡 degraded [27] | ✅ works | 🟡 degraded [28] | ➖ n/a [29] | 🟡 degraded [30] | 🟡 degraded [31] | 🟡 degraded [32] | 🟡 degraded [33] | ✅ works | ➖ n/a [34] |
| Kimi | ✅ works | ✅ works | 🟡 degraded [35] | ✅ works | ✅ works | ✅ works | 🟡 degraded [36] | ✅ works | 🟡 degraded [37] | ✅ works | ✅ works | 🟡 degraded [38] | ✅ works | ✅ works |
| Qwen Code | ✅ works | ✅ works | 🟡 degraded [39] | ✅ works | ✅ works | ✅ works | 🟡 degraded [40] | ✅ works | 🟡 degraded [41] | ✅ works | ✅ works | 🟡 degraded [42] | ✅ works | ✅ works |
| OpenCode | ✅ works | 🟡 degraded [43] | ➖ n/a [44] | ✅ works | ✅ works | ✅ works | 🟡 degraded [45] | ✅ works | 🟡 degraded [46] | ✅ works | ✅ works | 🟡 degraded [47] | ✅ works | ✅ works |

## Checked once for every agent

| Control | State | Where |
|---|---|---|
| Needs-you card in view on a new approval; band jumps to it | ✅ works | A: tests/panel.test.tsx (the scroll itself is not run by the test kit: see Notes) |
| Answer an approval from Claude chat (stage_decide) | ✅ works | B: tests/decide.test.ts |
| Each Claude session sees and answers only the runs it started; the board stays per folder | ✅ works | bridge/tests/test_session_scope.py, tests/decide.test.ts |
| Free text refused while an approval is pending (bridge 409 + message box) | ✅ works | C3: bridge/tests/conformance.py, tests/panel.test.tsx |
| stage_wait says waiting_on_user; until=turn_end keeps waiting while the user decides | ✅ works | C5 |
| A turn where the CLI reports nothing is flagged, not shown as a clean finish (ACP agents) | ✅ works | seen live: Kimi on a model its provider no longer serves |
| A model the CLI's flag ignores (Kimi ACP) is set through ACP, and the panel names the real model | ✅ works | seen live: kimi -m X acp started on its default model |
| 'Interrupt and send now' survives an agent that answers a cancel with an error (Kimi) | ✅ works | seen live on Kimi 16 Oct: session/prompt Internal error after cancel |
| Claude is a peer on the board: reads it, posts, claims; agents' messages reach it without starting a turn | ✅ works | Phase 3 P1: bridge/tests/test_claude_peer.py, tests/board-peer.test.ts |
| Claude's own Edit/Write is stopped on a file an agent holds (fails open without a bridge) | ✅ works | Phase 3 P1: tests/board-peer.test.ts |
| Grok's auto-approve config is shown before Start | ✅ works | bridge/tests/conformance.py |

## Notes

1. **Claude · 1 Start**: $.agent.spawn from the launcher or the Agent tool; tests/panel.test.tsx draws it
2. **Claude · 1b Pick a model**: haiku / sonnet / opus / any id, passed to $.agent.spawn
3. **Claude · 1c Pick a thinking effort**: a Claude subagent's thinking is set by Claude Code itself; ModStage picks only its model
4. **Claude · 2 Stream text + tools**: tool calls and the final message via hooks; no partial text stream
5. **Claude · 2b Long turn looks alive**: the tab shows the current tool; no thinking stream
6. **Claude · 2c Tool input and output in full**: the tool.call hook records each tool's whole input and result (helpers tested in tests/claude-detail.test.ts); the test kit cannot raise a subagent's tool call (the engine sets agentId), so confirm in a live subagent tab
7. **Claude · 2d Edits show what changed**: Edit, MultiEdit and Write inputs become a -/+ diff on an edit row (helpers tested); same live-confirmation caveat as above
8. **Claude · 3 Approval round trip**: Claude Code's own permission prompts apply, not the Needs-you inbox
9. **Claude · 4 Steer mid-turn**: SendMessage to the subagent ($.session.send)
10. **Claude · 4b Queued-message feedback**: messages reach the subagent after its current step
11. **Claude · 5 Interrupt**: Claude stops its own subagents; the tab offers no interrupt
12. **Claude · 6 Resume after exit**: SendMessage continues a finished subagent
13. **Claude · 7 Close**: closing the tab stops showing it; the subagent is Claude's to stop
14. **Claude · 8 Images**: the Agent tool takes text; Claude passes files by path
15. **Codex · 2d Edits show what changed**: each change's `diff` field from the app-server's fileChange item; the field name is the protocol's as documented, not yet confirmed against the real CLI (run scripts/smoke_real_cli.py)
16. **Codex · 4b Queued-message feedback**: steers natively; nothing queues
17. **Codex · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
18. **Muse · 2d Edits show what changed**: built from the edit tool's own arguments (replace old/new text, or the whole new file); an edit tool with another argument shape shows the file name only
19. **Muse · 4b Queued-message feedback**: steers natively; nothing queues
20. **Muse · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
21. **Grok · 2d Edits show what changed**: the diff comes from the ACP `diff` block the CLI sends (old and new text); not yet confirmed against each real CLI (run scripts/smoke_real_cli.py)
22. **Grok · 3 Approval round trip**: the round trip works, but Grok's own config (permission_mode = always-approve) means it never asks; the launcher says so before Start
23. **Grok · 4 Steer mid-turn**: CLI has no mid-turn input; the message queues until the turn ends
24. **Grok · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
25. **Grok · 8 Images**: Grok's ACP initialize says promptCapabilities.image = false: ModStage refuses with that reason
26. **Antigravity · 1c Pick a thinking effort**: agy carries its effort in the model name (Gemini 3.8 Flash High, Medium, Low): pick that model; ModStage refuses an effort for it and says so
27. **Antigravity · 2b Long turn looks alive**: agy streams no thinking text, only step events: the panel shows 'thinking' and stays fresh, but cannot show what it is thinking
28. **Antigravity · 2d Edits show what changed**: built from the edit tool's own parameters (target/replacement content, or the whole new file); a tool with another parameter shape shows the file name only
29. **Antigravity · 3 Approval round trip**: headless agy cannot ask (it refuses and reports denied_actions). Ask runs are read-only through a per-run agy project (web reads, web search, files in cwd); ModStage shows each refusal, marks the run blocked with the way out (autonomy auto), and says so before Start
30. **Antigravity · 4 Steer mid-turn**: CLI has no mid-turn input; the message queues until the turn ends
31. **Antigravity · 4b Queued-message feedback**: 'Interrupt and send now' restarts agy (it has no cancel) with a recap plus the queued message
32. **Antigravity · 5 Interrupt**: agy has no cancel: ModStage stops the process; the next message restarts it with a recap
33. **Antigravity · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
34. **Antigravity · 8 Images**: agy's print mode takes text only (no verified image input): ModStage refuses with a reason
35. **Kimi · 1c Pick a thinking effort**: set through ACP when the CLI advertises a thought-level setting; it warns and runs on its own default when it does not. Not yet confirmed which of these CLIs advertise one
36. **Kimi · 2d Edits show what changed**: the diff comes from the ACP `diff` block the CLI sends (old and new text); not yet confirmed against each real CLI (run scripts/smoke_real_cli.py)
37. **Kimi · 4 Steer mid-turn**: CLI has no mid-turn input; the message queues until the turn ends
38. **Kimi · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
39. **Qwen Code · 1c Pick a thinking effort**: set through ACP when the CLI advertises a thought-level setting; it warns and runs on its own default when it does not. Not yet confirmed which of these CLIs advertise one
40. **Qwen Code · 2d Edits show what changed**: the diff comes from the ACP `diff` block the CLI sends (old and new text); not yet confirmed against each real CLI (run scripts/smoke_real_cli.py)
41. **Qwen Code · 4 Steer mid-turn**: CLI has no mid-turn input; the message queues until the turn ends
42. **Qwen Code · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume
43. **OpenCode · 1b Pick a model**: `opencode acp` has no model flag: ModStage sets ACP's `model` config option after session/new (verified live: session/set_config_option switched it)
44. **OpenCode · 1c Pick a thinking effort**: `opencode acp` advertises only `model` and `mode` (checked live): there is no effort setting to apply. ModStage offers none; an effort asked for anyway is refused. Its models do list `variants` for `opencode run`
45. **OpenCode · 2d Edits show what changed**: the diff comes from the ACP `diff` block the CLI sends (old and new text); not yet confirmed against each real CLI (run scripts/smoke_real_cli.py)
46. **OpenCode · 4 Steer mid-turn**: CLI has no mid-turn input; the message queues until the turn ends
47. **OpenCode · 6 Resume after exit**: restarts a fresh process with a recap of the run, not the CLI's own session resume

## What the tests cannot show

- The test kit has no implementation of `$.ui.scroll`, so no test moves a real pane. Tests prove that a new approval reaches the code that asks the pane to scroll to the `inbox` key, and the arguments it asks with. Whether the desktop app then shows the card is checked only by looking at the real panel.
- Images: the fakes prove each protocol's shape (Codex localImage path, Muse image part with base64Data, ACP image block) and the per-agent capability as each CLI's own initialize reported it on 16 Oct 2026. No real CLI has yet been handed an image through ModStage.
- Queued messages: for ACP agents 'Interrupt and send now' sends session/cancel and the queued prompt runs next; the fakes show the cancel and the count, not that every ACP CLI starts the queued prompt after a cancel.
- Long turns: Antigravity's stream carries step events but no thinking text. What agy did during the ~6 quiet minutes of one demo run is still unknown; the panel now shows 'no new output for Nm, still running' instead of looking frozen.
- Resume: Grok, Kimi, Qwen Code and OpenCode advertise ACP loadSession, so a native resume is possible; ModStage still restarts with a recap. That is listed as degraded, not built.
- Claude Code's own approvals for its subagents are outside ModStage: Claude Code asks for those itself.

## Live checks with real CLIs (October 2026)

Run against an installed build with tiny prompts, one agent at a time (`scripts/smoke_real_cli.py` does the same):

- Codex network approval: the card is raised and `stage_wait` reports `waiting_on_user`; a typed "yes" is refused (409); another Claude session cannot answer it (403); an invalid choice is refused (400); a decision passed from Claude chat is logged as "decided by the user in Claude chat".
- In the desktop panel: the band's "needs you" button opens the panel with the card at the top, and each Claude session lists only the runs it started.
- Codex takes a PNG through `images` and describes it.
- Antigravity in ask mode ends a turn that needed a command as `blocked: refused …`, with the refusal in the feed.
- Muse lists its models through `model/list`; OpenCode switches model through its ACP config option.
- Kimi: a message sent mid-turn shows "1 queued"; "Interrupt and send now" ends the turn and the held message runs next. This needed three fixes found live: `kimi -m X acp` ignores the flag (ModStage now sets the model through ACP), Kimi rejects a second prompt while one runs (ModStage now holds queued messages), and Kimi answers a cancel with an error (ModStage treats it as the interrupt).
- A CLI that ends a turn without reporting anything (for example on a model its provider no longer serves) is flagged as an empty turn instead of a clean finish.
- Not seen on screen yet: the message box refusing free text while a card waits (covered by the bridge's 409 and tests/panel.test.tsx).
- A Claude Code session that loaded an older ModStage keeps that version's tool schemas; start a new session after updating.

## Why some rows read the way they do

- **Antigravity approvals are n/a**: probed on agy 1.4.0 in stream-json print mode without the skip-permissions flag. A command that needs permission is auto-denied, the turn ends with `result.denied_actions`, and stderr says headless mode cannot prompt. There is no stream-json input that answers a permission, so ModStage shows the refusal and says so before Start. Ask runs are made read-only rather than dead ends: each one gets a ModStage-owned agy project (`~/.gemini/config/projects/modstage-*.json`, removed when the run ends) that allows `read_url(*)` and `read_file(<cwd>)` and keeps `write_file(<cwd>)` and `command(*)` at ask, so web research and reading its folder work and writes, commands and files outside its folder are refused (probed 17 Oct 2026).
- **Approvals time out after 10 minutes**: an unanswered card is denied with the reason "no answer in time". Typing "yes" in the message box is not an answer, which is why the box refuses text while a card waits.
