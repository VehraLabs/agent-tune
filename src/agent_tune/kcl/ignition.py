"""Ignition Base and Ignition Maximum tables (map 0), low-cam (L) and high-cam (H).

Values are signed 16-bit, 10x the displayed degrees. Column labels are the
load / EGR values KTuner displays; the stored breakpoints are not decoded.
"""
from .common import grid, read_scale10

RPM = (500, 650, 800, 1000, 1250, 1500, 1750, 2000, 2250, 2500, 3000, 3500,
       4000, 4200, 4500, 5000, 5500, 6000, 6500, 6800)
LOAD = (131, 197, 263, 394, 526, 592, 657, 723, 789, 921, 1052, 1184)
EGR = (0, 30, 50, 80, 100, 150, 200, 250, 300, 350)
ROW_STRIDE, COLUMN_STRIDE = 2, 40
TABLES = (  # (table, id prefix, branch, offset, columns, column axis label)
    ('Ignition Base', 'ign-base-l', 'L', 410515, LOAD, 'Load_display'),
    ('Ignition Base', 'ign-base-h', 'H', 409715, LOAD, 'Load_display'),
    ('Ignition Maximum', 'ign-max-l', 'L', 193267, EGR, 'EGR_display'),
    ('Ignition Maximum', 'ign-max-h', 'H', 192867, EGR, 'EGR_display'),
)
REGIONS = tuple((offset, offset + len(columns) * COLUMN_STRIDE) for _, _, _, offset, columns, _ in TABLES)


def cells():
    out = {}
    for table, prefix, branch, offset, columns, column_key in TABLES:
        out.update(grid(table, lambda rpm, col, p=prefix: f'{p}-{rpm}-{col}', offset, RPM, columns,
                        ROW_STRIDE, COLUMN_STRIDE, 'i16-le-scale10',
                        lambda rpm, col, b=branch, k=column_key: {'RPM': rpm, k: col, 'branch': b, 'map_selector': 0},
                        lambda rpm, col, t=table, b=branch, k=column_key: f'{t} / {b}, map 0 / RPM={rpm}, {k.replace("_", " ")}={col}'))
    return out


def read(normalized, start):
    return read_scale10(normalized, start, cells())
