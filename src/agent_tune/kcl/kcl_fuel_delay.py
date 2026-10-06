"""Own offline delay display observations; CVT runtime gear meaning unverified."""
from decimal import Decimal, InvalidOperation
import struct

OFFSET, END = 80879, 80889
EXCLUSIONS = ((OFFSET, END),)
READBACKS = ((256, 257), (43, 53), (44, 54), (45, 55), (21, 22))
CONTROLLED = (0, 1, 4)


def cell_id(index):
    return f'fuel-delay-gear-{index+1}'


def cells():
    return {cell_id(i): {
        'table': 'Fuel Cut Delay', 'offset': OFFSET+2*i,
        'encoding': 'fuel-delay-u16-le', 'numeric_encoding_observed': True,
        'source_value': None, 'axis': {'Gear_display': i+1},
        'axis_breakpoint_exact': False, 'row': 'Delay', 'units': 'ms x10 (display)',
        'label': f'Fuel Cut Delay / Gear display {i+1}',
        'curve_id': 'fuel-delay', 'curve_index': i,
        'min': 0, 'max': 65535, 'step': 1,
        'location_evidence': 'two controlled edits + restore + independent readbacks'
            if i in CONTROLLED else 'two independent full-curve readbacks',
        'evidence': 'Two independent native readbacks; first point crosses byte boundary',
        'independent_readback_targets': list(READBACKS[i])}
        for i in range(5)}


def counts(target):
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 65535:
            raise ValueError('Delay display value must be an integer fitting unsigned 16-bit')
        return int(value)
    except InvalidOperation as error:
        raise ValueError('Invalid delay display value') from error


def deltas(offset, target, source):
    old, new = struct.pack('<H', counts(source)), struct.pack('<H', counts(target))
    return {offset+i: (b-a+128)%256-128 for i, (a, b) in enumerate(zip(old, new)) if a != b}


def read(normalized, start):
    return {cell_id(i): struct.unpack_from('<H', normalized, OFFSET+2*i-start)[0]
            for i in range(5)}


def metadata():
    return {'id': 'fuel-delay', 'table': 'Fuel Cut Delay',
            'point_count': 5, 'encoding': 'u16-le', 'units': 'ms x10 (display)',
            'axis_key': 'Gear_display', 'axis_label': 'Gear display',
            'axis_note': 'KTuner labels Gear 1..5 and Delay (ms x10); CVT runtime interpretation unverified.',
            'axis_breakpoints_exact': False,
            'controlled_cells': [cell_id(i) for i in CONTROLLED],
            'all_points_independently_read_back': True,
            'all_points_controlled_in_ktuner': False,
            'ktuner_readback_required': True}
