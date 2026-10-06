"""Write a new .kcl with changed cell values.

Changes are applied as byte deltas to the decoded body, which is then
re-compressed into a copy of the original header. The result is decoded again
and every changed cell is checked before anything is returned. Nothing here
talks to a device.
"""
from decimal import Decimal
import gzip
import hashlib

from . import afm_curve, cylinder_trim, map_cut, rev_limits, vtec, wot
from .common import scale10_deltas, u16, u16_deltas
from .decode import TABLE_MODULES, decode
from .envelope import GZIP_OFFSET, inspect

CELLS = {}
for _module in TABLE_MODULES:
    CELLS.update(_module.cells())


def _number(target):
    if isinstance(target, bool) or not isinstance(target, (str, int, float)):
        raise ValueError('Each target must be a number')
    return float(Decimal(str(target)))


def plan_changes(plan, decoded):
    """Turn {cell_id: target} into byte deltas, using the decoded source file for current values."""
    if not isinstance(plan, dict) or not plan or set(plan) - set(CELLS):
        raise ValueError('Plan must map known cell ids to values')
    values = decoded['values']
    if set(plan) & {'rev-high-limit', 'rev-high-restart'}:
        high = u16(plan.get('rev-high-limit', values['rev-high-limit']))
        restart = u16(plan.get('rev-high-restart', values['rev-high-restart']))
        if restart >= high:
            raise ValueError('High Restart must be below High Limit')
    if set(plan) & set(vtec.GROUPS):
        engage = u16(plan.get('vtec-lower-engage', values['vtec-lower-engage']))
        disengage = u16(plan.get('vtec-lower-disengage', values['vtec-lower-disengage']))
        if disengage >= engage:
            raise ValueError('Lower Disengage must be below Lower Engage')
    changes, edits = {}, []
    for name, target in plan.items():
        cell, source, encoding = CELLS[name], values[name], CELLS[name]['encoding']
        count, synchronize_restart = None, False
        if encoding == 'u16-le-trim':
            value = _number(target)
            count = decoded['trim_counts'][name] if value == source else cylinder_trim.counts(target)
            effective = cylinder_trim.value(count)
            local = u16_deltas(decoded['trim_counts'][name], count)
        elif encoding == 'u16-le-mbar':
            value = _number(target)
            count = decoded['map_counts'][name] if value == source else map_cut.counts(target)
            effective = count / 7.6
            local = u16_deltas(decoded['map_counts'][name], count)
        elif encoding == 'u16-le':
            value = effective = u16(target, cell['label'])
            local = u16_deltas(u16(source), value)
        elif encoding == 'u16-le-linked':
            value = effective = u16(target, cell['label'])
            if name in vtec.GROUPS:
                local = vtec.deltas(name, value, decoded['vtec_linked'])
            else:
                synchronize_restart = name == 'rev-high-limit' and 'rev-high-restart' not in plan
                local = rev_limits.deltas(name, value, decoded['rev_linked'], synchronize_restart)
        elif encoding == 'u8-reciprocal':
            local, effective, count = wot.encode(target, source)
            value = _number(target)
        elif encoding == 'float32-le':
            local, effective = afm_curve.encode(target, source)
            value = _number(target)
        else:  # i16-le-scale10
            local = scale10_deltas(target, source)
            value = effective = _number(target)
        if cell.get('choices') and value not in cell['choices']:
            raise ValueError(f"{cell['label']} accepts only {cell['choices']}")
        relocated = local if encoding == 'u16-le-linked' else {cell['offset'] + i: d for i, d in local.items()}
        if changes.keys() & relocated.keys():
            raise ValueError('Overlapping edits')
        changes.update(relocated)
        edits.append({'cell': name, 'table': cell['table'], 'label': cell['label'], 'axis': cell['axis'],
                      'from': source, 'to': value, 'encoded_value': effective, 'ui_units': cell['units'],
                      'encoded_storage_count': count, 'decoded_byte_deltas': relocated,
                      'linked_offsets': cell.get('linked_offsets'), 'restart_copies_synchronized': synchronize_restart})
    return changes, edits


def patch_bytes(data, changes, expected_sha256):
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('Source file changed; no edit performed')
    metadata = inspect(data)
    payload = bytearray(gzip.decompress(data[GZIP_OFFSET:]))
    for offset, delta in changes.items():
        if not 0 <= offset < len(payload):
            raise ValueError('Offset outside decoded body')
        payload[offset] = (payload[offset] + delta) % 256
    packed = gzip.compress(payload, mtime=0)
    header = bytearray(data[:GZIP_OFFSET])
    header[31:35] = len(packed).to_bytes(4, 'big')
    output = bytes(header) + packed
    if inspect(output)['decoded_size'] != metadata['decoded_size']:
        raise ValueError('Repacked size mismatch')
    return output


def generate(data, plan, allow_unverified=False):
    """New file bytes and a manifest of edits, checked by decoding the result again."""
    decoded = decode(data, allow_unverified)
    changes, edits = plan_changes(plan, decoded)
    output = patch_bytes(data, changes, decoded['input_sha256'])
    verified = decode(output, allow_unverified)
    for edit in edits:
        if verified['values'][edit['cell']] != edit['encoded_value']:
            raise ValueError('Output did not decode to the intended value')
        linked = verified['vtec_linked'] if edit['cell'] in vtec.GROUPS else verified['rev_linked']
        if edit['linked_offsets'] and any(linked[offset] != edit['encoded_value'] for offset in edit['linked_offsets']):
            raise ValueError('Output did not update all linked fields')
        if edit['restart_copies_synchronized']:
            restart = verified['values']['rev-high-restart']
            if any(verified['rev_linked'][offset] != restart for offset in rev_limits.GROUPS['rev-high-restart']):
                raise ValueError('Output did not synchronize restart copies')
    manifest = {'source_sha256': decoded['input_sha256'], 'family_sha256': decoded['family_sha256'],
                'family': decoded['family'], 'verified_family': decoded['verified'],
                'output_sha256': hashlib.sha256(output).hexdigest(), 'edits': edits,
                'decoded_bytes_changed': len(changes)}
    return output, manifest
