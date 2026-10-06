<p align="center">
  <a href="https://vehra.net">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/brand/vehra-logo-reversed.svg">
      <img src="docs/brand/vehra-logo.svg" alt="VEHRA" width="180">
    </picture>
  </a>
</p>

# agent-tune

**Your AI tuning assistant for KTuner.**

A [VEHRA](https://vehra.net) project.

[![test](https://github.com/VehraLabs/agent-tune/actions/workflows/test.yml/badge.svg)](https://github.com/VehraLabs/agent-tune/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

If you own a KTuner, you already have the tools to tune your car. The hard part is knowing
what to change. agent-tune helps with that:

* It tells you **how to record a datalog**: what to press in KTuner and how to drive.
* It **reads the logs for you, the way a professional tuner would**, and explains what it finds
  in plain language: is the engine knocking, is the fuel rich or lean, where is there room to
  improve.
* It **suggests small, careful changes** and, when you agree, writes them into a **new tune
  file**.
* **You stay in control.** You open the new file in KTuner, check it, and flash it yourself.
  agent-tune never flashes your car and never changes your original tune.

Use it through an AI assistant such as Claude Code, Codex or OpenClaw, which talks you through
each step, or run the commands yourself.

![A KTuner owner asks what to do first, gets driving instructions for a datalog, and gets one small reviewed change](docs/demo.gif)

> agent-tune works with KTuner hardware and the KTuner app. It is not affiliated with or
> endorsed by KTuner.

## How it works

1. **Record.** agent-tune tells you how to drive for your goal. For more power, that's a
   warm-up and three full-throttle runs. You record them with KTuner and export the datalog to
   a CSV file. agent-tune then checks that the log has what it needs, and tells you exactly
   what to redo if not.
2. **Understand.** It goes through the log like a tuner would: full-throttle runs, knock, fuel
   (AFR), ignition timing, fuel trims and intake temperature. It explains each finding in plain
   words, with the numbers behind it.
3. **Change.** It shows the current values in your tune and proposes one small step at a time,
   with the reason for each. When you say yes, it writes a new `.kcl` tune file plus a list of
   every value it changed. Your original file is left untouched.
4. **Flash and check.** You open the new file in KTuner, review it and flash it. Then you
   record the same runs again, and agent-tune compares before and after so you can see what
   the change did.

## What you need

* A KTuner device and the KTuner app, on a Windows laptop.
* A car KTuner supports. The full workflow, including editing tune files, currently works on
  the **Honda Civic 11th gen 2.0 L** (non-turbo). For other cars, agent-tune can already read
  and explain your KTuner datalogs; see [Trying another car](#trying-another-car).
* Optional: an AI assistant that can use skills or MCP tools. agent-tune also works fine
  without one.

## What it will and won't do

* It **never flashes** your car and never sends anything to the car except requests to read
  live data.
* It **never overwrites** your original tune. Every change goes into a new file you choose.
* It **never claims a change is safe** or promises a power gain. It suggests small steps,
  explains why, and asks you to check the result with a new datalog.
* Tuning for power can damage an engine if done carelessly. Read [Safety](#safety) before you
  flash anything.

## Get started

Install it with [uv](https://docs.astral.sh/uv/) (needs Python 3.11 or newer):

```bash
uv tool install "vehra-agent-tune[mcp]"
```

The package is called `vehra-agent-tune` on PyPI; the command it installs is `agent-tune`.
Leave out `[mcp]` if you won't connect an AI assistant. To install the latest development
version instead:

```bash
uv tool install "vehra-agent-tune[mcp] @ git+https://github.com/VehraLabs/agent-tune"
```

### With an AI assistant

Connect it once, then just talk to your assistant.

| Assistant | How to connect |
|---|---|
| Assistants that use skills (Claude Code, Codex, OpenClaw, ...) | Copy [`skills/agent-tune`](skills/agent-tune) into your skills folder (OpenClaw: `~/.agents/skills` or `<workspace>/skills`). |
| Assistants that use MCP | `claude mcp add agent-tune -- agent-tune mcp`, or run `agent-tune mcp` as a stdio server from any MCP client. |
| Anything that can run commands | Call `agent-tune` directly. Every command prints JSON. |

Then ask something like: *"I have a KTuner on my Civic and I want more power. What should I
do first?"* The assistant explains how to record, checks your log, explains what it finds,
and suggests changes for you to approve.

### On your own

```bash
agent-tune guide power                          # how to record and drive for more power
agent-tune check-log drive.csv --goal power     # is my log good enough? what to redo if not
agent-tune analyze drive.csv --findings         # what the log shows, in plain words
agent-tune tune check stock.kcl                 # can agent-tune edit this tune file?
agent-tune tune set stock.kcl --add "wot-h-6000-600=0.3" -o step-1.kcl --dry-run   # preview one change
```

Remove `--dry-run` to write `step-1.kcl` and `step-1.manifest.json`. Open the new file in
KTuner, check the changed values, and flash it yourself. After driving the same runs again,
`agent-tune compare before.csv after.csv` shows what changed.

## A few terms

* **Datalog**: a recording of your engine's sensors while you drive. KTuner records it; export
  it to CSV for agent-tune.
* **Full-throttle run** (or pull): accelerating with the pedal all the way down through the rev
  range. This is where power is made, so it's what power tuning looks at.
* **AFR (air-fuel ratio)**: how much air there is for each part of fuel. Lower is richer (more
  fuel). Naturally aspirated engines usually make the most power around 12.5 to 13.2 at full
  throttle.
* **Knock**: uncontrolled combustion that can damage an engine. Any change that causes knock
  gets undone.
* **Ignition timing**: when the spark fires. A little more can add power, but too much causes
  knock.
* **Tune file (`.kcl`)**: the file KTuner flashes to your car. **Flashing** means writing it to
  the car's computer.

## What's supported

| What | Cars |
|---|---|
| Recording guides and log checks | Any car KTuner supports |
| Explaining KTuner datalogs (CSV export): runs, knock, AFR, timing, fuel trims, before/after | Any car KTuner supports |
| Recording live data with agent-tune instead of the KTuner app | Honda Civic 11th gen 2.0 L (64S ECU) |
| Reading and editing tune files: 1,502 values, including ignition timing, full-throttle fuel (WOT enrichment), intake cam (VTC), VTEC, rev limits, fuel cut, airflow (AFM) curve and cylinder trims | Honda Civic 11th gen 2.0 L (64S ECU, 37805-64S-AC20), KTuner 1.0.14.1 save files |

When agent-tune records live data itself, it reads RPM, measured and commanded lambda (AFR),
MAF (g/s and Hz), MAP, throttle position, ignition timing, short and long-term fuel trims,
coolant and intake temperature, speed, battery voltage, knock control and fuel status. These
match what KTuner displays. Knock count, VTEC state, cam angles, commanded throttle and gear
are not available that way yet, so record with the KTuner app when you need them. Any timing
change needs the knock count.

### Trying another car

agent-tune has been verified on one car so far, and it is built so you can try yours and
report back.

* **Datalogs.** Guides, log checks and explanations already work for any car with a KTuner CSV
  export. For recording with agent-tune itself, `agent-tune log` keeps every reply the dongle
  sends, including ones it doesn't recognize yet, so they can be matched against a KTuner
  datalog later. You can also give it your own channel layout with `--platform my-car.json`,
  starting from [the bundled file](src/agent_tune/platforms/honda_civic_11g_20_64s.json).
* **Tune files.** `agent-tune tune check your.kcl` says whether your file is from a verified
  family. If not, it checks whether the known layout looks right for it (timing in a sensible
  range, the airflow curve increasing, rev limits in order, and so on). If it does,
  `--unverified` lets you read it and write a test file. Change **one** value, open the new
  file in KTuner, and confirm that exactly that value changed. Files written this way carry a
  warning. Don't flash anything until KTuner shows exactly what you expect.

If it works on your car, open an issue or a pull request with the fingerprint from
`tune check` and your car details so it can be added. [CONTRIBUTING.md](CONTRIBUTING.md) has
the steps. Please never share tune files, VINs or serial numbers.

## Commands

| Command | What it does |
|---|---|
| `guide [power\|cruise\|baseline\|compare]` | Step-by-step instructions for recording a useful datalog: what to press, how to drive, how to export |
| `check-log LOG [--goal GOAL]` | Checks whether a datalog is good enough for the goal, and says what to redo if not |
| `analyze LOG [--findings]` | Reads a datalog the way a tuner would: runs, knock, AFR, timing, fuel trims, heat |
| `compare BEFORE AFTER` | Before and after a change, by RPM: acceleration, AFR, timing, knock |
| `devices` | Finds a connected KTuner dongle |
| `log [--seconds N] [-o FILE] [--platform ID\|FILE.json]` | Records live data with agent-tune (KTuner app closed) |
| `tune check FILE` | Can agent-tune edit this tune file? Plausibility report if it isn't verified |
| `tune tables FILE`, `tune cells FILE [--match PATTERN]` | Shows the current values in a tune file |
| `tune set FILE --set/--add/--scale ID=VALUE -o NEW [--dry-run] [--note TEXT]` | Writes a new tune file with the changes, plus a list of every value changed |
| `suggest --tune FILE LOG...` | Airflow (AFM) curve suggestions; needs two or more drives that agree |
| `platforms` | Cars agent-tune can record live data from, and the values it reads |
| `mcp` | Runs the MCP server for AI assistants |

Value ids look like `ign-max-h-6000-100` (table, cam, RPM, column) and accept wildcards such as
`wot-h-6000-*`. Add `--unverified` to `tune` commands for a file outside the verified families.
`tune set` never overwrites the file you start from.

## Safety

Tuning for power can damage an engine. Ignition timing is where engines get hurt.

* Keep your original tune and a stock backup. Flash only with a healthy battery or a charger
  connected, and never interrupt a flash.
* Change timing in small steps (1 degree or less), only where your logs show no knock, and
  never where the full-throttle AFR is lean.
* Judge every change with the same full-throttle runs in the same gear, at a similar
  temperature, and only where it is legal and safe.
* You are responsible for what you flash and for following the emissions and road laws where
  you drive.

## For developers

```bash
uv sync --extra mcp
uv run pytest
```

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to add a car or a tune-file family.
[SECURITY.md](SECURITY.md) states exactly what the tool does and doesn't send to the car.
[AGENTS.md](AGENTS.md) is the guide for AI agents changing this code.

## License

MIT. See [LICENSE](LICENSE). The VEHRA name and logo are trademarks of Vehra and are not covered
by the license; see [docs/brand](docs/brand/README.md).

---

<p align="center">
  <a href="https://vehra.net">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="docs/brand/vehra-icon-reversed.svg">
      <img src="docs/brand/vehra-icon.svg" alt="VEHRA" width="28">
    </picture>
  </a>
  <br>
  <sub>Made by <a href="https://vehra.net">VEHRA</a></sub>
</p>
