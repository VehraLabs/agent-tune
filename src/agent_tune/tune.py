"""Read and edit KTuner .kcl tune files.

Verified today: KTuner 1.0.14.1 saves for the Honda Civic 11th gen 2.0 L (64S
ECU, 37805-64S-AC20 calibration). Other files are refused by default. With
`allow_unverified` the same layout is tried anyway so owners of other cars can
check whether it fits and confirm the result in KTuner. Writing always creates
a new file; the owner opens it in KTuner, reviews it and flashes it themselves.
This module never talks to a device.
"""
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path

from .kcl import decode, patch

MAX_INPUT = 16 * 1024 * 1024
UNVERIFIED_WARNING = ('This file is not from a verified family. The known table layout was applied without confirmation. '
                      'Open the new file in KTuner and confirm that exactly the intended cells changed before doing anything '
                      'else with it. If they did, please report it so the family can be added.')


def _read(path):
    data = Path(path).read_bytes()
    if len(data) > MAX_INPUT:
        raise ValueError('File larger than 16 MiB')
    return data


def check(path):
    """Is this .kcl supported? Never raises for unsupported files.

    For files outside the verified families, reports whether the known layout decodes
    plausibly so the owner can decide whether to try it with `allow_unverified`.
    """
    data = _read(path)
    digest = hashlib.sha256(data).hexdigest()
    try:
        decoded = decode.decode(data, allow_unverified=True)
    except ValueError as error:
        return {'file': str(path), 'sha256': digest, 'supported': False, 'reason': str(error)}
    result = {'file': str(path), 'sha256': digest, 'supported': decoded['verified'], 'family': decoded['family'],
              'editable_values': len(patch.CELLS)}
    if not decoded['verified']:
        result.update({'reason': 'Not a verified file family', 'layout_plausible': decoded['plausible'],
                       'checks': decoded['checks'],
                       'next': ('All checks pass: you can try the known layout with allow_unverified / --unverified and '
                                'confirm a single changed value in KTuner. See CONTRIBUTING.md to get the family verified.'
                                if decoded['plausible'] else
                                'Some checks fail: the known layout probably does not fit this file. Only KTuner CSV '
                                'analysis is available for this car for now.')})
    return result


def cells(path, pattern=None, allow_unverified=False):
    """Editable values with current value, units, limits and table position."""
    values = decode.decode(_read(path), allow_unverified)['values']
    out = []
    for cell_id, meta in patch.CELLS.items():
        if pattern and not (fnmatch(cell_id, pattern) or pattern.lower() in meta['label'].lower()
                            or pattern.lower() in meta['table'].lower()):
            continue
        out.append({'id': cell_id, 'table': meta['table'], 'label': meta['label'], 'value': values[cell_id],
                    'units': meta['units'], 'row': meta.get('matrix_row'), 'column': meta.get('matrix_column'),
                    'axis': meta['axis'], 'choices': meta.get('choices')})
    return out


def tables(path, allow_unverified=False):
    """Summary of editable tables: how many values each has and their value range."""
    summary = {}
    for c in cells(path, allow_unverified=allow_unverified):
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


def plan(path, set_values=None, add=None, scale=None, allow_unverified=False):
    """Resolve absolute/relative/scaled edits (cell ids or glob patterns) to a cell->value plan."""
    current = {c['id']: c['value'] for c in cells(path, allow_unverified=allow_unverified)}
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


def write(path, changes, out_path, note=None, allow_unverified=False):
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
    output, manifest = patch.generate(data, changes, allow_unverified)
    verified = decode.decode(output, allow_unverified)['values']
    diff = []
    for edit in manifest['edits']:
        diff.append({'id': edit['cell'], 'label': edit['label'], 'from': edit['from'], 'requested': edit['to'],
                     'stored': verified[edit['cell']], 'units': edit['ui_units']})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(output)
    next_steps = ['Open the output file in KTuner and review every changed value.',
                  'Keep your original tune file and a stock backup.',
                  'Flash with KTuner only with stable power; never interrupt a flash.',
                  'Log the same conditions afterwards and compare.']
    if not manifest['verified_family']:
        next_steps.insert(0, UNVERIFIED_WARNING)
    record = {'format': 'agent-tune.tune-change.v1', 'source_file': path.name,
              'source_sha256': hashlib.sha256(data).hexdigest(), 'output_file': out_path.name,
              'output_sha256': hashlib.sha256(output).hexdigest(), 'family': manifest['family'],
              'verified_family': manifest['verified_family'], 'changes': diff, 'note': note,
              'next_steps': next_steps, 'flashed_by_agent_tune': False}
    manifest_path = out_path.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    result = {'kcl': str(out_path), 'manifest': str(manifest_path), 'changes': diff}
    if not manifest['verified_family']:
        result['warning'] = UNVERIFIED_WARNING
    return result


def afm_curve(path, allow_unverified=False):
    """AFM flow curve values (g/s) in breakpoint order."""
    from .kcl import afm_curve as curve
    values = decode.decode(_read(path), allow_unverified)['values']
    return [values[curve.cell_id(i)] for i in range(curve.COUNT)]
