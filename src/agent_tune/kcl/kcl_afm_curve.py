"""Own measured103-point AFM curve, not an ECU ROM definition.

Two synthetic sequences were independently read at every point in KTuner.
Frequency estimates follow displayed labels; exact stored axes remain unknown.
Only two previously published local scalar defaults are retained for compatibility;
full source curves are read from the user file.
"""
import math
import struct

OFFSET, COUNT, STRIDE = 407401, 103, 4
END = OFFSET + COUNT * STRIDE
CONTROLLED = {0, 1, 2, 52, 102}


def cell_id(index):
    if index == 0:
        return 'afm-flow-first'
    if index == 1:
        return 'afm-flow-second'
    return f'afm-flow-point-{index:03d}'


def cells():
    return {cell_id(i): {
        'table':'AFM Flow', 'offset':OFFSET + i * STRIDE,
        'numeric_encoding_observed':True, 'encoding':'float32-le',
        'source_value':0.5591 if i == 0 else 0.9621 if i == 1 else None, 'axis':{'column_index':i,
            'Hz_estimate':2031.25 + 78.125 * i},
        'axis_breakpoint_exact':False, 'row':'g/s', 'units':'g/s',
        'label':f'AFM Flow / point {i} / g/s',
        'curve_id':'afm-flow', 'curve_index':i, 'step':'any',
        'location_evidence':'two controlled edits and restore' if i in CONTROLLED
            else 'two independent full-curve readbacks',
        'evidence':'Two controlled edits + restore + two curve readbacks' if i in CONTROLLED
            else 'Two independent curve readbacks',
        'independent_readback_targets':[5 + i, 10 + 2 * i]}
        for i in range(COUNT)}


def read(normalized, start):
    result = {cell_id(i):struct.unpack_from('<f',normalized,OFFSET + i * STRIDE - start)[0]
              for i in range(COUNT)}
    if any(not math.isfinite(v) or v < 0 for v in result.values()):
        raise ValueError('Invalid observed AFM curve value')
    return result


def metadata():
    return {'id':'afm-flow','table':'AFM Flow','point_count':COUNT,
            'stride':STRIDE,'encoding':'float32-le','units':'g/s',
            'axis_estimate_formula':'2031.25 + 78.125 * index Hz',
            'axis_breakpoints_exact':False,
            'controlled_cells':[cell_id(i) for i in sorted(CONTROLLED)],
            'all_points_independently_read_back':True,
            'all_points_controlled_in_ktuner':False,
            'ktuner_readback_required':True}
