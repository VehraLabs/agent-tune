"""Rev Limits: High/Low Limit and Restart RPM.

Each high value is stored in several linked places that KTuner keeps equal;
all copies are updated together. Editing High Limit without High Restart also
rewrites the restart copies, as KTuner does.
"""
import struct

from .common import u16, u16_deltas

GROUPS = {'rev-high-limit': (77589, 77593, 77949),
          'rev-high-restart': (77597, 77601, 77961),
          'rev-low-limit': (77947,),
          'rev-low-restart': (77959,)}
LABELS = {'rev-high-limit': 'High Limit', 'rev-high-restart': 'High Restart',
          'rev-low-limit': 'Low Limit', 'rev-low-restart': 'Low Restart'}
REGIONS = tuple((offset, offset + 2) for offsets in GROUPS.values() for offset in offsets)


def cells():
    return {name: {'table': 'Rev Limits', 'offset': offsets[-1], 'linked_offsets': list(offsets),
                   'encoding': 'u16-le-linked', 'axis': {}, 'units': 'RPM', 'label': 'Rev Limits / ' + LABELS[name],
                   'min': 0, 'max': 65535, 'step': 1}
            for name, offsets in GROUPS.items()}


def read(normalized, start):
    linked = {offset: struct.unpack_from('<H', normalized, offset - start)[0]
              for offsets in GROUPS.values() for offset in offsets}
    return {name: linked[offsets[-1]] for name, offsets in GROUPS.items()}, linked


def deltas(name, target, linked, synchronize_restart=False):
    """Absolute byte deltas for every linked copy of `name`."""
    desired = {offset: u16(target, 'Rev limit') for offset in GROUPS[name]}
    if synchronize_restart:
        desired.update({offset: linked[GROUPS['rev-high-restart'][-1]] for offset in GROUPS['rev-high-restart']})
    changes = {}
    for offset, value in desired.items():
        changes.update({offset + i: d for i, d in u16_deltas(linked[offset], value).items()})
    return changes
