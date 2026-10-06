# Guide for AI agents working in this repository

This file is for agents changing the code. The guide for agents *using* agent-tune to tune a
car is [skills/agent-tune/SKILL.md](skills/agent-tune/SKILL.md); read it too, because the
product rules below come from it.

## What this project is

A command-line tool, plus a skill and an MCP server, that lets KTuner owners read live data
from their car, analyze logs, and write a new `.kcl` tune file that they review and flash in
KTuner themselves. See [README.md](README.md).

## Layout

* `src/agent_tune/cli.py`: the commands. Every command prints JSON.
* `src/agent_tune/mcp_server.py`: the same functions as MCP tools.
* `src/agent_tune/telemetry.py` and `platforms/*.json`: live data from the dongle; where each
  channel sits in the reply is data, not code.
* `src/agent_tune/logs.py`, `analyze.py`, `suggest.py`: log loading, tuner-style analysis, and
  suggestions that need agreeing evidence.
* `src/agent_tune/tune.py` and `kcl/`: `.kcl` reading and writing. One module per table;
  `decode.py` holds the verified family fingerprints; `patch.py` turns a plan into byte deltas
  and checks the result by decoding it again.
* `tests/`: synthetic data only. `AGENT_TUNE_TEST_KCL` enables a round trip on a real file.

## Rules that must survive any change

* The tool is read-only toward the car: the only byte sent to the dongle is the live-data poll.
  Nothing flashes, nothing writes to the dongle or ECU.
* `tune set` and `tune_write` always create a new file and never overwrite the source.
* Files outside the verified `.kcl` families are refused unless the user opts in with
  `--unverified` / `allow_unverified`, and then the output carries a warning.
* Output never claims a change is safe or promises a power gain.
* Never commit tune files, logs, VINs or serial numbers. Tests use synthetic data.
* Plain words in messages and docs. Say what the tool does, not how it was researched.

## Working here

```bash
uv sync --extra mcp
uv run pytest
```

Keep output keys stable; agents depend on them. Add a test with each behaviour change and a
line to [CHANGELOG.md](CHANGELOG.md).

Changes go through pull requests, which are squash merged: the PR title becomes the commit on
`main`. Title every PR in Conventional Commits form, `type(scope): what changed` (types `feat`,
`fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`; `!` for
breaking), and keep the PR description accurate, because it becomes the commit body. The
`pr-title` check enforces the title format.
