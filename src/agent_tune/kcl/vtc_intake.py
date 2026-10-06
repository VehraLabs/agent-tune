"""WOT Intake VTC tables, low cam and high cam, two CAM rows each.

Values are signed 16-bit, 10x the displayed degrees. Rows are 80 bytes apart;
the bytes between rows are left untouched.
"""
from .common import grid, read_scale10

RPM = (900, 1000, 1100, 1250, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000,
       4200, 4500, 5000, 5500, 6000, 6500, 6800)
ROW_STRIDE, COLUMN_STRIDE = 80, 2
TABLES = (('WOT Intake VTC Low Cam', 'vtc-intake-low', 107603), ('WOT Intake VTC High Cam', 'vtc-intake-high', 107563))
REGIONS = tuple((offset + row * ROW_STRIDE, offset + row * ROW_STRIDE + len(RPM) * COLUMN_STRIDE)
                for _, _, offset in TABLES for row in range(2))


def cells():
    out = {}
    for table, prefix, offset in TABLES:
        out.update(grid(table, lambda row, rpm, p=prefix: f'{p}-cam{row}-{rpm}', offset, (1, 2), RPM,
                        ROW_STRIDE, COLUMN_STRIDE, 'i16-le-scale10',
                        lambda row, rpm: {'RPM': rpm, 'CAM_row': row},
                        lambda row, rpm, t=table: f'{t} / CAM row {row} / RPM={rpm}'))
    return out


def read(normalized, start):
    return read_scale10(normalized, start, cells())
