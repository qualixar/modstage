# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's **Report a vulnerability** button on the repository's Security tab (private vulnerability reporting), not in a public issue. Include the version, what an attacker controls, and what they gain.

## The model in one paragraph

ModStage runs coding agents as you, on your machine. Its job is to make what they do visible and to route their own permission requests to you. It is not a sandbox. The bridge listens on `127.0.0.1` only and refuses every request (except `/health`) that lacks the per-install token in `~/.modstage/token` (created with mode 0600 in a 0700 folder). Each run gets its own board token that can only use the coordination board, never approve, message or close runs.

## What ModStage defends against

- **Web pages in your browser.** No CORS headers are sent, every useful route needs a custom token header (which forces a preflight that fails), and the token is checked before a request body is read. Bodies are capped and sockets time out.
- **A repository you point an agent at.** Python that ModStage starts inside that folder (the agents' coordination tools, `modstage-cli`) never puts the folder on its import path, so a planted `json.py` cannot run. Board files under `<folder>/.modstage/` refuse symlinks and are written without following links, so an agent cannot aim them at your dotfiles. Agent-written text cannot add lines to `STATE.md`.
- **Agent text reaching Claude.** Approval titles, run activity, errors and board messages are flattened to one line, and an agent's own answer is fenced, before Claude reads them, so agent output cannot pose as ModStage's "waiting on the user" lines. Board messages are labelled as information from agents, never instructions or approvals.
- **One Claude Code session acting on another's runs.** Every run belongs to the session that started it; other sessions get 403, and an approval is answered only with the owning session named.
- **Silent approvals.** No answer within 10 minutes is a deny. A message typed while an approval waits is refused, never read as "yes".

## What it cannot defend against

- **Agents run as you.** Any agent process can read what you can read, including `~/.modstage/token`. A hostile agent can therefore call the bridge with your token. Ask mode and the Needs-you inbox are a control for well-behaved agents that ask, not a boundary against a malicious one. Use a git worktree or a disposable folder for work you do not trust.
- **Agents' own settings win.** If an agent's configuration approves everything (for example Grok's `permission_mode = "always-approve"`), it never asks. ModStage says so before Start.
- **Environment.** Agent CLIs inherit your environment, including provider keys they need to work.
- **Board files are advisory.** The bridge is the only intended writer of `<folder>/.modstage/board.db`, but an agent that can write the folder can edit it. Claims coordinate cooperative agents; they do not stop a determined one.
- **Guards are conveniences.** Blocking `codex exec` in Bash and stopping Claude's edits on claimed files make the safe path the easy one; neither is a security boundary.
- **Auto mode answers for you.** Start runs in auto mode only for work you would approve anyway. Claude is told to choose auto, and to answer approvals with `stage_decide`, only when you said so in your own words.

## Data ModStage keeps

Run logs in `~/.modstage/runs/` hold what the agents saw and did, including file contents and command output. They stay on your machine and are not rotated; delete them when you no longer need them. If SuperLocalMemory is installed and running, run peers, file claims and board messages are mirrored to its local mesh (set `MODSTAGE_SLM_MESH=0` to turn that off). Nothing leaves `127.0.0.1`.
