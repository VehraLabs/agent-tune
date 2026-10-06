# Changelog

## Unreleased

* New README, CONTRIBUTING, SECURITY and a skill in `skills/agent-tune` for skill-based agents.
* `tune check` reports plausibility checks for `.kcl` files outside the verified families.
  `--unverified` (CLI) and `allow_unverified` (MCP) apply the known layout anyway so owners of
  other cars can confirm it in KTuner. Verified families are a table in `kcl/decode.py`.
* Live logging: `--platform` accepts the path of a platform JSON file. Frames that do not match
  the platform layout are logged raw. `--port` accepts any serial port when given explicitly.
* The `.kcl` package is restructured into one module per table with no research notes in the
  output. Offsets and encodings are unchanged.
* Removed support for the pre-release internal log format.

## 0.1.0

* Initial release.
