"""Own observed Ignition Base H/map0 geometry, not an ECU ROM definition.

Axes are display labels read from our offline editor. Load units and exact
breakpoints remain unresolved. Values are read from the user's file, never
bundled here. Local stride is supported by adjacent controlled edits.
"""
import struct

OFFSET = 409715
RPM = (500,650,800,1000,1250,1500,1750,2000,2250,2500,3000,3500,
       4000,4200,4500,5000,5500,6000,6500,6800)
LOAD = (131,197,263,394,526,592,657,723,789,921,1052,1184)
ROW_STRIDE, COLUMN_STRIDE = 2, 40
END = OFFSET + len(LOAD)*COLUMN_STRIDE
CONTROLLED = {(500,131),(650,131),(500,197)}
READBACKS = {(500,131):[25.6,-0.5],(1500,526):[28.5,28],(6800,1184):[8.5,8]}


def cell_id(rpm,load):
    return f'ign-base-h-{rpm}-{load}'


def cells():
    result = {}
    for row,rpm in enumerate(RPM):
        for column,load in enumerate(LOAD):
            controlled = (rpm,load) in CONTROLLED
            result[cell_id(rpm,load)] = {
                'table':'Ignition Base','offset':OFFSET+row*ROW_STRIDE+column*COLUMN_STRIDE,
                'numeric_encoding_observed':True,'encoding':'i16-le-scale10',
                'source_value':None,'axis':{'RPM':rpm,'Load_display':load,'branch':'H','map_selector':0},
                'axis_breakpoint_exact':False,'row':'Ignition value','units':None,
                'label':f'Ignition Base / H, map 0 / RPM={rpm}, Load display={load}',
                'matrix_id':'ign-base-h-0','matrix_row':row,'matrix_column':column,
                'location_evidence':'two controlled edits and restore' if controlled else 'inferred from measured table geometry',
                'evidence':'Two edits + restore' if controlled else 'Two independent target readbacks' if (rpm,load) in READBACKS else 'Layout inferred; readback required',
                'independent_readback_targets':READBACKS.get((rpm,load),[])}
    return result


def read(normalized,start):
    return {name:struct.unpack_from('<h',normalized,cell['offset']-start)[0]/10
            for name,cell in cells().items()}


def metadata():
    return {'id':'ign-base-h-0','table':'Ignition Base','branch':'H','selector':0,
            'rpm_display':RPM,'load_display':LOAD,'column_display':LOAD,'column_axis_label':'Load display','units':None,
            'axis_breakpoints_exact':False,'row_stride':ROW_STRIDE,
            'column_stride':COLUMN_STRIDE,'storage':'column-major',
            'controlled_cells':[cell_id(rpm,load) for rpm,load in sorted(CONTROLLED)],
            'all_cells_individually_reproduced':False,
            'ktuner_readback_required':True}
