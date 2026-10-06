"""Helpers shared by the .kcl table modules."""
from decimal import Decimal, InvalidOperation
import struct


def deltas(old, new):
    """Signed per-byte difference between two equal-length byte strings, keyed by index.

    Unchanged bytes are omitted. Patching adds these deltas to the stored bytes.
    """
    return {i: (b - a + 128) % 256 - 128 for i, (a, b) in enumerate(zip(old, new)) if a != b}


def u16(target, what='value'):
    """Validate a whole number that must fit an unsigned 16-bit field."""
    try:
        value = Decimal(str(target))
    except InvalidOperation as error:
        raise ValueError(f'Invalid {what}') from error
    if isinstance(target, bool) or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 65535:
        raise ValueError(f'{what} must be a whole number between 0 and 65535')
    return int(value)


def u16_deltas(source_count, target_count):
    return deltas(struct.pack('<H', source_count), struct.pack('<H', target_count))


def scale10_deltas(target, source):
    """Byte deltas for a signed 16-bit little-endian value stored at 10x (0.1 resolution)."""
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not Decimal('-3276.8') <= value <= Decimal('3276.7'):
            raise ValueError('Value must be between -3276.8 and 3276.7')
        counts = value * 10
        if counts != counts.to_integral_value():
            raise ValueError('Value must be a multiple of 0.1')
        target_bytes = int(counts).to_bytes(2, 'little', signed=True)
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Value must be between -3276.8 and 3276.7') from error
    source_bytes = int(Decimal(str(source)) * 10).to_bytes(2, 'little', signed=True)
    return deltas(source_bytes, target_bytes)


def read_scale10(normalized, start, cells):
    return {name: struct.unpack_from('<h', normalized, cell['offset'] - start)[0] / 10 for name, cell in cells.items()}


def grid(table, cell_id, offset, rows, columns, row_stride, column_stride, encoding, axis, label, units=None):
    """Cells of a two-dimensional table laid out with the given strides."""
    out = {}
    for r, row in enumerate(rows):
        for c, column in enumerate(columns):
            out[cell_id(row, column)] = {'table': table, 'offset': offset + r * row_stride + c * column_stride,
                                         'encoding': encoding, 'axis': axis(row, column), 'units': units,
                                         'label': label(row, column), 'matrix_row': r, 'matrix_column': c}
    return out
