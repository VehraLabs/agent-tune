"""Own offline low-cam intake VTC geometry; no ECU addresses or bundled values."""
import struct

OFFSET = 107603
RPM = (900,1000,1100,1250,1500,1750,2000,2250,2500,3000,3500,4000,
       4200,4500,5000,5500,6000,6500,6800)
ROW_STRIDE, COLUMN_STRIDE = 80, 2
EXCLUSIONS = tuple((OFFSET+row*ROW_STRIDE,OFFSET+row*ROW_STRIDE+len(RPM)*2)
                   for row in range(2))
CONTROLLED = {(0,900),(0,1000),(0,6800),(1,900),(1,6800)}
READBACKS = {(0,900):[2.5,25.6,-1],(0,1000):[11.5,12.5],
             (0,6800):[6.5,7.5],(1,900):[2.5,3.5],(1,6800):[6.5,7.5]}


def cell_id(row,rpm):
    return f'vtc-intake-low-cam{row+1}-{rpm}'


def cells():
    return {cell_id(row,rpm):{
        'table':'WOT Intake VTC Low Cam','offset':OFFSET+row*ROW_STRIDE+column*2,
        'numeric_encoding_observed':True,'encoding':'i16-le-scale10',
        'source_value':None,'axis':{'RPM':rpm,'CAM_row':row+1},
        'axis_breakpoint_exact':False,'row':f'CAM row {row+1}','units':None,
        'label':f'WOT Intake VTC Low Cam / CAM row {row+1} / RPM={rpm}',
        'matrix_id':'vtc-intake-low','matrix_row':row,'matrix_column':column,
        'location_evidence':'two controlled edits and restore' if (row,rpm) in CONTROLLED
                            else 'inferred from measured table geometry',
        'evidence':'Controlled edits + independent readbacks' if (row,rpm) in CONTROLLED
                   else 'Layout inferred; readback required',
        'independent_readback_targets':READBACKS.get((row,rpm),[])}
        for row in range(2) for column,rpm in enumerate(RPM)}


def read(normalized,start):
    return {name:struct.unpack_from('<h',normalized,cell['offset']-start)[0]/10
            for name,cell in cells().items()}


def metadata():
    return {'id':'vtc-intake-low','table':'WOT Intake VTC Low Cam',
            'row_display':('CAM row 1','CAM row 2'),
            'row_axis_label':'CAM row','column_display':RPM,'column_axis_label':'RPM',
            'load_display':RPM,'units':None,'axis_breakpoints_exact':False,
            'row_stride':ROW_STRIDE,'column_stride':COLUMN_STRIDE,'storage':'row-major with gap',
            'preserved_inter_row_bytes':42,
            'controlled_cells':[cell_id(row,rpm) for row,rpm in sorted(CONTROLLED)],
            'all_cells_individually_reproduced':False,'ktuner_readback_required':True}
