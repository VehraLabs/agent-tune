"""Own observed Maximum L/map0 layout; display axes, not ECU ROM addresses."""
import struct
from .kcl_ignition_map import RPM

OFFSET=193267
EGR=(0,30,50,80,100,150,200,250,300,350)
ROW_STRIDE,COLUMN_STRIDE=2,40
END=OFFSET+len(EGR)*COLUMN_STRIDE
CONTROLLED={(500,0),(650,0),(500,30)}
READBACKS={(500,0):[-0.5,25.6],(1500,100):[25.5,25.0],(6800,350):[59.5,59.0]}

def cell_id(rpm,egr):
    return f'ign-max-l-{rpm}-{egr}'

def cells():
    result={}
    for row,rpm in enumerate(RPM):
        for column,egr in enumerate(EGR):
            controlled=(rpm,egr) in CONTROLLED
            result[cell_id(rpm,egr)]={
                'table':'Ignition Maximum','offset':OFFSET+row*2+column*40,
                'numeric_encoding_observed':True,'encoding':'i16-le-scale10',
                'source_value':None,'axis':{'RPM':rpm,'EGR_display':egr,'branch':'L','map_selector':0},
                'axis_breakpoint_exact':False,'row':'Ignition value','units':None,
                'label':f'Ignition Maximum / L, map 0 / RPM={rpm}, EGR display={egr}',
                'matrix_id':'ign-max-l-0','matrix_row':row,'matrix_column':column,
                'location_evidence':'two controlled edits and restore' if controlled else 'inferred from measured table geometry',
                'evidence':'Two edits + restore' if controlled else 'Layout inferred; readback required',
                'independent_readback_targets':READBACKS.get((rpm,egr),[])}
    return result

def read(normalized,start):
    return {name:struct.unpack_from('<h',normalized,cell['offset']-start)[0]/10
            for name,cell in cells().items()}

def metadata():
    return {'id':'ign-max-l-0','table':'Ignition Maximum','branch':'L','selector':0,
            'rpm_display':RPM,'column_display':EGR,'column_axis_label':'EGR display',
            'units':None,'axis_breakpoints_exact':False,'row_stride':2,
            'column_stride':40,'storage':'column-major',
            'controlled_cells':[cell_id(rpm,egr) for rpm,egr in sorted(CONTROLLED)],
            'all_cells_individually_reproduced':False,'ktuner_readback_required':True}
