"""Load logs into one shape: rows of {t, ch} with common channel names and units.

Sources:
  * agent-tune USB logs (`agent-tune log`), re-decoded from raw bytes
  * KTuner CSV exports (any KTuner-supported car; known columns mapped, others kept)
  * vehicle-lab decoded USB logs (A/B/C rows with raw payloads)

Units: rpm, kPa, g/s, Hz, %, degrees, deg C, km/h, V. AFR values at KTuner's 29.4
display ceiling (fuel cut or engine off) are removed and flagged `afr_ceiling`.
"""
from dataclasses import dataclass, field
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from . import telemetry

AFR_STOICH = 14.7
AFR_CEILING = 29.35
MAX_BYTES = 256 * 1024 * 1024

# KTuner CSV column -> (name, scale, bias)
KTUNER_COLUMNS = {
    'RPM': ('rpm', 1, 0), 'MAP(mBar)': ('map_kpa', 0.1, 0), 'MAF.Hz': ('maf_hz', 1, 0), 'MAF': ('maf_gs', 1, 0),
    'TPS': ('tps_pct', 1, 0), 'TPS.CMD': ('tps_cmd_pct', 1, 0), 'CAM.CMD': ('cam_cmd_deg', 1, 0),
    'CAMA': ('cam_deg', 1, 0), 'EXCAM.CMD': ('excam_cmd_deg', 1, 0), 'EXCAMA': ('excam_deg', 1, 0),
    'AIGN': ('ign_deg', 1, 0), 'FP1': ('fuel_pressure', 1, 0), 'STFT': ('stft_pct', 1, 0), 'LTFT': ('ltft_pct', 1, 0),
    'LAM': ('afr', 1, 0), 'LAM.CMD': ('afr_cmd', 1, 0), 'FUEL.STAT': ('fuel_status', 1, 0),
    'KNK.C': ('knock_count', 1, 0), 'KNK.CTRL': ('knock_ctrl', 1, 0), 'ECT(F)': ('ect_c', 5 / 9, -160 / 9),
    'IAT(F)': ('iat_c', 5 / 9, -160 / 9), 'VSS(MPH)': ('speed_kph', 1.609344, 0), 'GEAR': ('gear', 1, 0),
    'BAT': ('battery_v', 1, 0), 'VTEC': ('vtec', 1, 0),
}
UNITS = {'rpm': 'rpm', 'map_kpa': 'kPa', 'maf_hz': 'Hz', 'maf_gs': 'g/s', 'tps_pct': '%', 'tps_cmd_pct': '%',
         'cam_cmd_deg': 'deg', 'cam_deg': 'deg', 'excam_cmd_deg': 'deg', 'excam_deg': 'deg', 'ign_deg': 'deg',
         'stft_pct': '%', 'ltft_pct': '%', 'afr': 'AFR', 'afr_cmd': 'AFR', 'lambda': '', 'lambda_cmd': '',
         'fuel_status': 'enum', 'knock_count': 'count', 'knock_ctrl': '', 'ect_c': 'C', 'iat_c': 'C',
         'speed_kph': 'km/h', 'gear': '', 'battery_v': 'V', 'vtec': 'bool', 'fuel_pressure': ''}


@dataclass
class Log:
    name: str
    sha256: str
    source: str  # 'agent-tune-usb', 'ktuner-csv', 'vehicle-lab-usb'
    rows: list
    platform: str | None = None
    notes: list = field(default_factory=list)

    @property
    def duration_s(self):
        return self.rows[-1]['t'] - self.rows[0]['t'] if len(self.rows) > 1 else 0.0

    def channels(self):
        names = set()
        for r in self.rows[:5000]:
            names.update(r['ch'])
        return sorted(names)


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _finish(ch):
    """Derive AFR/lambda pairs and strip the 29.4 display ceiling."""
    if 'lambda_measured' in ch:
        ch['lambda'] = ch.pop('lambda_measured')
        ch['afr'] = ch['lambda'] * AFR_STOICH
    if 'lambda_commanded' in ch:
        ch['lambda_cmd'] = ch.pop('lambda_commanded')
        ch['afr_cmd'] = ch['lambda_cmd'] * AFR_STOICH
    if 'afr' in ch and 'lambda' not in ch:
        ch['lambda'] = ch['afr'] / AFR_STOICH
    if 'afr_cmd' in ch and 'lambda_cmd' not in ch:
        ch['lambda_cmd'] = ch['afr_cmd'] / AFR_STOICH
    if ch.get('afr', 0) >= AFR_CEILING or ch.get('afr_cmd', 0) >= AFR_CEILING:
        for key in ('afr', 'afr_cmd', 'lambda', 'lambda_cmd'):
            ch.pop(key, None)
        ch['afr_ceiling'] = 1
    return ch


