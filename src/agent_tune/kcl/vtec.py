"""VTEC Settings: Lower Engage and Lower Disengage RPM, each stored in two linked places."""
import struct

from .common import u16, u16_deltas

GROUPS = {'vtec-lower-engage': (72929, 72933),
          'vtec-lower-disengage': (72931, 72935)}
LABELS = {'vtec-lower-engage': 'Lower Engage', 'vtec-lower-disengage': 'Lower Disengage'}
REGIONS = tuple((offset, offset + 2) for offsets in GROUPS.values() for offset in offsets)


def cells():
    return {name: {'table': 'VTEC Settings', 'offset': offsets[-1], 'linked_offsets': list(offsets),
                   'encoding': 'u16-le-linked', 'axis': {}, 'units': 'RPM', 'label': 'VTEC Settings / ' + LABELS[name],
                   'min': 0, 'max': 65535, 'step': 1}
            for name, offsets in GROUPS.items()}


def read(normalized, start):
    linked = {offset: struct.unpack_from('<H', normalized, offset - start)[0]
              for offsets in GROUPS.values() for offset in offsets}
    if any(len({linked[offset] for offset in offsets}) != 1 for offsets in GROUPS.values()):
        raise ValueError('VTEC linked fields differ; file not supported')
    return {name: linked[offsets[-1]] for name, offsets in GROUPS.items()}, linked


def deltas(name, target, linked):
    """Absolute byte deltas for both linked copies of `name`."""
    value = u16(target, 'VTEC RPM')
    changes = {}
    for offset in GROUPS[name]:
        changes.update({offset + i: d for i, d in u16_deltas(linked[offset], value).items()})
    return changes
