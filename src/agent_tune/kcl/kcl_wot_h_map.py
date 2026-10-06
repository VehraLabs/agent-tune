"""Own measured WOT H/map0 geometry; display conversion remains inferred."""
from .kcl_ignition_map import RPM
from . import kcl_wot_cell as codec
OFFSET=426834
MGSTK=(100,250,300,350,400,450,500,530,550,600)
ROW_STRIDE,COLUMN_STRIDE=1,20
END=OFFSET+len(MGSTK)*COLUMN_STRIDE
CONTROLLED={(500,100),(650,100),(500,250)}
READBACKS={(500,100):[15.68,11.76],(1500,400):[14.7,codec.display(144)],(6800,600):[9.8,11.76]}

def cell_id(rpm,mgstk):
    return f'wot-h-{rpm}-{mgstk}'

def cells():
    result={}
    for row,rpm in enumerate(RPM):
        for column,mgstk in enumerate(MGSTK):
            cell=codec.metadata()
            controlled=(rpm,mgstk) in CONTROLLED
            cell.update({'offset':OFFSET+row+column*20,
                         'axis':{'RPM':rpm,'MgStk_display':mgstk,'branch':'H','map_selector':0},
                         'label':f'WOT Enrichment / H, map 0 / RPM={rpm}, MgStk display={mgstk}',
                         'conversion_evidence':'own independent H readbacks raw120/160/128/144/192 match rounded reciprocal display',
                         'matrix_id':'wot-h-0','matrix_row':row,'matrix_column':column,
                         'location_evidence':'two controlled edits and restore' if controlled else 'inferred from measured table geometry',
                         'evidence':'Two edits + restore; reciprocal display inferred' if controlled else 'Layout and reciprocal display inferred; readback required',
                         'independent_readback_targets':READBACKS.get((rpm,mgstk),[])})
            result[cell_id(rpm,mgstk)]=cell
    return result

def read(normalized,start):
    return {name:codec.display(normalized[cell['offset']-start]) for name,cell in cells().items()}

def metadata():
    return {'id':'wot-h-0','table':'WOT Enrichment','branch':'H','selector':0,
            'rpm_display':RPM,'column_display':MGSTK,'column_axis_label':'MgStk display',
            'units':None,'axis_breakpoints_exact':False,'row_stride':1,'column_stride':20,
            'storage':'column-major','display_model_inferred':True,'exact_coefficient_verified':False,
            'controlled_cells':[cell_id(rpm,mgstk) for rpm,mgstk in sorted(CONTROLLED)],
            'all_cells_individually_reproduced':False,'ktuner_readback_required':True}
