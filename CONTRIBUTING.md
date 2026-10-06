# Contributing

## Adding a platform (live channels)

Live values come from KTuner's B0 read reply, which carries diagnostic data groups. Each
platform needs a JSON file in `src/agent_tune/platforms/` that says where each channel sits.
The validation method that produced the Civic file:

1. Record, at the same time, a KTuner datalog (exported to CSV) and the raw dongle replies,
   over parked revs, idle with load changes (A/C), engine-off/restart and a normal drive.
2. Align the two recordings on RPM, then compare every KTuner channel with candidate byte
   positions and formats. Fit on one part of the data and check on held-out data.
3. Freeze each encoding (offset, format, scale, bias) and score it without refitting on other
   sessions. Accept only channels that agree within one KTuner display step on 99%+ of steady
   samples, and say over what range they were validated.

Please share only aggregated results, never VINs, serial numbers or raw logs that identify a
car or person.

## Adding a `.kcl` family

`.kcl` support is measured value by value: change one value in KTuner, save, change it again,
restore it, and compare the saved files to find where and how it is stored; then confirm by
writing values with agent-tune and reading them back in KTuner. Files outside a measured family
are refused by a fingerprint check. Do not commit tune files; they are personal and may be
copyrighted.

## Development

```bash
uv sync --extra mcp
uv run pytest
```

Tests use synthetic data. Set `AGENT_TUNE_TEST_KCL=<path to a supported .kcl>` to also run the
`.kcl` round-trip tests against a real file.
