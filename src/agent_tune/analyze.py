"""Tuner-style analysis of a log: pulls, knock, fueling, timing, heat.

Output is plain data (JSON-serializable) so an AI agent or a person can reason
over it. Findings state the evidence they rest on; nothing here edits a tune.
"""
import math
import statistics

from .logs import series

WOT_TPS = 80.0           # % throttle treated as full throttle
MIN_PULL_S = 1.0
RPM_BIN = 500
POWER_AFR_RANGE = (12.5, 13.2)  # common NA gasoline full-throttle target band (guidance, not a rule)


def _stats(values):
    if not values:
        return None
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values), 'n': len(values)}


def _bin(rpm):
    return int(rpm // RPM_BIN * RPM_BIN)


def overview(log):
    out = {'name': log.name, 'source': log.source, 'platform': log.platform, 'sha256': log.sha256,
           'rows': len(log.rows), 'duration_s': round(log.duration_s, 2), 'channels': {}}
    for name in log.channels():
        values = [v for _, v in series(log, name)]
        if values:
            out['channels'][name] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in _stats(values).items()}
    out['afr_ceiling_rows'] = sum(1 for r in log.rows if r['ch'].get('afr_ceiling'))
    return out


def find_pulls(log, min_s=MIN_PULL_S):
    """Contiguous full-throttle segments with rising RPM."""
    pulls, current = [], []
    for r in log.rows:
        if r['ch'].get('tps_pct', 0) >= WOT_TPS and 'rpm' in r['ch']:
            current.append(r)
            continue
        if current:
            pulls.append(current)
            current = []
    if current:
        pulls.append(current)
    out = []
    for rows in pulls:
        if rows[-1]['t'] - rows[0]['t'] < min_s or rows[-1]['ch']['rpm'] - rows[0]['ch']['rpm'] < 500:
            continue
        out.append(rows)
    return out


def describe_pull(rows):
    t0, t1 = rows[0]['t'], rows[-1]['t']
    bins = {}
    for a, b in zip(rows, rows[1:]):
        dt = b['t'] - a['t']
        if dt <= 0:
            continue
        key = _bin(a['ch']['rpm'])
        entry = bins.setdefault(key, {'rpm_rate': [], 'afr': [], 'afr_cmd': [], 'ign_deg': [], 'knock_ctrl': [],
                                      'map_kpa': [], 'cam_deg': []})
        entry['rpm_rate'].append((b['ch']['rpm'] - a['ch']['rpm']) / dt)
        for k in ('afr', 'afr_cmd', 'ign_deg', 'knock_ctrl', 'map_kpa', 'cam_deg'):
            if k in a['ch']:
                entry[k].append(a['ch'][k])
    by_rpm = []
    for key in sorted(bins):
        e = bins[key]
        by_rpm.append({'rpm_bin': key, **{k: round(statistics.median(v), 3) for k, v in e.items() if v}})
    knock_counts = [r['ch']['knock_count'] for r in rows if 'knock_count' in r['ch']]
    afr = [r['ch']['afr'] for r in rows if 'afr' in r['ch']]
    iat = [r['ch']['iat_c'] for r in rows if 'iat_c' in r['ch']]
    return {'start_s': round(t0, 2), 'duration_s': round(t1 - t0, 2),
            'rpm_start': rows[0]['ch']['rpm'], 'rpm_end': rows[-1]['ch']['rpm'],
            'gear': rows[0]['ch'].get('gear'),
            'afr': _stats(afr), 'iat_c_start_end': [iat[0], iat[-1]] if iat else None,
            'knock_count_increase': (max(knock_counts) - min(knock_counts)) if knock_counts else None,
            'by_rpm': by_rpm,
            'rpm_rate_note': 'RPM rise rate in the same gear is a relative power proxy for before/after comparisons.'}


def knock_events(log):
    """Knock count increments and knock-control drops, with where they happened."""
    events = []
    prev = None
    for r in log.rows:
        ch = r['ch']
        if prev is not None:
            if 'knock_count' in ch and 'knock_count' in prev['ch'] and ch['knock_count'] > prev['ch']['knock_count']:
                events.append({'t': r['t'], 'kind': 'knock_count', 'delta': ch['knock_count'] - prev['ch']['knock_count'],
                               'rpm': ch.get('rpm'), 'map_kpa': ch.get('map_kpa'), 'ign_deg': ch.get('ign_deg'),
                               'tps_pct': ch.get('tps_pct')})
            if 'knock_ctrl' in ch and 'knock_ctrl' in prev['ch'] and prev['ch']['knock_ctrl'] - ch['knock_ctrl'] >= 0.02:
                events.append({'t': r['t'], 'kind': 'knock_ctrl_drop', 'delta': round(ch['knock_ctrl'] - prev['ch']['knock_ctrl'], 4),
                               'rpm': ch.get('rpm'), 'map_kpa': ch.get('map_kpa'), 'ign_deg': ch.get('ign_deg'),
                               'tps_pct': ch.get('tps_pct')})
        prev = r
    return events


