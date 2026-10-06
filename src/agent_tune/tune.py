"""Read and edit KTuner .kcl tune files (measured file families only).

Supported today: KTuner 1.0.14.1 saves for the Honda Civic 11th gen 2.0 L (64S
ECU, calibration 37805-64S-AC20 family). Other files are refused rather than
guessed. Writing creates a NEW file; the user opens it in KTuner, reviews it
there and flashes it with KTuner. This module never talks to a device.
"""
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path

from .kcl import kcl_observed_decode, patch_observed_kcl

MAX_INPUT = 16 * 1024 * 1024


def _read(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_INPUT:
        raise ValueError('File larger than 16 MiB')
    return data


def check(path):
    """Is this .kcl in a supported family? Never raises for unsupported files."""
    data = _read(path)
    digest = hashlib.sha256(data).hexdigest()
    try:
        kcl_observed_decode.decode(data)
    except ValueError as error:
        return {'file': str(path), 'sha256': digest, 'supported': False, 'reason': str(error)}
    return {'file': str(path), 'sha256': digest, 'supported': True,
            'family': 'Honda Civic 11th gen 2.0 L (64S), KTuner 1.0.14.1 save format',
            'editable_values': len(patch_observed_kcl.CELLS)}


def cells(path, pattern=None):
    """Editable values with current value, units, limits and table position."""
    values = kcl_observed_decode.decode(_read(path))['values']
    out = []
    for cell_id, meta in patch_observed_kcl.CELLS.items():
        if pattern and not (fnmatch(cell_id, pattern) or pattern.lower() in meta.get('label', cell_id).lower()
                            or pattern.lower() in meta.get('table', '').lower()):
            continue
        numeric = meta.get('numeric_encoding_observed', True)
        out.append({'id': cell_id, 'table': meta.get('table'), 'label': meta.get('label', meta.get('table', cell_id)),
                    'value': values.get(cell_id, meta.get('source_value')), 'units': meta.get('units'),
                    'row': meta.get('matrix_row'), 'column': meta.get('matrix_column'), 'axis': meta.get('axis'),
                    'choices': None if numeric else [0.5, 1.0, 1.5],
                    'evidence': meta.get('evidence') or meta.get('location_evidence')})
    return out


def tables(path):
    """Summary of editable tables: how many values each has and their value range."""
    summary = {}
    for c in cells(path):
        t = summary.setdefault(c['table'], {'table': c['table'], 'values': 0, 'min': None, 'max': None,
                                            'example_ids': []})
        t['values'] += 1
        v = c['value']
        if isinstance(v, (int, float)):
            t['min'] = v if t['min'] is None else min(t['min'], v)
            t['max'] = v if t['max'] is None else max(t['max'], v)
        if len(t['example_ids']) < 3:
            t['example_ids'].append(c['id'])
    return sorted(summary.values(), key=lambda t: t['table'])


def plan(path, set_values=None, add=None, scale=None):
    """Resolve absolute/relative/scaled edits (cell ids or glob patterns) to a cell->value plan."""
    current = {c['id']: c['value'] for c in cells(path)}
    result = {}

    def targets(pattern):
        hits = [cid for cid in current if fnmatch(cid, pattern)]
        if not hits:
            raise ValueError(f'No editable value matches {pattern!r}')
        return hits
    for pattern, value in (set_values or {}).items():
        for cid in targets(pattern):
            result[cid] = float(value)
    for pattern, delta in (add or {}).items():
        for cid in targets(pattern):
            result[cid] = round(result.get(cid, current[cid]) + float(delta), 6)
    for pattern, factor in (scale or {}).items():
        for cid in targets(pattern):
            result[cid] = round(result.get(cid, current[cid]) * float(factor), 6)
    return result


def write(path, changes, out_path, note=None):
    """Write a new .kcl with `changes` ({cell_id: value}) plus `<out>.manifest.json`."""
    path, out_path = Path(path), Path(out_path)
    if out_path.suffix.lower() != '.kcl':
        out_path = out_path.with_suffix('.kcl')
    if out_path.resolve() == path.resolve():
        raise ValueError('Refusing to overwrite the source tune; choose a new output file')
    if out_path.exists():
        raise ValueError(f'{out_path} already exists; choose a new output file')
    if not changes:
        raise ValueError('No changes requested')
    data = _read(path)
    output, manifest = patch_observed_kcl.generate(data, changes)
    verified = kcl_observed_decode.decode(output)['values']
    diff = []
    for edit in manifest['edits']:
        diff.append({'id': edit['cell'], 'label': edit.get('label'), 'from': edit.get('from'),
                     'requested': edit.get('to'), 'stored': verified[edit['cell']], 'units': edit.get('ui_units')})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(output)
    record = {'format': 'agent-tune.tune-change.v1', 'source_file': path.name,
              'source_sha256': hashlib.sha256(data).hexdigest(), 'output_file': out_path.name,
              'output_sha256': hashlib.sha256(output).hexdigest(), 'changes': diff, 'note': note,
              'next_steps': ['Open the output file in KTuner and review every changed value.',
                             'Keep your original tune file and a stock backup.',
                             'Flash with KTuner only with stable power; never interrupt a flash.',
                             'Log the same conditions afterwards and compare.'],
              'flashed_by_agent_tune': False}
    manifest_path = out_path.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return {'kcl': str(out_path), 'manifest': str(manifest_path), 'changes': diff}


def afm_curve(path):
    """AFM flow curve values (g/s) in breakpoint order."""
    from .kcl import kcl_afm_curve
    values = kcl_observed_decode.decode(_read(path))['values']
    return [values[kcl_afm_curve.cell_id(i)] for i in range(kcl_afm_curve.COUNT)]
