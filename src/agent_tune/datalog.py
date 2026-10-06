"""How to record a useful datalog, and whether a recorded one is good enough.

`guide(goal)` explains, step by step, how to record and how to drive for a goal.
`check(log, goal)` tests a recorded log against that goal and says exactly what
to redo. It catches the usual problems: only idle in the log, a cold engine, no
full-throttle runs, runs in different gears or at very different intake
temperatures, and logs without knock data.
"""
import statistics

from .analyze import describe_pull, find_pulls

WARM_ECT_C = 75.0

CONNECT = ["Plug the KTuner dongle into the car's OBD port (under the dashboard) and into the laptop.",
           'Open the KTuner app and press Connect.',
           'Press Record (the red dot). Put the laptop somewhere safe: nobody touches it while the car is moving.']
EXPORT = ['Back in KTuner, press Record again to stop.',
          'Save the datalog, then choose Export Datalog To CSV.']
SAFE = 'Only on a closed course, a dyno, or a road where this is legal and safe. Keep to speed limits.'

GOALS = {
    'power': {
        'why': ('To tune for power you need to see what the engine does at full throttle: fuel, timing and '
                'knock. Three full-throttle runs show that.'),
        'minutes': 15,
        'before': CONNECT,
        'drive': ['Drive normally for about 10 minutes so the engine is fully warm.',
                  'In 2nd gear at about 2,000 rpm, press the accelerator all the way down.',
                  'Keep it down until the engine is close to the rev limit, then ease off.',
                  'Cruise gently for about a minute to let things cool a little.',
                  'Repeat until you have 3 runs, all in 2nd gear.'],
        'after': EXPORT,
    },
    'cruise': {
        'why': ("Steady driving shows how well the fueling matches the engine's airflow. It is the data for "
                'fuel trim and airflow (MAF) changes.'),
        'minutes': 20,
        'before': CONNECT,
        'drive': ['Drive normally for about 10 minutes so the engine is fully warm.',
                  'Hold steady speeds for at least 30 seconds each: about 25, 40, 50 and 65 mph '
                  '(40, 60, 80 and 100 km/h), where legal.',
                  'Add some gentle acceleration, and a hill if there is one nearby.',
                  'Keep driving like this for 15 to 20 minutes.'],
        'after': EXPORT + ['Do the same drive on another day too: suggestions need two drives that agree.'],
    },
    'baseline': {
        'why': 'A quick health check of the engine before you change anything.',
        'minutes': 12,
        'before': CONNECT,
        'drive': ['With the engine warm, let it idle for 2 minutes with the A/C off, then 1 minute with it on.',
                  'Drive normally for about 10 minutes: some city, some highway.'],
        'after': EXPORT,
    },
}
GOALS['compare'] = dict(GOALS['power'],
                        why='After flashing a change, repeat the same runs so the two logs can be compared fairly.',
                        drive=['Use the same road, the same gear and the same starting rpm as your first log, '
                               'ideally at a similar outside temperature.'] + GOALS['power']['drive'])

OTHER_WAY = ('On a Honda Civic 11th gen 2.0 L you can also record without the KTuner app: close KTuner, run '
             '`agent-tune log --seconds 900 -o drive.jsonl`, and drive the same plan. That log has no knock count '
             'yet, so use the KTuner recording for anything involving timing.')


