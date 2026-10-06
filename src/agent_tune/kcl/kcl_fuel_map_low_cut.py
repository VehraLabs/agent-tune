"""Own offline MAP low-cam cut observations; exact source counts required.

Exact source counts are retained independently of displayed pressure values.
Reopened KTuner display rounding remains unverified beyond recorded controls.
"""
from decimal import Decimal, InvalidOperation
import struct

OFFSET, END = 80057, 80065
RPM_DISPLAY = (1500, 3000, 5000, 6500)
READBACKS = ((150, 200), (170, 220), (180, 230), (200, 250))
SCALE = Decimal('7.6')
EXCLUSIONS = ((OFFSET, END),)


def cell_id(index):
    return f'fuel-map-low-cut-rpm-{RPM_DISPLAY[index]}'


def cells():
    return {cell_id(i): {
        'table': 'MAP Based Low Cam Cut', 'offset': OFFSET+2*i,
        'encoding': 'pressure-count-u16-le', 'numeric_encoding_observed': True,
        'source_value': None, 'axis': {'RPM_display': rpm},
        'axis_breakpoint_exact': False, 'row': 'Pressure', 'units': 'mBar',
        'label': f'MAP Based Low Cam Cut / RPM display {rpm}',
        'curve_id': 'fuel-map-low-cut', 'curve_index': i,
        'min': 0, 'max': 8623.1, 'step': 0.1,
        'evidence': 'Own controls and two independent full-curve native readbacks; exact source counts retained',
        'independent_readback_targets': list(READBACKS[i]),
        'quantization': 'truncate entered mBar * 7.6; baseline shown as exact count / 7.6, not KTuner rounded display'}
        for i, rpm in enumerate(RPM_DISPLAY)}


def read(normalized, start):
    raw = {cell_id(i): value for i, value in enumerate(read_counts(normalized, start))}
    return {name: value/7.6 for name, value in raw.items()}, raw


def metadata():
    return {'id': 'fuel-map-low-cut', 'table': 'MAP Based Low Cam Cut',
            'point_count': 4, 'units': 'mBar', 'axis_key': 'RPM_display',
            'axis_label': 'RPM display', 'axis_breakpoints_exact': False,
            'axis_note': 'Baseline is exact stored count / 7.6. KTuner rounds its display; unchanged values retain exact bytes.',
            'controlled_cells': [cell_id(i) for i in (0, 1, 3)],
            'all_points_independently_read_back': True,
            'ktuner_readback_required': True}


def counts(target):
    """Encode an entered mBar value using the measured truncation model."""
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or value < 0:
            raise ValueError('Pressure must be a finite nonnegative number')
        result = int(value * SCALE)
        if result > 65535:
            raise ValueError('Pressure does not fit unsigned 16-bit storage')
        return result
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Invalid pressure value') from error


def raw_deltas(offset, target_count, source_count):
    """Patch exact counts; also supports byte-exact restoration of a source."""
    if offset not in range(OFFSET, END, 2):
        raise ValueError('Unobserved pressure cell offset')
    for value in (source_count, target_count):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
            raise ValueError('Stored pressure count must be an unsigned 16-bit integer')
    old, new = struct.pack('<H', source_count), struct.pack('<H', target_count)
    return {offset+i: (b-a+128)%256-128
            for i, (a, b) in enumerate(zip(old, new)) if a != b}


def deltas(offset, target, source_count):
    return raw_deltas(offset, counts(target), source_count)


def read_counts(normalized, start):
    return struct.unpack_from('<4H', normalized, OFFSET-start)
