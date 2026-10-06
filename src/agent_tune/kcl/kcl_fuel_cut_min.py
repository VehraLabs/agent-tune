"""Own five-point offline fuel-cut observation; offsets are not ECU addresses."""
from decimal import Decimal, InvalidOperation
import struct

OFFSET, END = 83519, 83529
ECT_DISPLAY = (86, 104, 122, 158, 176)
CONTROLLED = (0, 1, 4)
EXCLUSIONS = ((OFFSET, END),)


def cell_id(index):
    return f'fuel-cut-min-ect-{ECT_DISPLAY[index]}'


def cells():
    return {cell_id(i): {
        'table': 'MAP Based Cut Minimum RPM', 'offset': OFFSET + 2*i,
        'encoding': 'fuel-cut-u16-le', 'numeric_encoding_observed': True,
        'source_value': None, 'axis': {'ECT_display': ect},
        'axis_breakpoint_exact': False, 'row': 'RPM', 'units': 'RPM',
        'label': f'MAP Based Cut Minimum RPM / ECT display {ect}',
        'curve_id': 'fuel-cut-min', 'curve_index': i,
        'min': 0, 'max': 65535, 'step': 1,
        'location_evidence': 'two controlled edits + restore + independent readbacks'
            if i in CONTROLLED else 'two independent full-curve readbacks',
        'evidence': 'Two independent native readbacks; exact file byte isolation',
        'independent_readback_targets': [2225, 2325] if i == 0 else
            [1825, 1925] if i == 1 else [1375, 1475] if i == 2 else
            [1400, 1500] if i == 3 else [1425, 1525]}
        for i, ect in enumerate(ECT_DISPLAY)}


def counts(target):
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 65535:
            raise ValueError('Fuel-cut RPM must be an integer fitting unsigned 16-bit')
        return int(value)
    except InvalidOperation as error:
        raise ValueError('Invalid fuel-cut RPM') from error


def deltas(offset, target, source):
    old, new = struct.pack('<H', counts(source)), struct.pack('<H', counts(target))
    return {offset+i: (b-a+128)%256-128 for i, (a, b) in enumerate(zip(old, new)) if a != b}


def read(normalized, start):
    return {cell_id(i): struct.unpack_from('<H', normalized, OFFSET+2*i-start)[0]
            for i in range(len(ECT_DISPLAY))}


def metadata():
    return {'id': 'fuel-cut-min', 'table': 'MAP Based Cut Minimum RPM',
            'point_count': 5, 'encoding': 'u16-le', 'units': 'RPM',
            'axis_key': 'ECT_display', 'axis_label': 'ECT display',
            'axis_note': 'ECT labels observed in KTuner; stored axis and temperature unit unverified.',
            'axis_breakpoints_exact': False,
            'controlled_cells': [cell_id(i) for i in CONTROLLED],
            'all_points_independently_read_back': True,
            'all_points_controlled_in_ktuner': False,
            'ktuner_readback_required': True}
