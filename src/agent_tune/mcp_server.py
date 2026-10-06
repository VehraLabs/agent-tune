"""MCP server exposing agent-tune to AI agents (stdio).

Add to an MCP client, e.g. Claude Code:
    claude mcp add agent-tune -- uvx --from "agent-tune[mcp]" agent-tune mcp
"""
from pathlib import Path
import time

from mcp.server.mcpserver import MCPServer

from . import __version__, analyze, logs, suggest, telemetry, tune

INSTRUCTIONS = """agent-tune reads car data through the user's KTuner dongle and edits KTuner .kcl tune files.
Workflow: list_devices -> record_log (KTuner app closed, ignition ON) or use the user's KTuner CSV export ->
analyze_log -> discuss findings with the user -> tune_cells to see current values -> tune_write a NEW .kcl ->
the user opens it in KTuner, reviews, and flashes it themselves -> record again and compare_logs.
Rules: never claim a change is safe; change timing in small steps (<= 1 degree) and only where logs show no knock;
never add timing where AFR is lean at full throttle; show every change (from -> to) before writing; never overwrite
the user's original tune; keep the user's stock backup. Power decisions need full-throttle pulls in the same gear.
Live USB reading and .kcl editing are validated only for the Honda Civic 11th gen 2.0 (64S ECU); KTuner CSV analysis
works for any car."""

server = MCPServer('agent-tune', version=__version__, instructions=INSTRUCTIONS)


@server.tool()
def list_devices() -> dict:
    """Find connected KTuner dongles (USB)."""
    return {'devices': telemetry.find_ports(), 'note': 'Close the KTuner app before recording; it holds the port.'}


@server.tool()
def record_log(seconds: float = 60, port: str | None = None, out_path: str | None = None) -> dict:
    """Record live values from the car for up to 900 s (blocks until done). Returns the log path and counts."""
    if not 0 < seconds <= 900:
        raise ValueError('seconds must be between 0 and 900')
    ports = [p['port'] for p in telemetry.find_ports()]
    name = port or (ports[0] if len(ports) == 1 else None)
    if not name:
        raise ValueError(f'Specify port; detected: {ports or "none"}')
    out = Path(out_path or time.strftime('drive-%Y%m%d-%H%M%S.jsonl'))
    handle = telemetry.open_port(name)
    try:
        summary = telemetry.record(handle, seconds, out)
    finally:
        handle.close()
    return {'log': str(out.resolve()), 'summary': summary.as_dict()}


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
    """Is this .kcl supported for editing?"""
    return tune.check(path)


@server.tool()
def tune_tables(path: str) -> list:
    """Editable tables in a supported .kcl with value counts and ranges."""
    return tune.tables(path)


@server.tool()
def tune_cells(path: str, match: str | None = None) -> list:
    """Editable values (id, label, current value, axis). `match` filters by id pattern or label text."""
    return tune.cells(path, match)


@server.tool()
def tune_write(path: str, out_path: str, set_values: dict[str, float] | None = None,
               add: dict[str, float] | None = None, scale: dict[str, float] | None = None,
               note: str | None = None, dry_run: bool = True) -> dict:
    """Plan (dry_run=True, default) or write a NEW .kcl. Keys may be cell ids or patterns (e.g. ign-max-h-6000-*).
    Show the planned changes to the user and get agreement before calling again with dry_run=False."""
    changes = tune.plan(path, set_values, add, scale)
    if dry_run:
        current = {c['id']: c['value'] for c in tune.cells(path)}
        return {'dry_run': True, 'changes': [{'id': k, 'from': current[k], 'to': v} for k, v in changes.items()]}
    return tune.write(path, changes, out_path, note)


@server.tool()
def suggest_afm(tune_path: str, log_paths: list[str]) -> dict:
    """Evidence-gated AFM flow (MAF calibration) suggestions from 2+ logs and the tune."""
    return suggest.afm([logs.load(p) for p in log_paths], tune.afm_curve(tune_path))


@server.tool()
def platforms() -> list:
    """Supported platforms and the channels decoded over USB."""
    return [{'id': p['id'], 'name': p['name'], 'channels': [c['name'] for c in p['channels']],
             'not_decoded': p['not_decoded']} for p in telemetry.platforms().values()]


def main():
    server.run('stdio')


if __name__ == '__main__':
    main()
