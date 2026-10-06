"""How to record a useful datalog, and whether a recorded one is good enough.

`guide(goal)` returns a recording plan: what to record with, how to drive, how
to export. `check(log, goal)` tests a recorded log against that goal and says
exactly what to redo. Common failures this catches: idle-only logs, a cold
engine, no full-throttle pulls, pulls in different gears or at very different
intake temperatures, and logs without knock data.
"""
import statistics

from .analyze import describe_pull, find_pulls

WARM_ECT_C = 75.0

RECORD_WITH = {
    'ktuner': {
        'when': 'Any car KTuner supports. Includes knock count, gear and cam angles. Use this for power and timing work.',
        'steps': ['Open KTuner with the dongle on the OBD port and press Connect.',
                  'Press Record (the red dot) before you start driving.',
                  'Drive the plan below. Do not touch the laptop while moving; a passenger can, or leave it running.',
                  'Press Record again to stop, then Save Datalog (.kdlg) and Export Datalog To CSV.',
                  'Give the CSV file to agent-tune (or your agent).'],
    },
    'agent-tune': {
        'when': 'Honda Civic 11th gen 2.0 L (64S). No knock count yet, so not for timing changes.',
        'steps': ['Close the KTuner app (it holds the port). Dongle on OBD, ignition ON.',
                  'Run: agent-tune log --seconds 900 -o drive.jsonl',
                  'Drive the plan below without touching the laptop. The log stops on its own.'],
    },
}

GOALS = {
    'power': {
        'purpose': 'Full-throttle data for timing, full-throttle fuel and cam decisions.',
        'record_with': 'ktuner',
        'drive': ['Only on a closed course, a dyno, or where it is legal and safe. Obey speed limits.',
                  'Warm up: drive normally for 10 minutes until coolant is at operating temperature.',
                  'Do 3 pulls in the same gear (2nd or 3rd): roll at about 2,000 rpm, then full throttle to near '
                  'the rev limit. Keep the pedal flat for the whole pull.',
                  'Between pulls, cruise gently for about 1 minute so intake temperature settles.',
                  'Stop recording after the last pull and cool-down.'],
        'minutes': 15,
    },
    'cruise': {
        'purpose': 'Steady driving for fuel trims and the airflow (AFM) curve.',
        'record_with': 'ktuner',
        'drive': ['Warm up for 10 minutes first.',
                  'Hold steady speeds for at least 30 seconds each: around 40, 60, 80 and 100 km/h, where legal.',
                  'Include gentle accelerations and some uphill or loaded driving.',
                  'Record for 15-20 minutes. Repeat on another day: suggestions need two sessions that agree.'],
        'minutes': 20,
    },
    'baseline': {
        'purpose': 'A general health check before changing anything.',
        'record_with': 'ktuner',
        'drive': ['Start the recording at a warm idle for 2 minutes with the A/C off, then on.',
                  'Drive normally for 10 minutes: city and some highway.'],
        'minutes': 12,
    },
}
GOALS['compare'] = dict(GOALS['power'], purpose='Before/after: repeat the exact power pulls after flashing a change.',
                        drive=GOALS['power']['drive'] + ['Use the same road, gear and starting RPM as the "before" log, '
                                                         'at a similar intake temperature.'])


def guide(goal='power'):
    if goal not in GOALS:
        raise ValueError(f'Unknown goal {goal!r}; choose one of: {", ".join(GOALS)}')
    plan = GOALS[goal]
    other = 'agent-tune' if plan['record_with'] == 'ktuner' else 'ktuner'
    return {'goal': goal, 'purpose': plan['purpose'], 'about_minutes': plan['minutes'],
            'record_with': {'recommended': plan['record_with'], **RECORD_WITH[plan['record_with']]},
            'alternative': {'method': other, **RECORD_WITH[other]},
            'drive': plan['drive'],
            'then': f'Run: agent-tune check <your log> --goal {goal}',
            'safety': 'The driver never operates the laptop while moving. Full-throttle runs only where legal and safe.'}


def _item(name, ok, detail, fix=None, required=True):
    return {'check': name, 'ok': bool(ok), 'required': required, 'detail': detail, 'fix': None if ok else fix}


