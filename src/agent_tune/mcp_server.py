"""MCP server exposing agent-tune to AI agents over stdio.

Claude Code: `claude mcp add agent-tune -- agent-tune mcp`. Any MCP client can run
`agent-tune mcp` as a stdio server. The CLI offers the same functions as JSON for
agents that prefer a shell; see skills/agent-tune/SKILL.md.
"""
from pathlib import Path
import time

from mcp.server.mcpserver import MCPServer

from . import __version__, analyze, datalog, logs, suggest, telemetry, tune

INSTRUCTIONS = """agent-tune reads car data through the user's KTuner dongle and writes new KTuner .kcl tune files.
Workflow: datalog_guide (tell the user how to record and drive for their goal) -> the user records with KTuner and
exports CSV, or list_devices -> record_log (KTuner app closed, ignition ON) -> check_log (if not ready, tell the user
exactly what to redo) -> analyze_log -> discuss findings with the user -> tune_cells to see current values -> tune_write (dry_run first) a NEW
.kcl -> the user opens it in KTuner, reviews and flashes it themselves -> record again and compare_logs.
Rules: never claim a change is safe; change timing in small steps (<= 1 degree) and only where logs show no knock;
never add timing where AFR is lean at full throttle; show every change (from -> to) before writing; never overwrite
the user's original tune; keep the user's stock backup. Power decisions need full-throttle runs in the same gear.
Live USB reading and .kcl editing are verified for the Honda Civic 11th gen 2.0 L (64S ECU). KTuner CSV analysis works
for any car. For other cars, tune_check reports whether the known .kcl layout looks plausible; with the user's agreement,
allow_unverified applies it anyway and the user must confirm the changed cells in KTuner before anything else."""

server = MCPServer('agent-tune', version=__version__, instructions=INSTRUCTIONS)


@server.tool()
def list_devices() -> dict:
    """Find connected KTuner dongles (USB)."""
    return {'devices': telemetry.find_ports(), 'note': 'Close the KTuner app before recording; it holds the port.'}


@server.tool()
def record_log(seconds: float = 60, port: str | None = None, out_path: str | None = None,
               platform: str = telemetry.DEFAULT_PLATFORM) -> dict:
    """Record live values from the car for up to 900 s (blocks until done). Returns the log path and counts.
    `platform` is a bundled platform id or the path of a platform .json for a car that is not bundled yet."""
    if not 0 < seconds <= 900:
        raise ValueError('seconds must be between 0 and 900')
    ports = [p['port'] for p in telemetry.find_ports()]
    name = port or (ports[0] if len(ports) == 1 else None)
    if not name:
        raise ValueError(f'Specify port; detected: {ports or "none"}')
    out = Path(out_path or time.strftime('drive-%Y%m%d-%H%M%S.jsonl'))
    handle = telemetry.open_port(name)
    try:
        summary = telemetry.record(handle, seconds, out, platform)
    finally:
        handle.close()
    result = {'log': str(out.resolve()), 'summary': summary.as_dict()}
    if summary.frames and not summary.telemetry_frames:
        result['warning'] = ('Frames were received but none matched the platform layout; they were logged raw. '
                             'This car may need its own platform file (see CONTRIBUTING.md).')
    return result


@server.tool()
def datalog_guide(goal: str = 'power') -> dict:
    """How to record a useful datalog: what to record with, how to drive, how to export.
    Goals: power (full-throttle runs), cruise (fuel trims/AFM), baseline, compare (before/after)."""
    return datalog.guide(goal)


@server.tool()
def check_log(path: str, goal: str = 'power') -> dict:
    """Is a recorded log good enough for the goal? Returns each requirement and what to redo."""
    return datalog.check(logs.load(path), goal)


@server.tool()
def analyze_log(path: str, findings_only: bool = False) -> dict:
    """Tuner-style analysis of an agent-tune log or KTuner CSV export: pulls, knock, AFR, timing, trims, heat."""
    result = analyze.analyze(logs.load(path))
    return {'findings': result['findings']} if findings_only else result


@server.tool()
def compare_logs(before: str, after: str) -> dict:
    """Before/after comparison by RPM bin (RPM rise rate, AFR, timing, knock)."""
    return analyze.compare(logs.load(before), logs.load(after))


@server.tool()
def tune_check(path: str) -> dict:
    """Is this .kcl from a verified family? For other files, reports whether the known layout looks plausible."""
    return tune.check(path)


@server.tool()
def tune_tables(path: str, allow_unverified: bool = False) -> list:
    """Editable tables in a .kcl with value counts and ranges."""
    return tune.tables(path, allow_unverified)


@server.tool()
def tune_cells(path: str, match: str | None = None, allow_unverified: bool = False) -> list:
    """Editable values (id, label, current value, axis). `match` filters by id pattern or label text."""
    return tune.cells(path, match, allow_unverified)


@server.tool()
def tune_write(path: str, out_path: str, set_values: dict[str, float] | None = None,
               add: dict[str, float] | None = None, scale: dict[str, float] | None = None,
               note: str | None = None, dry_run: bool = True, allow_unverified: bool = False) -> dict:
    """Plan (dry_run=True, default) or write a NEW .kcl. Keys may be cell ids or patterns (e.g. ign-max-h-6000-*).
    Show the planned changes to the user and get agreement before calling again with dry_run=False.
    `allow_unverified` applies the known layout to a file from an unverified family; the user must then confirm
    the changed cells in KTuner."""
    changes = tune.plan(path, set_values, add, scale, allow_unverified)
    if dry_run:
        current = {c['id']: c['value'] for c in tune.cells(path, allow_unverified=allow_unverified)}
        return {'dry_run': True, 'changes': [{'id': k, 'from': current[k], 'to': v} for k, v in changes.items()]}
    return tune.write(path, changes, out_path, note, allow_unverified)


@server.tool()
def suggest_afm(tune_path: str, log_paths: list[str], allow_unverified: bool = False) -> dict:
    """AFM flow (MAF calibration) suggestions from 2+ agreeing logs and the tune."""
    return suggest.afm([logs.load(p) for p in log_paths], tune.afm_curve(tune_path, allow_unverified))


@server.tool()
def platforms() -> list:
    """Bundled platforms and the channels decoded over USB."""
    return [{'id': p['id'], 'name': p['name'], 'channels': [c['name'] for c in p['channels']],
             'not_decoded': p.get('not_decoded', [])} for p in telemetry.platforms().values()]


def main():
    server.run('stdio')


if __name__ == '__main__':
    main()
