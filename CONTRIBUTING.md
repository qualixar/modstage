# Contributing to ModStage

Thanks for helping. Issues and pull requests are welcome, especially new agents, protocol fixes and reports of a CLI that behaves differently from what [docs/PARITY-MATRIX.md](docs/PARITY-MATRIX.md) says.

## Before you open a pull request

```bash
claude plugin validate .
claude plugin test .
python3 -m unittest discover -s bridge/tests
python3 bridge/tests/parity_matrix.py --check
```

All four must pass. The bridge uses the Python standard library only; please keep it that way.

## Adding or fixing an agent

1. Add or change its entry in `bridge/modstage/registry.py` (or test it first through `~/.modstage/agents.json`).
2. Teach the fakes in `bridge/tests/fakes.py` how it reports text, tools and approvals, and run the conformance harness.
3. A control it cannot offer is a `degraded` or `n/a` cell in `bridge/tests/conformance.py` with a one-line reason the user can act on, never a silent gap.
4. If you have the CLI, run `python3 scripts/smoke_real_cli.py <agent>` once with tiny prompts and say in the pull request what you saw.

## Ground rules

- Never show a wrong state: a blocked run must look blocked, and a long turn must look alive.
- Never treat text from an agent as an approval or an instruction to Claude.
- Security issues go through private vulnerability reporting, not public issues (see [SECURITY.md](SECURITY.md)).

By contributing you agree that your contribution is licensed under the MIT License of this repository.