def parse_ktuner_csv(data, name='log.csv'):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    header = reader.fieldnames or []
    if 'Time(s)' not in header or 'RPM' not in header:
        raise ValueError('Not a KTuner CSV export (needs Time(s) and RPM columns)')
    rows, previous = [], -math.inf
    for line, raw in enumerate(reader, 2):
        try:
            t = float(raw['Time(s)'])
        except (TypeError, ValueError):
            raise ValueError(f'Bad time at line {line}') from None
        if t < previous:
            raise ValueError(f'Time goes backwards at line {line}')
        previous = t
        ch = {}
        for column, value in raw.items():
            if column in (None, 'Time(s)') or value in (None, ''):
                continue
            try:
                number = float(value)
            except ValueError:
                continue
            if not math.isfinite(number):
                continue
            if column in KTUNER_COLUMNS:
                key, scale, bias = KTUNER_COLUMNS[column]
                ch[key] = number * scale + bias
            else:  # keep unknown columns (other platforms) under a safe name
                ch['ktuner_' + ''.join(c if c.isalnum() else '_' for c in column).strip('_').lower()] = number
        rows.append({'t': t, 'ch': _finish(ch)})
    if not rows:
        raise ValueError('CSV has no rows')
    return Log(name, hashlib.sha256(data).hexdigest(), 'ktuner-csv', rows,
               notes=['Values are KTuner display channels.'])


def parse_usb_log(data, name='log.jsonl'):
    lines = [json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip()]
    if not lines:
        raise ValueError('Empty log')
    header = lines[0] if lines[0].get('format') == 'agent-tune.log.v1' else None
    plat = header['platform'] if header else telemetry.DEFAULT_PLATFORM
    rows = []
    if header:
        for r in lines[1:]:
            groups = {k: bytes.fromhex(v) for k, v in (r.get('raw') or {}).items()}
            ch = telemetry.decode_groups(groups, plat) if groups else dict(r.get('ch', {}))
            rows.append({'t': float(r['t']), 'ch': _finish(ch)})
        source = 'agent-tune-usb'
    else:  # vehicle-lab format: one row per group, groups of one frame share t
        merged = {}
        for r in lines:
            if r.get('group') not in telemetry.GROUPS or not r.get('raw'):
                raise ValueError('Unrecognized JSONL log (expected agent-tune or vehicle-lab USB format)')
            merged.setdefault(r['t'], {})[r['group']] = bytes.fromhex(r['raw'])
        for t in sorted(merged):
            rows.append({'t': float(t), 'ch': _finish(telemetry.decode_groups(merged[t], plat))})
        source = 'vehicle-lab-usb'
    if any(b['t'] < a['t'] for a, b in zip(rows, rows[1:])):
        raise ValueError('Time goes backwards')
    return Log(name, hashlib.sha256(data).hexdigest(), source, rows, platform=plat,
               notes=['USB channels decode what KTuner displays (validated on the reference car).'])


def load(path):
    path = Path(path)
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError('Log larger than 256 MiB')
    head = data[:2048].decode('utf-8-sig', 'replace').lstrip()
    if head.startswith('Time(s)'):
        return parse_ktuner_csv(data, path.name)
    if head.startswith('{'):
        return parse_usb_log(data, path.name)
    raise ValueError(f'{path.name}: expected a KTuner CSV export or an agent-tune .jsonl log')


def series(log, name):
    """(t, value) pairs for one channel."""
    return [(r['t'], r['ch'][name]) for r in log.rows if _finite(r['ch'].get(name))]
