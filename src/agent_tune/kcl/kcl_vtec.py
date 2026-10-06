"""Own offline VTEC threshold observations; file offsets are not ECU addresses."""
from decimal import Decimal, InvalidOperation
import struct

GROUPS = {'vtec-lower-engage': (72929, 72933),
          'vtec-lower-disengage': (72931, 72935)}
EXCLUSIONS = tuple((offset, offset+2) for offsets in GROUPS.values() for offset in offsets)


def cells():
    return {name: {'table': 'VTEC Settings', 'offset': offsets[-1],
                   'linked_offsets': list(offsets), 'encoding': 'vtec-linked-u16-le',
                   'numeric_encoding_observed': True, 'source_value': None,
                   'axis': {}, 'row': label, 'units': 'RPM',
                   'label': 'VTEC Settings / '+label, 'min': 0, 'max': 65535, 'step': 1,
                   'location_evidence': 'two controlled edits + restore + independent readbacks',
                   'evidence': 'Two linked fields; two edits, restore and independent readbacks',
                   'independent_readback_targets': [5350, 5450] if name=='vtec-lower-engage' else [5050, 5150]}
            for (name, offsets), label in zip(GROUPS.items(), ['Lower Engage', 'Lower Disengage'])}


def read(normalized, start):
    linked = {offset: struct.unpack_from('<H', normalized, offset-start)[0]
              for offsets in GROUPS.values() for offset in offsets}
    if any(len({linked[offset] for offset in offsets}) != 1 for offsets in GROUPS.values()):
        raise ValueError('Unsupported differing VTEC linked source fields')
    return {name: linked[offsets[-1]] for name, offsets in GROUPS.items()}, linked


def counts(target):
    try:
        value = Decimal(str(target))
        if isinstance(target, bool) or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 65535:
            raise ValueError('VTEC target must be an integer fitting unsigned 16-bit RPM')
        return int(value)
    except InvalidOperation as error:
        raise ValueError('Invalid VTEC target') from error


def deltas(name, target, linked):
    if linked is None or any(offset not in linked for offsets in GROUPS.values() for offset in offsets):
        raise ValueError('VTEC edits require all linked source values decoded from the file')
    if any(len({linked[offset] for offset in offsets}) != 1 for offsets in GROUPS.values()):
        raise ValueError('Unsupported differing VTEC linked source fields')
    desired = struct.pack('<H', counts(target))
    return {offset+i: (new-old+128)%256-128
            for offset in GROUPS[name]
            for i, (old, new) in enumerate(zip(struct.pack('<H', linked[offset]), desired))
            if old != new}
