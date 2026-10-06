"""MAP based cam cut and recover pressure tables (low cam and high cam).

Values are unsigned 16-bit counts; the displayed pressure is count / 7.6 mBar.
Entered values are truncated to a count, so unchanged cells keep their exact
stored bytes rather than being re-encoded from the rounded display value.
"""
from decimal import Decimal, InvalidOperation
import struct

SCALE = Decimal('7.6')
TABLES = (  # (table, id prefix, offset, RPM axis)
    ('MAP Based Low Cam Cut', 'fuel-map-low-cut', 80057, (1500, 3000, 5000, 6500)),
    ('MAP Based Low Cam Recover', 'fuel-map-low-recover', 80065, (1500, 3000, 5000, 6500)),
    ('MAP Based High Cam Cut', 'fuel-map-high-cut', 80073, (2000, 3000, 3500, 6500)),
    ('MAP Based High Cam Recover', 'fuel-map-high-recover', 80081, (2000, 3000, 3500, 6500)),
)
REGIONS = tuple((offset, offset + 2 * len(rpms)) for _, _, offset, rpms in TABLES)


def cells():
    out = {}
    for table, prefix, offset, rpms in TABLES:
        for i, rpm in enumerate(rpms):
            out[f'{prefix}-rpm-{rpm}'] = {'table': table, 'offset': offset + 2 * i, 'encoding': 'u16-le-mbar',
                                          'axis': {'RPM_display': rpm}, 'units': 'mBar', 'curve_index': i,
                                          'label': f'{table} / RPM display {rpm}', 'min': 0, 'max': 8623.1, 'step': 0.1}
    return out


def counts(target):
    """Stored count for an entered mBar value (truncated, as KTuner stores it)."""
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or value < 0:
            raise ValueError('Pressure must be a non-negative number')
        result = int(value * SCALE)
        if result > 65535:
            raise ValueError('Pressure is too large to store')
        return result
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Invalid pressure value') from error


def read(normalized, start):
    """(displayed values, stored counts) for every cell."""
    raw = {name: struct.unpack_from('<H', normalized, cell['offset'] - start)[0] for name, cell in cells().items()}
    return {name: count / 7.6 for name, count in raw.items()}, raw
