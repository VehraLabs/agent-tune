# Security

## What agent-tune does on the wire

* The only byte it ever sends to the KTuner dongle is the single-byte live-data poll (`0xB0`)
  that the KTuner app itself sends. There is no code path that writes to the dongle's storage
  or the ECU, and nothing that flashes.
* It never opens a network connection. Logs, tune files and manifests stay on your disk.
* Tune edits go into a new `.kcl` file; the source file is never modified. Every output file is
  decoded again and checked against the requested values before it is reported as written.

## Reporting a vulnerability

If you find a way for agent-tune to write to a device, send data off the machine, or produce a
`.kcl` whose changed values differ from its manifest, please report it privately through
GitHub's security advisory form on this repository rather than in a public issue. Include the
version (`agent-tune --version`) and steps to reproduce, without any tune files or logs that
identify a car.
