# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button on the repository's Security tab (private vulnerability reporting), not in a public issue. Include the version, what an attacker controls, and what they gain.

## The model in one paragraph

ModStage runs coding agents as you, on your machine, as subagents of the Claude Code session that started them. Its job is to make what they do visible, route their own permission requests to you, and keep each session's agents its own. It is not a sandbox. The bridge listens on `127.0.0.1` only. Three credentials, each with its own reach:

- **The install token** (`~/.modstage/token`, mode 0600 in a 0700 folder) says the caller is a program on this machine. It is needed for every request except `/health`, and on its own it reaches no session's runs. Agents run as you and can read it; that is expected.
- **A session secret** is what makes a run yours. The mod registers when a Claude Code session starts (`POST /sessions`) and gets a random secret, held in Claude Code's memory and never written to disk, then sends it with every call (`X-ModStage-Session`). Runs, approvals, the inbox and Claude's seat on the board belong to the secret's hash, not to the session id. Registering a known session id again yields a new, empty scope.
- **A run token** is given to each agent in its own environment. It works only on the coordination board, as that run: it cannot list runs, message or close a run, answer an approval, or register a session.

`scripts/isolation-gate.py` tries every cross-session and agent-to-parent attack against a real bridge; it must pass before a release.

## What ModStage defends against

- **Web pages in your browser.** No CORS headers are sent, every useful route needs a custom token header (which forces a preflight that fails), and the token is checked before a request body is read. Bodies are capped and sockets time out.
- **A repository you point an agent at.** Python that ModStage starts inside that folder (the agents' coordination tools, `modstage-cli`) never puts the folder on its import path, so a planted `json.py` cannot run. Board files under `<folder>/.modstage/` refuse symlinks and are written without following links, so an agent cannot aim them at your dotfiles. Agent-written text cannot add lines to `STATE.md`.
- **Agent text reaching Claude.** Approval titles, run activity, errors and board messages are flattened to one line, and an agent's own answer is fenced, before Claude reads them, so agent output cannot pose as ModStage's "waiting on the user" lines. Board messages are labelled as information from agents, never instructions or approvals.
- **One Claude Code session reaching another's agents.** A session sees, steers and approves only runs it owns. Another session's run answers 404, exactly like a run that never existed, and no listing counts other sessions' runs.
- **An agent posing as its parent.** Reading `~/.modstage/token` and learning the session id gets an agent nowhere: run summaries carry no owner, and ownership needs the session secret, which never touches disk. An agent cannot approve its own request this way.
- **Agents of different sessions in one folder.** They share what keeps files safe: the roster and the claims, so neither writes over the other. Messages, wakes, what an agent says it is doing, and the log lines that quote them stay inside their own session. An agent cannot message or wake another session's agent, and `STATE.md`, which any agent can read, holds no message or prompt text.
- **Silent or stretched approvals.** No answer within 10 minutes is a deny. A message typed while an approval waits is refused, never read as "yes". Claude can pass on an approval only when your latest message states that decision; one message answers one approval, and "allow it" does not mean "for the rest of the run".

## What it cannot defend against

- **Agents run as you.** Any agent process can read what you can read. With the install token it can register a session of its own and start runs there; those do not appear in your sessions' panels. It cannot reach your sessions' runs without their secrets, which exist only in Claude Code's memory, so taking one needs access to the Claude Code process itself rather than to a file. Ask mode and the Needs-you inbox control agents that ask; they are not a boundary against one that never asks. Use a git worktree or a disposable folder for work you do not trust.
- **Agents' own settings win.** If an agent's configuration approves everything (for example Grok's `permission_mode = "always-approve"`), it never asks. ModStage says so before Start.
- **Environment.** Agent CLIs inherit your environment, including provider keys they need to work.
- **Board files are advisory.** The bridge is the only intended writer of `<folder>/.modstage/board.db`, but an agent that can write the folder can edit it. Claims coordinate cooperative agents; they do not stop a determined one.
- **Guards are conveniences.** Blocking agent CLI launches and the bridge's token and port in Claude's Bash, and stopping Claude's Edit and Write on claimed files, make the safe path the easy one. Neither is a security boundary: an edit made with `sed -i` in Bash is not checked against claims, for example.
- **Auto mode answers for you.** Start runs in auto mode only for work you would approve anyway. Claude is told to choose auto, and to answer approvals with `stage_decide`, only when you said so in your own words.

## Data ModStage keeps

Run logs in `~/.modstage/runs/` hold what the agents saw and did, including file contents and command output. They stay on your machine and are not rotated; delete them when you no longer need them. If SuperLocalMemory is installed and running, run peers (engine and run id) and file claims are mirrored to its local mesh; messages and prompt text are not (set `MODSTAGE_SLM_MESH=0` to turn it off). Nothing leaves `127.0.0.1`.
