"""Cylinder Fuel Trim, four cylinders.

Stored as unsigned 16-bit counts: 32768 * (1 + trim / 100), truncated. The
displayed trim is the exact inverse, so unchanged cells keep their stored bytes.
"""
from decimal import Decimal, InvalidOperation
import struct

OFFSET, CYLINDERS = 85053, 4
REGIONS = ((OFFSET, OFFSET + 2 * CYLINDERS),)


def cell_id(i):
    return f'cylinder-trim-{i + 1}'


def cells():
    return {cell_id(i): {'table': 'Cylinder Fuel Trim', 'offset': OFFSET + 2 * i, 'encoding': 'u16-le-trim',
                         'axis': {'Cylinder': i + 1}, 'units': None, 'label': f'Cylinder Fuel Trim / cylinder {i + 1}',
                         'min': -1, 'max': 2, 'step': 0.1}
            for i in range(CYLINDERS)}


def counts(target):
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or not Decimal(-1) <= value <= Decimal(2):
            raise ValueError('Trim must be between -1 and 2')
        return int(Decimal(32768) * (1 + value / 100))
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Invalid trim') from error


def value(count):
    return (count - 32768) * 100 / 32768


def read(normalized, start):
    """(displayed trims, stored counts) for every cylinder."""
    raw = {cell_id(i): n for i, n in enumerate(struct.unpack_from(f'<{CYLINDERS}H', normalized, OFFSET - start))}
    return {name: value(n) for name, n in raw.items()}, raw
