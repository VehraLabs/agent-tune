"""Suggestions that map log data onto tune cells, gated on enough agreeing evidence.

AFM flow (MAF calibration): per-sample fuel correction = measured/commanded AFR,
times total fuel trim in closed loop. A factor above 1 means the engine needed
more fuel than the airflow model predicted, i.e. the curve under-reads flow at
that frequency. Suggestions require agreement across sessions on different
days, because learned trims drift from day to day.
"""
import statistics

from .kcl import afm_curve

POLICY = {
    'min_samples': 20, 'min_span_s': 5.0, 'deadband_pct': 1.0, 'max_change_pct': 5.0, 'max_spread_pct': 8.0,
    'min_ect_c': 71.0, 'max_tps_rate_pct_s': 40.0, 'max_hz_rate_per_s': 4000.0,
    'min_sessions': 2, 'max_session_disagreement_pct': 3.0,
}
AXIS = {'base_hz': 2031.25, 'step_hz': 78.125, 'note': 'estimated from the rounded axis labels KTuner displays'}


def correction_samples(log, policy):
    rows = log.rows
    samples, excluded = [], {}

    def skip(reason):
        excluded[reason] = excluded.get(reason, 0) + 1
    for i, r in enumerate(rows):
        ch = r['ch']
        if ch.get('afr_ceiling'):
            skip('fuel_cut_or_ceiling'); continue
        if not all(k in ch for k in ('maf_hz', 'afr', 'afr_cmd', 'fuel_status')):
            skip('missing_channel'); continue
        if int(ch['fuel_status']) not in (1, 2):
            skip('not_open_or_closed_loop'); continue
        if 'ect_c' in ch and ch['ect_c'] < policy['min_ect_c']:
            skip('engine_not_warm'); continue
        if 0 < i < len(rows) - 1:
            a, b = rows[i - 1]['ch'], rows[i + 1]['ch']
            dt = rows[i + 1]['t'] - rows[i - 1]['t']
            if dt > 0 and 'tps_pct' in a and 'tps_pct' in b and abs(b['tps_pct'] - a['tps_pct']) / dt > policy['max_tps_rate_pct_s']:
                skip('throttle_transient'); continue
            if dt > 0 and 'maf_hz' in a and 'maf_hz' in b and abs(b['maf_hz'] - a['maf_hz']) / dt > policy['max_hz_rate_per_s']:
                skip('airflow_transient'); continue
        factor = ch['afr'] / ch['afr_cmd']
        if int(ch['fuel_status']) == 2:
            if 'stft_pct' not in ch or 'ltft_pct' not in ch:
                skip('missing_fuel_trims'); continue
            factor *= 1 + (ch['stft_pct'] + ch['ltft_pct']) / 100
        samples.append({'t': r['t'], 'hz': ch['maf_hz'], 'factor': factor})
    return samples, excluded


def afm(logs, curve, policy=None, axis=None):
    """Per-AFM-point suggestions; only points supported by enough agreeing sessions get a value."""
    policy = dict(POLICY, **(policy or {}))
    axis = dict(AXIS, **(axis or {}))
    buckets, excluded = {}, {}
    for n, log in enumerate(logs):
        found, skipped = correction_samples(log, policy)
        for k, v in skipped.items():
            excluded[k] = excluded.get(k, 0) + v
        for s in found:
            index = round((s['hz'] - axis['base_hz']) / axis['step_hz'])
            if 0 <= index < len(curve):
                buckets.setdefault(index, []).append((n, s))
    points = []
    for index, items in sorted(buckets.items()):
        factors = sorted(s['factor'] for _, s in items)
        median = statistics.median(factors)
        q = statistics.quantiles(factors, n=4) if len(factors) >= 4 else [factors[0], median, factors[-1]]
        reasons = []
        if len(items) < policy['min_samples']:
            reasons.append('insufficient_samples')
        if (q[2] - q[0]) * 100 > policy['max_spread_pct']:
            reasons.append('dispersion')
        per = {}
        for n, s in items:
            per.setdefault(n, []).append(s)
        medians = {logs[n].name: round((statistics.median(x['factor'] for x in v) - 1) * 100, 2) for n, v in per.items()
                   if len(v) >= policy['min_samples'] and v[-1]['t'] - v[0]['t'] >= policy['min_span_s']}
        if len(medians) < policy['min_sessions']:
            reasons.append('needs_more_sessions')
        elif max(medians.values()) - min(medians.values()) > policy['max_session_disagreement_pct']:
            reasons.append('sessions_disagree')
        change = (median - 1) * 100
        if not reasons and abs(change) < policy['deadband_pct']:
            reasons.append('within_deadband')
        clamped = max(-policy['max_change_pct'], min(policy['max_change_pct'], change))
        points.append({'id': afm_curve.cell_id(index), 'hz_estimate': axis['base_hz'] + axis['step_hz'] * index,
                       'samples': len(items), 'median_correction_pct': round(change, 2),
                       'per_session_pct': medians, 'current': curve[index],
                       'suggested': None if reasons else round(curve[index] * (1 + clamped / 100), 4),
                       'reasons': reasons})
    final = {p['id']: p['suggested'] for p in points if p['suggested'] is not None}
    ordered = [afm_curve.cell_id(i) for i in range(len(curve))]
    values = [final.get(cid, curve[i]) for i, cid in enumerate(ordered)]
    for p in points:  # keep the curve strictly increasing
        i = ordered.index(p['id'])
        if p['suggested'] is not None and ((i and values[i] <= values[i - 1]) or (i + 1 < len(values) and values[i] >= values[i + 1])):
            p['suggested'], p['reasons'] = None, p['reasons'] + ['would_break_increasing_curve']
    return {'table': 'AFM Flow', 'sessions': [l.name for l in logs], 'excluded_samples': excluded, 'axis': axis,
            'policy': policy, 'points': points,
            'changes': {p['id']: p['suggested'] for p in points if p['suggested'] is not None},
            'assumptions': ['AFM breakpoints are estimated from rounded KTuner labels.',
                            'Fuel delivery is assumed to scale with AFM flow.',
                            'Inputs are KTuner display values (or USB values matching them), not calibrated sensors.']}