def check(log, goal='power'):
    """Is this log good enough for `goal`? Lists each requirement and what to redo."""
    if goal not in GOALS:
        raise ValueError(f'Unknown goal {goal!r}; choose one of: {", ".join(GOALS)}')
    rows = log.rows
    chans = set(log.channels())
    items = []
    gaps = [b['t'] - a['t'] for a, b in zip(rows, rows[1:])]
    items.append(_item('continuous recording', not gaps or max(gaps) <= 2.0,
                       f'largest gap {max(gaps) if gaps else 0:.1f} s',
                       'The recording has gaps. Check the USB cable and keep the laptop awake.', required=False))
    ect = [r['ch']['ect_c'] for r in rows if 'ect_c' in r['ch']]
    if goal in ('power', 'compare', 'cruise'):
        items.append(_item('engine warm', ect and statistics.median(ect) >= WARM_ECT_C,
                           f'median coolant {statistics.median(ect):.0f} C' if ect else 'no coolant channel',
                           'Warm up for 10 minutes before recording the important part.'))
    if goal in ('power', 'compare'):
        pulls = [describe_pull(p) for p in find_pulls(log)]
        good = [p for p in pulls if p['rpm_end'] - p['rpm_start'] >= 2500]
        items.append(_item('full-throttle pulls', len(good) >= 3,
                           f'{len(good)} full pulls (TPS >= 80%, 2,500+ rpm sweep); {len(pulls)} full-throttle segments in total',
                           'Do 3 pulls in the same gear from about 2,000 rpm to near the rev limit, pedal flat the whole way.'))
        gears = {p['gear'] for p in good if p.get('gear') is not None}
        gear_detail = 'no pulls to compare' if not good else f'gears {sorted(gears) or "not logged"}'
        items.append(_item('same gear', len(gears) <= 1, gear_detail,
                           'Use one gear for every pull so they can be compared.', required=False))
        iats = [p['iat_c_start_end'][0] for p in good if p.get('iat_c_start_end')]
        spread = max(iats) - min(iats) if len(iats) > 1 else 0
        items.append(_item('similar intake temperature', spread <= 10,
                           f'intake air spread {spread:.0f} C across pulls' if len(iats) > 1 else 'fewer than 2 pulls',
                           'Cruise gently for a minute between pulls so intake temperature settles.', required=False))
        items.append(_item('knock data', 'knock_count' in chans,
                           'knock count present' if 'knock_count' in chans else 'no knock count channel',
                           'Record with the KTuner app and export to CSV; timing decisions need knock count.',
                           required=False))
        items.append(_item('fuel data', {'afr', 'afr_cmd'} <= chans, 'measured and commanded AFR',
                           'The log needs LAM and LAM.CMD (KTuner) or the lambda channels (agent-tune log).'))
    if goal == 'cruise':
        closed = [r for r in rows if r['ch'].get('fuel_status') == 2 and 'rpm' in r['ch'] and 'map_kpa' in r['ch']]
        cells = {(int(r['ch']['rpm'] // 500), int(r['ch']['map_kpa'] // 15)) for r in closed}
        items.append(_item('steady driving coverage', len(closed) >= 2000 and len(cells) >= 6,
                           f'{len(closed)} closed-loop samples across {len(cells)} RPM/load areas',
                           'Drive longer at several steady speeds, including some load (uphill or gentle acceleration).'))
        items.append(_item('airflow channel', 'maf_hz' in chans, 'MAF frequency present' if 'maf_hz' in chans else 'missing',
                           'Record with KTuner (MAF.Hz column) or agent-tune log.'))
    if goal == 'baseline':
        items.append(_item('long enough', log.duration_s >= 300, f'{log.duration_s / 60:.1f} minutes',
                           'Record at least 5 minutes, including idle and normal driving.'))
        rpm = [r['ch']['rpm'] for r in rows if 'rpm' in r['ch']]
        items.append(_item('engine running and driven', rpm and max(rpm) - min(rpm) >= 1000,
                           f'rpm {min(rpm):.0f}-{max(rpm):.0f}' if rpm else 'no rpm channel',
                           'Drive normally during the recording, not only idle.'))
    ready = all(i['ok'] for i in items if i['required'])
    fixes = [i['fix'] for i in items if not i['ok'] and i['fix']]
    return {'log': log.name, 'goal': goal, 'ready': ready,
            'summary': ('Ready for analysis.' if ready else 'Not ready: record again with the fixes below.')
                       + (f' {sum(1 for i in items if not i["ok"] and not i["required"])} optional item(s) to improve.'
                          if any(not i['ok'] and not i['required'] for i in items) else ''),
            'checks': items, 'fixes': fixes}
