"""Own five-point recovery RPM observation; file positions are not ECU addresses."""
import struct
from .kcl_fuel_cut_min import counts, deltas, ECT_DISPLAY, CONTROLLED

OFFSET, END = 83439, 83449
EXCLUSIONS = ((OFFSET, END),)
READBACKS = ((1925, 2025), (1525, 1625), (1175, 1275), (1200, 1300), (1225, 1325))


def cell_id(index):
    return f'fuel-recover-ect-{ECT_DISPLAY[index]}'


def cells():
    return {cell_id(i): {
        'table': 'MAP Based Recover RPM', 'offset': OFFSET+2*i,
        'encoding': 'fuel-cut-u16-le', 'numeric_encoding_observed': True,
        'source_value': None, 'axis': {'ECT_display': ect},
        'axis_breakpoint_exact': False, 'row': 'RPM', 'units': 'RPM',
        'label': f'MAP Based Recover RPM / ECT display {ect}',
        'curve_id': 'fuel-recover', 'curve_index': i,
        'min': 0, 'max': 65535, 'step': 1,
        'location_evidence': 'two controlled edits + restore + independent readbacks'
            if i in CONTROLLED else 'two independent full-curve readbacks',
        'evidence': 'Two independent native readbacks; adjacent u16 byte carry',
        'independent_readback_targets': list(READBACKS[i])}
        for i, ect in enumerate(ECT_DISPLAY)}


def read(normalized, start):
    return {cell_id(i): struct.unpack_from('<H', normalized, OFFSET+2*i-start)[0]
            for i in range(len(ECT_DISPLAY))}


def metadata():
    return {'id': 'fuel-recover', 'table': 'MAP Based Recover RPM',
            'point_count': 5, 'encoding': 'u16-le', 'units': 'RPM',
            'axis_key': 'ECT_display', 'axis_label': 'ECT display',
            'axis_note': 'ECT labels observed in KTuner; stored axis and temperature unit unverified.',
            'axis_breakpoints_exact': False,
            'controlled_cells': [cell_id(i) for i in CONTROLLED],
            'all_points_independently_read_back': True,
            'all_points_controlled_in_ktuner': False,
            'ktuner_readback_required': True}
