"""Own measured cylinder trim file fields; offline only, not ECU addresses."""
from decimal import Decimal, InvalidOperation
import struct
OFFSET, END = 85053, 85061
EXCLUSIONS = ((OFFSET, END),)
def cell_id(i): return f'cylinder-trim-{i+1}'
def cells():
    return {cell_id(i):dict(table='Cylinder Fuel Trim',offset=OFFSET+2*i,
        encoding='trim-u16-le',numeric_encoding_observed=True,source_value=None,
        axis={'Cylinder':i+1},axis_breakpoint_exact=True,row='Trim',units=None,
        label=f'Cylinder Fuel Trim / cylinder {i+1}',min=-1,max=2,step=0.1,
        evidence='Two edits and zero restore per cylinder; two full-four independent native readbacks',
        independent_readback_targets=([-1,2],[1,1.5],[1.5,1],[2,-1])[i],
        quantization='truncate(32768 * (1 + entered trim / 100)); decoded source is exact inverse, unchanged values retain raw counts') for i in range(4)}
def counts(target):
    try:
        value=Decimal(str(target))
        if isinstance(target,bool) or not value.is_finite() or not Decimal(-1)<=value<=Decimal(2):
            raise ValueError('Trim must be finite within measured range -1 through 2')
        return int(Decimal(32768)*(1+value/100))
    except (InvalidOperation,OverflowError) as error: raise ValueError('Invalid trim') from error
def value(count): return (count-32768)*100/32768
def read(normalized,start):
    raw={cell_id(i):n for i,n in enumerate(struct.unpack_from('<4H',normalized,OFFSET-start))}
    return {name:value(n) for name,n in raw.items()},raw
def raw_deltas(offset,target,source):
    if offset not in range(OFFSET,END,2): raise ValueError('Unobserved trim offset')
    for n in (target,source):
        if isinstance(n,bool) or not isinstance(n,int) or not 0<=n<=65535: raise ValueError('Invalid trim count')
    return {offset+i:(b-a+128)%256-128 for i,(a,b) in enumerate(zip(struct.pack('<H',source),struct.pack('<H',target))) if a!=b}
