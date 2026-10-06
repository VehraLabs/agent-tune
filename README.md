# agent-tune

**Tune your car with the KTuner you already own, with an AI agent doing the analysis.**

[![test](https://github.com/VehraLabs/agent-tune/actions/workflows/test.yml/badge.svg)](https://github.com/VehraLabs/agent-tune/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

agent-tune is a command-line tool for KTuner owners. It reads live data from your car through
the KTuner dongle, analyzes logs the way a tuner would, and writes a **new `.kcl` tune file**
with the changes you agree on. You open that file in KTuner, review it, and flash it yourself.

It is built to be driven by an AI agent: every command prints JSON, and the bundled skill and
MCP server teach the agent the tuning workflow and the safety rules. It works just as well by
hand.

**agent-tune never flashes anything.** It never writes to the dongle or the ECU, and it never
overwrites your original tune.

> KTuner only. This project works with KTuner hardware and the KTuner app. It is not affiliated
> with or endorsed by KTuner.

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/). Tested on Windows, where KTuner runs; log
and tune-file analysis is plain Python and runs anywhere.

```bash
uv tool install "agent-tune[mcp] @ git+https://github.com/VehraLabs/agent-tune"
```

Drop `[mcp]` if you only want the command line.

## Quick start

```bash
agent-tune devices                                   # find the dongle
agent-tune log --seconds 600 -o drive.jsonl          # KTuner app closed, ignition ON
agent-tune analyze drive.jsonl --findings            # or a KTuner CSV export
agent-tune tune check stock.kcl                      # is this tune file supported?
agent-tune tune set stock.kcl --add "ign-max-h-6000-*=0.5" -o plus-half.kcl --dry-run
```

Drop `--dry-run` to write `plus-half.kcl` and `plus-half.manifest.json`. Open the new file in
KTuner, review the changed cells, and flash it yourself.

## How it fits together

1. **Read.** `log` polls the dongle for live values and keeps the raw bytes in a `.jsonl` log.
   Or export a datalog from KTuner as CSV, which works for any car KTuner supports.
2. **Analyze.** `analyze` finds full-throttle pulls and reports knock, AFR, timing, fuel trims
   and intake heat as plain-language findings with the numbers behind them.
3. **Change.** `tune cells` shows current values. `tune set` writes a new `.kcl` plus a manifest
   listing each value's old, requested and stored value. Dry-run first.
4. **Flash and compare.** You flash in KTuner. Log the same conditions again and `compare` shows
   what the change did.

## Use it with an AI agent

Pick whichever fits your agent. All of them run the same code.

| Agent | How |
|---|---|
| Skill-based agents (OpenClaw, Claude Code, Codex, ...) | Copy [`skills/agent-tune`](skills/agent-tune) into your skills folder (OpenClaw: `~/.agents/skills` or `<workspace>/skills`). The skill teaches the workflow and drives the CLI. |
| MCP clients | `claude mcp add agent-tune -- agent-tune mcp`, or run `agent-tune mcp` as a stdio server from any MCP client. |
| Anything with a shell | Call the CLI directly. Every command prints JSON. |

Then ask something like: *"Record 10 minutes of driving, analyze it, and suggest safe changes
to my tune at C:\Tunes\stock.kcl."*

## What's supported

| Capability | Cars |
|---|---|
| Analyze KTuner CSV exports: pulls, knock, AFR, timing, trims, before/after | Any car KTuner supports |
| Live logging through the dongle (KTuner app closed) | Honda Civic 11th gen 2.0 L NA (64S ECU). Other cars: see below |
| Read and edit `.kcl` tunes: 1,502 values across ignition base and maximum, WOT enrichment, intake VTC, VTEC, rev limits, fuel cut, MAP cut, AFM curve and cylinder trims | Honda Civic 11th gen 2.0 L NA (64S ECU, 37805-64S-AC20), KTuner 1.0.14.1 saves. Other cars: see below |

Live channels: RPM, measured and commanded lambda, MAF g/s and Hz, MAP, TPS, ignition timing,
STFT and LTFT, coolant, intake air, speed, battery, knock control and fuel status. They match
what KTuner displays; they are not an independent sensor calibration. Knock count, VTEC state,
cam angles, commanded throttle and gear are not available over USB yet, so use a KTuner CSV
export when you need them. Timing decisions need the knock count.

### Trying another car

agent-tune is verified on one car so far, but it is built so you can try yours and report back.

* **Logs.** Analysis of KTuner CSV exports already works for any car. For live logging,
  `agent-tune log` records every frame the dongle sends. Frames that do not match the bundled
  layout are kept raw in the log so they can be mapped against a KTuner datalog. You can also
  pass your own layout with `--platform my-car.json`; start from
  [the bundled file](src/agent_tune/platforms/honda_civic_11g_20_64s.json).
* **Tune files.** `agent-tune tune check your.kcl` says whether the file is from a verified
  family and, if not, whether the known table layout looks plausible for it: timing within
  range, AFM curve increasing, rev limits ordered, and so on. If it does, `--unverified` lets
  you read it and write a test file. Change **one** value, open the new file in KTuner, and
  confirm that exactly that cell changed. Writes to unverified files carry a warning in the
  manifest. Do not flash anything until KTuner shows exactly what you expect.

If it works, open an issue or a pull request with the fingerprint from `tune check` and the
car details so the family can be added. [CONTRIBUTING.md](CONTRIBUTING.md) has the steps.
Please never share tune files, VINs or serial numbers.

## Commands

| Command | What it does |
|---|---|
| `devices` | Find connected KTuner dongles |
| `log [--seconds N] [-o FILE] [--platform ID\|FILE.json]` | Record live values to a `.jsonl` log |
| `analyze LOG [--findings]` | Tuner-style analysis of a log or KTuner CSV export |
| `compare BEFORE AFTER` | Before/after by RPM bin: acceleration, AFR, timing, knock |
| `tune check FILE` | Is this `.kcl` supported? Plausibility report otherwise |
| `tune tables FILE`, `tune cells FILE [--match PATTERN]` | Current values |
| `tune set FILE --set/--add/--scale ID=VALUE -o NEW [--dry-run] [--note TEXT]` | Write a new `.kcl` and its manifest |
| `suggest --tune FILE LOG...` | AFM flow suggestions; needs two or more agreeing sessions |
| `platforms` | Bundled platforms and the channels decoded over USB |
| `mcp` | Run the MCP server |

Cell ids look like `ign-max-h-6000-100` (table, cam branch, RPM, column) and accept glob
patterns. Add `--unverified` to `tune` commands for a file outside the verified families.
`tune set` never overwrites the source file.

## Safety

Tuning for power can damage an engine. Timing is where engines get hurt.

* Keep your original tune and a stock backup. Flash only with stable power, and never interrupt
  a flash.
* Change timing in small steps (1 degree or less), only where logs show no knock, and never
  where full-throttle AFR is lean.
* Judge changes with repeatable full-throttle pulls in the same gear at similar intake
  temperatures, only where it is legal and safe.
* You are responsible for what you flash and for complying with the emissions and road laws
  where you drive.

## Development

```bash
uv sync --extra mcp
uv run pytest
```

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to add a platform or a `.kcl` family.
[SECURITY.md](SECURITY.md) states what the tool does and does not do on the wire.

## License

MIT. See [LICENSE](LICENSE).
