"""agent-tune command line. Every command prints JSON so people and AI agents can both use it."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

from . import __version__, analyze, datalog, logs, suggest, telemetry, tune


def emit(data):
    print(json.dumps(data, indent=2, default=str))


def pairs(items, flag):
    out = {}
    for item in items or []:
        if '=' not in item:
            raise SystemExit(f'{flag} expects ID=VALUE (ID may be a pattern like ign-max-h-6000-*), got {item!r}')
        key, value = item.split('=', 1)
        try:
            out[key.strip()] = float(value)
        except ValueError:
            raise SystemExit(f'{flag} {item!r}: value must be a number') from None
    return out


def cmd_devices(a):
    emit({'devices': telemetry.find_ports(),
          'note': 'Close the KTuner app before logging; it holds the same port.'})


def cmd_log(a):
    ports = [p['port'] for p in telemetry.find_ports()]
    port_name = a.port or (ports[0] if len(ports) == 1 else None)
    if not port_name:
        raise SystemExit(f'Specify --port; detected KTuner ports: {ports or "none"}')
    out = Path(a.out or time.strftime('drive-%Y%m%d-%H%M%S.jsonl'))
    last = [0.0]

    def show(t, values):
        if t - last[0] >= 1.0 and not a.quiet:
            last[0] = t
            keys = ('rpm', 'speed_kph', 'map_kpa', 'tps_pct', 'lambda_measured', 'ign_deg', 'ect_c')
            print(f'{t:7.1f}s ' + '  '.join(f'{k}={values[k]:.4g}' for k in keys if k in values), file=sys.stderr)
    port = telemetry.open_port(port_name)
    stop = threading.Event()
    try:
        summary = telemetry.record(port, a.seconds, out, a.platform, on_values=show, stop=stop)
    except KeyboardInterrupt:
        stop.set()
        summary = None
    finally:
        port.close()
    result = {'log': str(out), 'summary': summary.as_dict() if summary else 'stopped by user'}
    if summary and summary.frames == 0:
        result['warning'] = ('No reply from the dongle. Is it on the OBD port with ignition ON, and KTuner closed? '
                             'Unplug and replug the dongle USB and retry.')
    elif summary and summary.telemetry_frames == 0:
        result['warning'] = (f'{summary.unknown_frames} frames received but none matched the platform layout '
                             f'({a.platform}). They were logged raw. This car may need its own platform file; '
                             'see CONTRIBUTING.md.')
    emit(result)


def cmd_guide(a):
    emit(datalog.guide(a.goal))


def cmd_check_log(a):
    emit(datalog.check(logs.load(a.log), a.goal))


def cmd_analyze(a):
    result = analyze.analyze(logs.load(a.log))
    emit(result['findings'] if a.findings else result)


def cmd_compare(a):
    emit(analyze.compare(logs.load(a.before), logs.load(a.after)))


def cmd_tune(a):
    if a.action == 'check':
        emit(tune.check(a.file))
    elif a.action == 'tables':
        emit(tune.tables(a.file, a.unverified))
    elif a.action == 'cells':
        emit(tune.cells(a.file, a.match, a.unverified))
    elif a.action == 'set':
        if not a.out:
            raise SystemExit('tune set needs -o NEW_FILE.kcl')
        changes = tune.plan(a.file, pairs(a.set, '--set'), pairs(a.add, '--add'), pairs(a.scale, '--scale'),
                            a.unverified)
        if a.dry_run:
            current = {c['id']: c['value'] for c in tune.cells(a.file, allow_unverified=a.unverified)}
            emit({'dry_run': True, 'changes': [{'id': k, 'from': current[k], 'to': v} for k, v in changes.items()]})
            return
        emit(tune.write(a.file, changes, a.out, a.note, a.unverified))


def cmd_suggest(a):
    result = suggest.afm([logs.load(p) for p in a.logs], tune.afm_curve(a.tune, a.unverified))
    emit(result)


def cmd_platforms(a):
    emit([{'id': p['id'], 'name': p['name'], 'ecu': p.get('ecu'), 'channels': [c['name'] for c in p['channels']],
           'not_decoded': p.get('not_decoded', [])} for p in telemetry.platforms().values()])


def cmd_mcp(a):
    from .mcp_server import main as serve
    serve()


def build_parser():
    p = argparse.ArgumentParser(prog='agent-tune', description='Read car data through your KTuner dongle, analyze it, '
                                'and write a new .kcl tune file to review and flash in KTuner.')
    p.add_argument('--version', action='version', version=__version__)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('devices', help='find connected KTuner dongles').set_defaults(func=cmd_devices)
    lg = sub.add_parser('log', help='record live values (KTuner app must be closed)')
    lg.add_argument('--port', help='serial port; default: the single detected KTuner dongle')
    lg.add_argument('--seconds', type=float, default=300)
    lg.add_argument('-o', '--out')
    lg.add_argument('--platform', default=telemetry.DEFAULT_PLATFORM,
                    help='bundled platform id (see `platforms`) or the path of your own platform .json')
    lg.add_argument('--quiet', action='store_true')
    lg.set_defaults(func=cmd_log)
    gd = sub.add_parser('guide', help='how to record a useful datalog for a goal')
    gd.add_argument('goal', nargs='?', default='power', choices=sorted(datalog.GOALS))
    gd.set_defaults(func=cmd_guide)
    ck = sub.add_parser('check-log', help='is a recorded log good enough for a goal? what to redo if not')
    ck.add_argument('log')
    ck.add_argument('--goal', default='power', choices=sorted(datalog.GOALS))
    ck.set_defaults(func=cmd_check_log)
    an = sub.add_parser('analyze', help='tuner-style analysis of a log or KTuner CSV export')
    an.add_argument('log')
    an.add_argument('--findings', action='store_true', help='only the plain-language findings')
    an.set_defaults(func=cmd_analyze)
    cp = sub.add_parser('compare', help='before/after comparison of two logs')
    cp.add_argument('before')
    cp.add_argument('after')
    cp.set_defaults(func=cmd_compare)
    tn = sub.add_parser('tune', help='inspect or edit a KTuner .kcl')
    tn.add_argument('action', choices=['check', 'tables', 'cells', 'set'])
    tn.add_argument('file')
    tn.add_argument('--match', help='cells: id pattern (e.g. ign-max-h-*) or text in the label/table')
    tn.add_argument('--set', action='append', metavar='ID=VALUE')
    tn.add_argument('--add', action='append', metavar='ID=DELTA')
    tn.add_argument('--scale', action='append', metavar='ID=FACTOR')
    tn.add_argument('-o', '--out')
    tn.add_argument('--note')
    tn.add_argument('--dry-run', action='store_true')
    tn.add_argument('--unverified', action='store_true',
                    help='apply the known table layout to a .kcl from an unverified family '
                         '(confirm the result in KTuner)')
    tn.set_defaults(func=cmd_tune)
    sg = sub.add_parser('suggest', help='AFM flow suggestions from two or more agreeing logs plus the tune')
    sg.add_argument('--tune', required=True)
    sg.add_argument('--unverified', action='store_true')
    sg.add_argument('logs', nargs='+')
    sg.set_defaults(func=cmd_suggest)
    sub.add_parser('platforms', help='bundled platforms and the channels decoded over USB').set_defaults(func=cmd_platforms)
    sub.add_parser('mcp', help='run the MCP server (stdio) for AI agents').set_defaults(func=cmd_mcp)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as error:
        emit({'error': str(error)})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