def guide(goal='power'):
    if goal not in GOALS:
        raise ValueError(f'Unknown goal {goal!r}; choose one of: {", ".join(GOALS)}')
    plan = GOALS[goal]
    return {'goal': goal, 'why': plan['why'], 'about_minutes': plan['minutes'],
            'before_you_drive': plan['before'],
            'on_the_road': {'where': SAFE, 'steps': plan['drive']},
            'after_the_drive': plan['after'] + ['Give the CSV to your agent, or run: '
                                                f'agent-tune check-log your-log.csv --goal {goal}'],
            'other_way_to_record': OTHER_WAY,
            'safety': 'The driver never uses the laptop while driving. Full-throttle runs only where legal and safe.'}


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
                       'The recording has gaps. Check the USB cable and stop the laptop from going to sleep.',
                       required=False))
    ect = [r['ch']['ect_c'] for r in rows if 'ect_c' in r['ch']]
    if goal in ('power', 'compare', 'cruise'):
        items.append(_item('engine warm', ect and statistics.median(ect) >= WARM_ECT_C,
                           f'median coolant {statistics.median(ect):.0f} C' if ect else 'no coolant channel',
                           'Drive for about 10 minutes to warm the engine up before the runs.'))
    if goal in ('power', 'compare'):
        pulls = [describe_pull(p) for p in find_pulls(log)]
        good = [p for p in pulls if p['rpm_end'] - p['rpm_start'] >= 2500]
        items.append(_item('full-throttle runs', len(good) >= 3,
                           f'{len(good)} runs, each sweeping 2,500+ rpm ({len(pulls)} full-throttle moments in total)',
                           'Do 3 full-throttle runs in 2nd gear, from about 2,000 rpm to near the rev limit, '
                           'with the pedal all the way down the whole time.'))
        gears = {p['gear'] for p in good if p.get('gear') is not None}
        gear_detail = 'no runs to compare' if not good else f'gears {sorted(gears) or "not logged"}'
        items.append(_item('same gear', len(gears) <= 1, gear_detail,
                           'Do every run in the same gear so they can be compared.', required=False))
        iats = [p['iat_c_start_end'][0] for p in good if p.get('iat_c_start_end')]
        spread = max(iats) - min(iats) if len(iats) > 1 else 0
        items.append(_item('similar intake temperature', spread <= 10,
                           f'intake air spread {spread:.0f} C across runs' if len(iats) > 1 else 'fewer than 2 runs',
                           'Cruise gently for about a minute between runs.', required=False))
        items.append(_item('knock data', 'knock_count' in chans,
                           'knock count present' if 'knock_count' in chans else 'no knock count channel',
                           'Record with the KTuner app and export to CSV: timing changes need the knock count.',
                           required=False))
        items.append(_item('fuel data', {'afr', 'afr_cmd'} <= chans, 'measured and commanded AFR',
                           'The log needs LAM and LAM.CMD (KTuner) or the lambda channels (agent-tune log).'))
    if goal == 'cruise':
        closed = [r for r in rows if r['ch'].get('fuel_status') == 2 and 'rpm' in r['ch'] and 'map_kpa' in r['ch']]
        cells = {(int(r['ch']['rpm'] // 500), int(r['ch']['map_kpa'] // 15)) for r in closed}
        items.append(_item('steady driving coverage', len(closed) >= 2000 and len(cells) >= 6,
                           f'{len(closed)} closed-loop samples across {len(cells)} RPM/load areas',
                           'Drive longer at several steady speeds, with some gentle acceleration or a hill.'))
        items.append(_item('airflow channel', 'maf_hz' in chans, 'MAF frequency present' if 'maf_hz' in chans else 'missing',
                           'Record with KTuner (it logs MAF.Hz) or with agent-tune log.'))
    if goal == 'baseline':
        items.append(_item('long enough', log.duration_s >= 300, f'{log.duration_s / 60:.1f} minutes',
                           'Record at least 5 minutes, including idle and normal driving.'))
        rpm = [r['ch']['rpm'] for r in rows if 'rpm' in r['ch']]
        items.append(_item('engine running and driven', rpm and max(rpm) - min(rpm) >= 1000,
                           f'rpm {min(rpm):.0f}-{max(rpm):.0f}' if rpm else 'no rpm channel',
                           'Drive normally during the recording, not only idle.'))
    ready = all(i['ok'] for i in items if i['required'])
    fixes = [i['fix'] for i in items if not i['ok'] and i['fix']]
    optional = sum(1 for i in items if not i['ok'] and not i['required'])
    return {'log': log.name, 'goal': goal, 'ready': ready,
            'summary': ('Ready for analysis.' if ready else 'Not ready yet: record again with the fixes below.')
                       + (f' {optional} optional item(s) could be better.' if optional else ''),
            'checks': items, 'fixes': fixes}
