"""Fuel cut tables: MAP Based Cut Minimum RPM, MAP Based Recover RPM, Fuel Cut Delay.

All values are plain unsigned 16-bit. Axis labels are what KTuner displays.
"""
import struct

ECT_DISPLAY = (86, 104, 122, 158, 176)
GEARS = (1, 2, 3, 4, 5)
TABLES = (  # (table, id prefix, offset, axis key, axis values, units)
    ('MAP Based Cut Minimum RPM', 'fuel-cut-min-ect', 83519, 'ECT_display', ECT_DISPLAY, 'RPM'),
    ('MAP Based Recover RPM', 'fuel-recover-ect', 83439, 'ECT_display', ECT_DISPLAY, 'RPM'),
    ('Fuel Cut Delay', 'fuel-delay-gear', 80879, 'Gear_display', GEARS, 'ms x10 (display)'),
)
REGIONS = tuple((offset, offset + 2 * len(axis)) for _, _, offset, _, axis, _ in TABLES)


def cells():
    out = {}
    for table, prefix, offset, key, axis, units in TABLES:
        for i, point in enumerate(axis):
            out[f'{prefix}-{point}'] = {'table': table, 'offset': offset + 2 * i, 'encoding': 'u16-le',
                                        'axis': {key: point}, 'units': units, 'curve_index': i,
                                        'label': f'{table} / {key.replace("_", " ")} {point}',
                                        'min': 0, 'max': 65535, 'step': 1}
    return out


def read(normalized, start):
    return {name: struct.unpack_from('<H', normalized, cell['offset'] - start)[0] for name, cell in cells().items()}
