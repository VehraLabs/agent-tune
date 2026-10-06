"""Own first WOT cell; inferred reciprocal display, bounded readback domain."""
from decimal import Decimal, InvalidOperation
OFFSET = 427034
CELL = 'wot-l-500-100'
CONSTANT = Decimal('1881.6')  # own 14.7 target stores 128; independently read 120/160 and corner192
MIN_RAW, MAX_RAW = 120,192

def display(raw):
    return float(CONSTANT / raw) if raw else None

def encode(target, source):
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not CONSTANT/MAX_RAW <= value <= CONSTANT/MIN_RAW:
            raise ValueError('WOT target is outside the independently bounded display domain 9.8..15.68')
        raw = min(range(MIN_RAW, MAX_RAW+1), key=lambda count:abs(CONSTANT/count-value))
        old = int(round(float(CONSTANT)/source))
        if not MIN_RAW <= old <= MAX_RAW:
            raise ValueError('WOT source is outside the independently bounded representation')
    except (InvalidOperation,ZeroDivisionError,OverflowError,TypeError) as error:
        raise ValueError('WOT target requires a finite positive numeric source and target') from error
    delta=(raw-old+128)%256-128
    return ({OFFSET:delta} if delta else {}),display(raw),raw

def metadata():
    return {'table':'WOT Enrichment','offset':OFFSET,'encoding':'u8-reciprocal-display',
            'numeric_encoding_observed':True,'source_value':None,
            'axis':{'RPM':500,'MgStk_display':100,'branch':'L','map_selector':0},
            'axis_breakpoint_exact':False,'row':'WOT value','units':None,
            'display_model_inferred':True,'exact_coefficient_verified':False,
            'label':'WOT Enrichment / L, map 0 / RPM=500, MgStk display=100',
            'evidence':'Two edits + restore; reciprocal display inferred; two independent readbacks',
            'location_evidence':'two controlled edits and restore',
            'independent_readback_targets':[11.76,15.68],
            'min':9.8,'max':15.68,'step':'any',
            'conversion_evidence':'inferred from own target128/display14.7 and readback120/display15.7,160/display11.8',
            'quantization':'nearest representable display value; not a claim to reproduce KTuner setter rounding'}
