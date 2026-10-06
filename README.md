# agent-tune

Let your AI agent help you tune your car with the **KTuner** you already own.

agent-tune reads live values from the car through your KTuner dongle, analyzes logs the way a
tuner would (full-throttle pulls, knock, AFR, timing, fuel trims, heat), and writes a **new
`.kcl` tune file** with the changes you agree on. You open that file in KTuner, review it, and
flash it yourself. agent-tune never flashes anything and never writes to the dongle or ECU.

> **KTuner only.** This project works with KTuner hardware and the KTuner app. It is not
> affiliated with or endorsed by KTuner.

## What works today

| Capability | Platforms |
|---|---|
| Analyze KTuner CSV exports (pulls, knock, AFR, timing, trims, before/after) | Any car KTuner supports |
| Live logging through the KTuner dongle (KTuner app closed) | Honda Civic 11th gen 2.0 L NA (64S ECU) |
| Read and edit `.kcl` tunes (1,502 values: ignition base/max, WOT AFR, intake VTC, VTEC, rev limits, fuel cut, AFM curve, cylinder trims) | Honda Civic 11th gen 2.0 L NA (64S ECU, 37805-64S-AC20 family), KTuner 1.0.14.1 saves |

The 16 live channels (RPM, measured/commanded lambda, MAF g/s and Hz, MAP, TPS, ignition timing,
STFT/LTFT, coolant, intake air, speed, battery, knock control, fuel status) were validated against
KTuner's own displayed values on a real car: 99.84-100% agreement on steady samples within one
display step. That means agent-tune shows what KTuner shows; it is not an independent sensor
calibration. Knock count, VTEC state, cam angles and commanded throttle are not decoded over USB
yet. Use a KTuner CSV export when you need them.

Unsupported `.kcl` files are refused, not guessed. See [CONTRIBUTING.md](CONTRIBUTING.md) to
help add a platform.

## Install

Requires Windows, Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install "agent-tune[mcp] @ git+https://github.com/VehraLabs/agent-tune"
```

## Use it with an AI agent (MCP)

Claude Code:

```bash
claude mcp add agent-tune -- agent-tune mcp
```

Other MCP clients: run `agent-tune mcp` as a stdio server. The server tells the agent the
workflow and safety rules; [AGENTS.md](AGENTS.md) has the full guide.

Then ask your agent something like: *"Record 10 minutes of driving, analyze it, and suggest
safe changes to my tune at C:\Tunes\stock.kcl."*

## Use it from the command line

```bash
agent-tune devices                                   # find the dongle
agent-tune log --seconds 600 -o drive.jsonl          # KTuner app closed, ignition ON
agent-tune analyze drive.jsonl --findings            # or a KTuner CSV export
agent-tune tune check stock.kcl
agent-tune tune tables stock.kcl
agent-tune tune cells stock.kcl --match "wot-h-6000-*"
agent-tune tune set stock.kcl --scale "wot-h-6000-*=0.98" --dry-run
agent-tune tune set stock.kcl --scale "wot-h-6000-*=0.98" -o richer-6000.kcl --note "test pull"
agent-tune compare before.csv after.csv
agent-tune suggest --tune stock.kcl day1.jsonl day2.jsonl   # AFM flow, needs 2+ agreeing sessions
```

Every `tune set` writes a new file plus `<name>.manifest.json` listing each value's old,
requested and stored value. The source tune is never overwritten.

## Safety

Tuning for power can damage an engine. Timing is where engines get hurt.

* Keep your original tune and a stock backup. Flash only with stable power, and never interrupt a flash.
* Change timing in small steps (1 degree or less), only where logs show no knock, and never where
  full-throttle AFR is lean.
* Judge changes with repeatable full-throttle pulls in the same gear at similar intake temperatures.
* You are responsible for what you flash and for complying with the emissions and road laws where
  you drive.

## Credits

Channel definitions and the `.kcl` format support come from controlled experiments on an owner's
car and files (logs compared with KTuner's displayed values; single-value edits saved and read
back in KTuner). MIT licensed.
