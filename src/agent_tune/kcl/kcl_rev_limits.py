"""Own offline Rev Limits observations; linked fields are not ECU addresses."""
from decimal import Decimal, InvalidOperation
import struct

GROUPS = {'rev-high-limit':(77589,77593,77949),
          'rev-high-restart':(77597,77601,77961),
          'rev-low-limit':(77947,),
          'rev-low-restart':(77959,)}
EXCLUSIONS = tuple((offset,offset+2) for offsets in GROUPS.values() for offset in offsets)


def cells():
    return {name:{'table':'Rev Limits','offset':offsets[-1],
                  'linked_offsets':list(offsets),'encoding':'linked-u16-le',
                  'numeric_encoding_observed':True,'source_value':None,
                  'axis':{},'row':label,'units':'RPM','label':'Rev Limits / '+label,
                  'min':0,'max':65535,'step':1,
                  'location_evidence':'two controlled edits + restore + independent readbacks',
                  'evidence':'Two edits + restore + two independent readbacks' if name.startswith('rev-low-')
                      else 'Three linked writes; independently verified display location',
                  'independent_readback_targets':[6850,6950] if name=='rev-high-limit'
                      else [4650,4800] if name=='rev-low-limit'
                      else [4250,4150] if name=='rev-low-restart' else [6650,6550]}
            for (name,offsets),label in zip(GROUPS.items(),['High Limit','High Restart','Low Limit','Low Restart'])}


def read(normalized,start):
    linked={offset:struct.unpack_from('<H',normalized,offset-start)[0]
            for offsets in GROUPS.values() for offset in offsets}
    return {name:linked[offsets[-1]] for name,offsets in GROUPS.items()},linked


def counts(target):
    try:
        value=Decimal(str(target))
        if not value.is_finite() or value!=value.to_integral_value() or not 0<=value<=65535:
            raise ValueError('Rev value must be an integer fitting unsigned 16-bit RPM')
        return int(value)
    except InvalidOperation as error:
        raise ValueError('Invalid rev target') from error


def deltas(name,target,linked,synchronize_restart=False):
    if linked is None or any(offset not in linked for offsets in GROUPS.values() for offset in offsets):
        raise ValueError('Rev edits require all linked source values decoded from the file')
    desired={offset:counts(target) for offset in GROUPS[name]}
    if synchronize_restart:
        # High Limit UI edits also synchronize the two restart copies to its display.
        desired.update({offset:linked[GROUPS['rev-high-restart'][-1]]
                        for offset in GROUPS['rev-high-restart']})
    changes={}
    for offset,value in desired.items():
        old,new=struct.pack('<H',linked[offset]),struct.pack('<H',value)
        changes.update({offset+i:(b-a+128)%256-128 for i,(a,b) in enumerate(zip(old,new)) if a!=b})
    return changes
