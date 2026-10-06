# Changelog

## Unreleased

* `guide GOAL` explains how to record a useful datalog (method, driving plan, export) and
  `check-log LOG --goal GOAL` says whether a log is good enough and what to redo. MCP tools
  `datalog_guide` and `check_log`; the skill now starts with them.
* README rewritten in plain language for KTuner owners who are not tuners, with a short glossary.
  Command help text uses the same wording.
* Demo video in `docs/demo.mp4` (about 55 seconds), with the scripts that produce it in `demo/`.
* Repository: pull requests are squash merged and titled in Conventional Commits form
  (`feat:`, `fix:`, ...), checked by the `pr-title` workflow.

## 0.2.1 - 2026-10-06

* Published on PyPI as `vehra-agent-tune` (the name `agent-tune` is too close to an existing
  project). The command is still `agent-tune` and the package is still `agent_tune`.

## 0.2.0 - 2026-10-06

* New README, CONTRIBUTING, SECURITY and a skill in `skills/agent-tune` for skill-based agents.
* `tune check` reports plausibility checks for `.kcl` files outside the verified families.
  `--unverified` (CLI) and `allow_unverified` (MCP) apply the known layout anyway so owners of
  other cars can confirm it in KTuner. Verified families are a table in `kcl/decode.py`.
* Live logging: `--platform` accepts the path of a platform JSON file. Frames that do not match
  the platform layout are logged raw. `--port` accepts any serial port when given explicitly.
* The `.kcl` package is restructured into one module per table with no research notes in the
  output. Offsets and encodings are unchanged.
* Removed support for the pre-release internal log format.
* Repository: issue templates, code of conduct, Dependabot, branch protection on `main`, and a
  release workflow that publishes GitHub release assets and PyPI.

## 0.1.0

* Initial release.
