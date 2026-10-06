# Contributing

Thanks for helping more KTuner owners use this. The most useful contributions are reports that
agent-tune works (or does not) on a car it has not seen, platform files for live logging on
other cars, and new verified `.kcl` families.

## Ground rules

* Never commit tune files, logs, VINs, ECU serial numbers or anything else that identifies a
  car or a person. `.gitignore` blocks the common file types; please check anyway.
* agent-tune stays read-only toward the car. Do not add code that sends anything to the dongle
  other than the live-data poll, and never anything that flashes.
* Every command prints JSON. Keep output stable and self-describing; agents depend on it.
* One behaviour per pull request, with a test.

## Development

```bash
uv sync --extra mcp
uv run pytest
```

Tests use synthetic data. Set `AGENT_TUNE_TEST_KCL=<path to a supported .kcl>` to also run the
`.kcl` round-trip test against a real file. Keep that file out of the repository.

## Reporting how it went on your car

Run `agent-tune tune check your.kcl` and `agent-tune log --seconds 60`, then open an issue
titled with the car, engine, ECU part number (shown in KTuner) and KTuner version. Include:

* the `tune check` output (it contains fingerprints and pass/fail checks, not tune values),
* the `summary` from `log`, and which channels matched KTuner's display,
* whether a single-cell edit written with `--unverified` showed up correctly in KTuner.

## Adding a platform (live channels)

A platform is a JSON file in `src/agent_tune/platforms/` that describes the dongle's reply frame
and where each channel sits. Start by copying the bundled Civic file.

1. Record a KTuner datalog (export it to CSV) and an agent-tune log at the same time: parked
   revs, idle with load changes (A/C on and off), engine off and restart, then a normal drive.
   If no frame matches the bundled layout, the log still holds every frame raw (`"frame"` lines);
   that is what you need.
2. Align the two recordings on RPM and compare each KTuner channel with candidate byte
   positions, widths and scales. Fit on one part of the recording and check on the rest.
3. Write each channel's offset, type, scale and bias into the JSON. Accept a channel only if it
   matches KTuner's display within one display step on nearly all steady samples, and note any
   limits, for example a temperature range you could not cover.
4. Try it with `agent-tune log --platform my-car.json`, then open a pull request with the file
   and a summary of how you checked it. No raw logs, please.

## Adding a `.kcl` family

A family is identified by a fingerprint: the SHA-256 of the decoded save body with every
editable table masked out. The same ECU calibration gives the same fingerprint whatever the tune
values are. Verified families are listed in `FAMILIES` in `src/agent_tune/kcl/decode.py`.

1. Run `agent-tune tune check your.kcl`. If every plausibility check passes, the bundled table
   layout probably fits your file.
2. Confirm it. Change one value by a known amount, for example
   `agent-tune tune set your.kcl --unverified --add ign-base-l-1500-526=0.5 -o test.kcl`, open
   `test.kcl` in KTuner and check that exactly that cell changed by exactly that amount. Repeat
   for one cell in each table you care about (WOT enrichment, intake VTC, rev limits, AFM
   curve, and so on).
3. Open a pull request that adds the fingerprint and a description to `FAMILIES`, and say which
   tables you confirmed.

If some checks fail, the tables sit elsewhere in your file. Finding them works like this: change
one value in KTuner, save, change it again, save again, then restore it. Compare the decoded
bodies to see which bytes moved and how the value is encoded. That becomes a new table layout
rather than a new fingerprint. Open an issue first so we can agree on the shape.

## Style

Plain Python 3.11+, standard library plus pyserial. Short functions, plain words in messages,
and never a claim that a change is safe.
