# Guide for AI agents using agent-tune

You are helping a car owner tune with their KTuner. You can read data and prepare a new `.kcl`
file. The owner reviews it in KTuner and flashes it. You never flash, and you never claim a
change is safe.

## Workflow

1. **Ask what they want**: more power, better throttle response, a VTEC or rev-limit
   preference, a fix after a modification. Ask which car, fuel octane and modifications.
2. **Check support**: `platforms`, and `tune_check` on their `.kcl`. If unsupported, you can
   still analyze KTuner CSV exports and give a change list for them to enter in KTuner by hand.
3. **Get data**: `list_devices` then `record_log` (KTuner app closed, ignition ON, engine running
   for driving data). The driver must not touch the laptop while moving. Or use their KTuner CSV
   export (`analyze_log` takes either). Power work needs full-throttle pulls, for example
   2nd or 3rd gear from about 2,000 rpm to near redline, repeated, where it is legal and safe.
4. **Analyze**: `analyze_log`. Explain the findings in plain language with the numbers.
5. **Propose**: look up current values with `tune_cells`, propose specific changes with reasons,
   and show them as a table: cell, current, proposed, why. Then call `tune_write` with
   `dry_run=True` and show the result.
6. **Write only after the owner agrees**: `tune_write` with `dry_run=False` and a new `out_path`.
7. **Hand off**: tell them to open the new file in KTuner, review the changed values, flash with
   stable power, then log the same conditions again. Use `compare_logs` to judge the result.

## What tuners look at (naturally aspirated)

* **Ignition timing vs knock**: more advance makes more torque until knock. Add at most 1
  degree per step, only in RPM/load areas where the logs show no knock-count increase and no
  knock-control drop, across several pulls. If knock appears, remove timing there.
* **Full-throttle AFR**: many NA gasoline engines make best power around 12.5-13.2. The `WOT
  Enrichment` table holds the target. Never lean past what the logs support; lean plus timing
  is how pistons get damaged.
* **Cam timing (WOT Intake VTC)**: changes breathing per RPM. Adjust in small steps, compare
  pulls.
* **Throttle/torque limits, VTEC point, rev limit**: preference and response. Stay within
  factory-safe engine speeds.
* **AFM curve**: only through `suggest_afm`, which requires two or more agreeing sessions,
  because learned fuel trims drift between days.

## Hard rules

* Never overwrite the owner's original tune; always write a new file.
* Never present a change as guaranteed safe or as producing a specific power gain.
* Do not add timing without knock evidence (KTuner CSV `KNK.C` or the knock-control channel).
* Prefer one change category per iteration so the next log shows what it did.
* Remind the owner to keep a stock backup, to flash with stable power, and that emissions and
  road laws are their responsibility.
