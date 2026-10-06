"""AFM Flow curve: 103 float32 points in g/s.

The frequency of each point is estimated from KTuner's rounded axis labels
(2031.25 Hz plus 78.125 Hz per point); the stored breakpoints are not decoded.
"""
from decimal import Decimal, InvalidOperation
import math
import struct

from .common import deltas

OFFSET, COUNT, STRIDE = 407401, 103, 4
BASE_HZ, STEP_HZ = 2031.25, 78.125
REGIONS = ((OFFSET, OFFSET + COUNT * STRIDE),)


def cell_id(index):
    if index == 0:
        return 'afm-flow-first'
    if index == 1:
        return 'afm-flow-second'
    return f'afm-flow-point-{index:03d}'


def cells():
    return {cell_id(i): {'table': 'AFM Flow', 'offset': OFFSET + i * STRIDE, 'encoding': 'float32-le',
                         'axis': {'column_index': i, 'Hz_estimate': BASE_HZ + STEP_HZ * i}, 'units': 'g/s',
                         'label': f'AFM Flow / point {i} / g/s', 'curve_index': i, 'step': 'any'}
            for i in range(COUNT)}


def encode(target, source):
    """Byte deltas (keyed 0-3) and the value float32 actually stores."""
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not Decimal(0) <= value <= Decimal('3.4028234663852886e38'):
            raise ValueError('AFM value must be a non-negative number that fits float32')
        packed = struct.pack('<f', float(value))
        effective = struct.unpack('<f', packed)[0]
        if not math.isfinite(effective) or (value != 0 and effective == 0):
            raise ValueError('AFM value overflows or underflows float32')
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('AFM value must be a non-negative number that fits float32') from error
    return deltas(struct.pack('<f', source), packed), effective


def read(normalized, start):
    result = {cell_id(i): struct.unpack_from('<f', normalized, OFFSET + i * STRIDE - start)[0] for i in range(COUNT)}
    if any(not math.isfinite(v) or v < 0 for v in result.values()):
        raise ValueError('AFM Flow curve contains an invalid value')
    return result