def fuel_trims(log, rpm_edges=(0, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 6000, 8000),
               map_edges=(0, 30, 45, 60, 75, 90, 110)):
    """Median total fuel trim (STFT+LTFT) in closed loop by RPM x MAP cell."""
    cells = {}
    for r in log.rows:
        ch = r['ch']
        if ch.get('fuel_status') != 2 or not all(k in ch for k in ('rpm', 'map_kpa', 'stft_pct', 'ltft_pct')):
            continue
        ri = next((i for i in range(len(rpm_edges) - 1) if rpm_edges[i] <= ch['rpm'] < rpm_edges[i + 1]), None)
        mi = next((i for i in range(len(map_edges) - 1) if map_edges[i] <= ch['map_kpa'] < map_edges[i + 1]), None)
        if ri is None or mi is None:
            continue
        cells.setdefault((ri, mi), []).append(ch['stft_pct'] + ch['ltft_pct'])
    return [{'rpm': [rpm_edges[ri], rpm_edges[ri + 1]], 'map_kpa': [map_edges[mi], map_edges[mi + 1]],
             'median_total_trim_pct': round(statistics.median(v), 2), 'samples': len(v)}
            for (ri, mi), v in sorted(cells.items()) if len(v) >= 20]


def analyze(log):
    over = overview(log)
    pulls = [describe_pull(p) for p in find_pulls(log)]
    knocks = knock_events(log)
    trims = fuel_trims(log)
    findings = []
    chans = over['channels']
    if not pulls:
        findings.append({'topic': 'power', 'level': 'info',
                         'text': 'No full-throttle pulls (TPS >= 80% for 1 s with rising RPM). Power tuning decisions '
                                 '(timing, WOT fueling, cam) need repeatable full-throttle pulls in the same gear.'})
    for i, p in enumerate(pulls, 1):
        if p['afr']:
            med = p['afr']['median']
            band = POWER_AFR_RANGE
            if med < band[0]:
                findings.append({'topic': 'wot_fueling', 'level': 'note', 'pull': i,
                                 'text': f'Pull {i}: median AFR {med:.2f} is richer than the common NA power band '
                                         f'{band[0]}-{band[1]}. Leaning toward the band can add power; change in small steps '
                                         'and confirm knock stays absent.'})
            elif med > band[1]:
                findings.append({'topic': 'wot_fueling', 'level': 'warn', 'pull': i,
                                 'text': f'Pull {i}: median AFR {med:.2f} is leaner than {band[1]} at full throttle. '
                                         'Lean full-throttle mixtures raise knock and temperature risk; do not add timing here.'})
        if p['knock_count_increase']:
            findings.append({'topic': 'knock', 'level': 'warn', 'pull': i,
                             'text': f"Pull {i}: knock count rose by {p['knock_count_increase']}. Do not add timing in the "
                                     'affected RPM range; consider removing some.'})
    count_events = [e for e in knocks if e['kind'] == 'knock_count']
    if count_events:
        rpms = sorted({_bin(e['rpm']) for e in count_events if e['rpm'] is not None})
        findings.append({'topic': 'knock', 'level': 'warn',
                         'text': f'{len(count_events)} knock-count increments, RPM bins {rpms}.'})
    elif 'knock_count' in chans:
        findings.append({'topic': 'knock', 'level': 'info', 'text': 'Knock count never increased in this log.'})
    if 'knock_count' not in chans:
        findings.append({'topic': 'knock', 'level': 'info',
                         'text': 'This log has no knock count channel (USB logs on the reference platform do not decode it yet; '
                                 'KTuner CSV exports include KNK.C). Use a KTuner CSV for timing decisions.'})
    big = [c for c in trims if abs(c['median_total_trim_pct']) >= 8]
    if big:
        findings.append({'topic': 'fueling', 'level': 'note',
                         'text': f'{len(big)} closed-loop cells with total trim beyond +-8%: the ECU is correcting airflow '
                                 'there. Check across several days before changing the airflow (MAF) calibration; trims drift.'})
    if 'iat_c' in chans and chans['iat_c']['max'] >= 60:
        findings.append({'topic': 'heat', 'level': 'note',
                         'text': f"Intake air reached {chans['iat_c']['max']:.0f} C. Hot intake air reduces power and "
                                 'knock margin; compare pulls at similar intake temperatures.'})
    return {'overview': over, 'pulls': pulls, 'knock_events': knocks[:200], 'fuel_trims': trims, 'findings': findings,
            'disclaimer': 'Evidence summary only. Changes are made by the user in KTuner (or via agent-tune tune set) and '
                          'flashed by the user in KTuner.'}


def compare(before, after):
    """Side-by-side of two analyses: pulls by RPM bin, AFR, timing and knock."""
    a, b = analyze(before), analyze(after)

    def pull_table(result):
        table = {}
        for p in result['pulls']:
            for row in p['by_rpm']:
                table.setdefault(row['rpm_bin'], []).append(row)
        return {k: {m: statistics.median(r[m] for r in rows if m in r) for m in ('rpm_rate', 'afr', 'ign_deg', 'knock_ctrl')
                    if any(m in r for r in rows)} for k, rows in table.items()}
    ta, tb = pull_table(a), pull_table(b)
    rows = []
    for rpm in sorted(set(ta) & set(tb)):
        row = {'rpm_bin': rpm}
        for m in ('rpm_rate', 'afr', 'ign_deg', 'knock_ctrl'):
            if m in ta[rpm] and m in tb[rpm]:
                row[m] = {'before': round(ta[rpm][m], 3), 'after': round(tb[rpm][m], 3),
                          'change': round(tb[rpm][m] - ta[rpm][m], 3)}
        rows.append(row)
    knock = {'before': sum(1 for e in a['knock_events'] if e['kind'] == 'knock_count'),
             'after': sum(1 for e in b['knock_events'] if e['kind'] == 'knock_count')}
    return {'before': a['overview']['name'], 'after': b['overview']['name'],
            'pulls': {'before': len(a['pulls']), 'after': len(b['pulls'])}, 'by_rpm': rows, 'knock_count_events': knock,
            'note': 'Compare pulls in the same gear and at similar intake temperature; a higher rpm_rate means faster '
                    'acceleration (more power) under the same conditions.'}
