"""ECT Ignition correction cells at the ECT=104 column.

The low table cell is a normal 0.1-degree value. The high table cell has only
been confirmed for 0.5, 1.0 and 1.5, so only those are accepted.
"""
from .common import read_scale10

CELLS = {
    'ect-low-104': {'table': 'ECT Ignition Low', 'offset': 80145, 'encoding': 'i16-le-scale10',
                    'axis': {'ECT_display': 104}, 'units': None, 'label': 'ECT Ignition Low / ECT display 104 / Corr'},
    'ect-high-104': {'table': 'ECT Ignition High', 'offset': 83405, 'encoding': 'i16-le-scale10',
                     'axis': {'ECT_display': 104}, 'units': None, 'label': 'ECT Ignition High / ECT display 104 / Corr',
                     'choices': [0.5, 1.0, 1.5]},
}
REGIONS = ((80143, 80147), (83405, 83407))


def cells():
    return {name: dict(cell) for name, cell in CELLS.items()}


def read(normalized, start):
    return read_scale10(normalized, start, CELLS)
