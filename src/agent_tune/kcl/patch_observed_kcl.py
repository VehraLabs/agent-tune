"""Restricted offline experiment: patch observed cells in the measured own save family.

No device access, upload or ECU writes. Output is for offline KTuner readback.
Not a general KCL writer: unknown header/footer/integrity fields are preserved.
"""
import argparse
import gzip
import hashlib
import json
import math
import struct
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .inspect_kcl import inspect
from .kcl_observed_decode import decode
from . import kcl_ignition_map as ignition_map
from . import kcl_base_h_map as base_h_map
from . import kcl_maximum_map as maximum_map
from . import kcl_maximum_h_map as maximum_h_map
from . import kcl_wot_cell as wot_cell
from . import kcl_wot_map as wot_map
from . import kcl_wot_h_map as wot_h_map
from . import kcl_vtc_intake_low as vtc_low
from . import kcl_vtc_intake_high as vtc_high
from . import kcl_afm_curve as afm_curve
from . import kcl_rev_limits as rev_limits
from . import kcl_vtec as vtec
from . import kcl_fuel_cut_min as fuel_cut_min
from . import kcl_fuel_recover as fuel_recover
from . import kcl_fuel_delay as fuel_delay
from . import kcl_fuel_map_low_cut as pressure
from . import kcl_fuel_map_low_recover as recovery_pressure
from . import kcl_fuel_map_high_cut as high_cut_pressure
from . import kcl_cylinder_trim as cylinder_trim
from . import kcl_fuel_map_high_recover as high_recover_pressure

BASELINE_SHA256 = 'd72696f68c37efdfec2a688b69598b3268834d03dff5bf08aeb9cdf83bfa1df1'
OFFSET = 80145
CELLS = {
    'ect-low-104': {'table':'ECT Ignition Low', 'offset':OFFSET,
                    'numeric_encoding_observed':True},
    'ect-high-104': {'table':'ECT Ignition High', 'offset':83405,
                     'numeric_encoding_observed':False},
    'afm-flow-first': {'table':'AFM Flow','offset':407401,
                      'numeric_encoding_observed':True,'encoding':'float32-le',
                      'source_value':0.5591,'axis':{'Hz_display':'2031.2','column_index':0},
                      'axis_breakpoint_exact':False,'row':'g/s','units':'g/s',
                      'label':'AFM Flow / first Hz point (display 2031.2) / g/s'},
    'afm-flow-second': {'table':'AFM Flow','offset':407405,
                       'numeric_encoding_observed':True,'encoding':'float32-le',
                       'source_value':0.9621,'axis':{'Hz_display':'2109.3','column_index':1},
                       'axis_breakpoint_exact':False,'row':'g/s','units':'g/s',
                       'label':'AFM Flow / second Hz point (display 2109.3) / g/s'},
    'ign-base-l-500-131': {'table':'Ignition Base','offset':410515,
                         'numeric_encoding_observed':True,'encoding':'i16-le-scale10',
                         'source_value':55.0,'axis':{'RPM':500,'Load_display':131,'branch':'L','map_selector':0},
                         'axis_breakpoint_exact':False,'row':'Ignition value','units':None,
                         'label':'Ignition Base / L, map 0 / RPM=500, Load display=131',
                         'independent_readback_targets':[-0.5,51.1]},
}
main_first = CELLS['ign-base-l-500-131']
CELLS.update(ignition_map.cells())
CELLS.update(base_h_map.cells())
CELLS['ign-base-l-500-131'].update(main_first)
CELLS['ign-base-l-500-131']['evidence'] = 'Signed crossing + positive carry'
CELLS['ign-max-l-500-0'] = {
    'table':'Ignition Maximum','offset':193267,'encoding':'i16-le-scale10',
    'numeric_encoding_observed':True,'source_value':13.8,
    'axis':{'RPM':500,'EGR_display':0,'branch':'L','map_selector':0},
    'axis_breakpoint_exact':False,'row':'Ignition value','units':None,
    'label':'Ignition Maximum / L, map 0 / RPM=500, EGR display=0',
    'evidence':'Two edits + restore; signed crossing + positive carry',
    'location_evidence':'two controlled edits and restore',
    'independent_readback_targets':[-0.5,25.6]}
maximum_first=CELLS['ign-max-l-500-0']
CELLS.update(maximum_map.cells())
CELLS['ign-max-l-500-0'].update(maximum_first)
CELLS.update(maximum_h_map.cells())
CELLS.update(wot_map.cells())
CELLS.update(wot_h_map.cells())
CELLS.update(afm_curve.cells())
CELLS.update(rev_limits.cells())
CELLS.update(vtc_low.cells())
CELLS.update(vtc_high.cells())
CELLS.update(vtec.cells())
CELLS.update(fuel_cut_min.cells())
CELLS.update(fuel_recover.cells())
CELLS.update(fuel_delay.cells())
CELLS.update(pressure.cells())
CELLS.update(recovery_pressure.cells())
CELLS.update(high_cut_pressure.cells())
CELLS.update(high_recover_pressure.cells())
CELLS.update(cylinder_trim.cells())


def float_deltas(target, source_value=0.5591):
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not Decimal(0) <= value <= Decimal('3.4028234663852886e38'):
            raise ValueError('AFM value must be nonnegative and fit finite float32')
        packed = struct.pack('<f',float(value))
        effective = struct.unpack('<f',packed)[0]
        if not math.isfinite(effective) or (value != 0 and effective == 0):
            raise ValueError('AFM value overflows or underflows float32')
    except (InvalidOperation,OverflowError) as error:
        raise ValueError('AFM value must fit finite float32') from error
    source = struct.pack('<f',source_value)
    return {407401+i:(new-old+128)%256-128 for i,(old,new) in
            enumerate(zip(source,packed)) if old != new}, effective


def cell_deltas(target, source_value=1.5):
    """Local measured i16 little-endian arithmetic from a decoded source value.

    Encoding is supported by positive carry and negative zero-crossing controls.
    Unsampled values still require independent offline UI readback.
    """
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not Decimal('-3276.8') <= value <= Decimal('3276.7'):
            raise ValueError('Target must fit signed 16-bit counts at scale 10')
        counts = value * 10
        if not value.is_finite() or counts != counts.to_integral_value():
            raise ValueError('Target must be finite in exact 0.1 display increments')
        target_bytes = int(counts).to_bytes(2, 'little', signed=True)
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Target must fit signed 16-bit counts at scale 10') from error
    source_bytes = int(Decimal(str(source_value))*10).to_bytes(2, 'little', signed=True)
    changes = {}
    for index, (old, new) in enumerate(zip(source_bytes, target_bytes)):
        delta = (new-old) % 256
        if delta:
            changes[OFFSET+index] = delta if delta < 128 else delta-256
    return changes


def plan_changes(plan, source_values=None, source_linked=None, source_vtec_linked=None, source_pressure_counts=None, source_trim_counts=None):
    """Validate an offline plan; no arbitrary offsets or source values accepted."""
    if not isinstance(plan, dict) or not plan or set(plan)-set(CELLS):
        raise ValueError('Plan must be a nonempty object of observed cell IDs')
    changes, edits = {}, []
    if set(plan) & {'rev-high-limit','rev-high-restart'}:
        if source_values is None:
            raise ValueError('Rev edits require a decoded source file')
        high=rev_limits.counts(plan.get('rev-high-limit',source_values['rev-high-limit']))
        restart=rev_limits.counts(plan.get('rev-high-restart',source_values['rev-high-restart']))
        if restart >= high:
            raise ValueError('High Restart must be below High Limit')
    if set(plan) & set(vtec.GROUPS):
        if source_values is None:
            raise ValueError('VTEC edits require a decoded source file')
        engage=vtec.counts(plan.get('vtec-lower-engage',source_values['vtec-lower-engage']))
        disengage=vtec.counts(plan.get('vtec-lower-disengage',source_values['vtec-lower-disengage']))
        if disengage >= engage:
            raise ValueError('Lower Disengage must be below Lower Engage')
    for name, target in plan.items():
        if isinstance(target, bool) or not isinstance(target, (str, int, float)):
            raise ValueError('Each target must be a numeric value or decimal string')
        cell = CELLS[name]
        source = (source_values or {}).get(name,cell.get('source_value',1.5))
        if source is None:
            raise ValueError('Cell edits require source values decoded from a supported file')
        encoded_raw = None
        if cell.get('encoding') == 'trim-u16-le':
            if source_trim_counts is None or name not in source_trim_counts:
                raise ValueError('Trim edits require exact decoded source counts')
            value=float(Decimal(str(target)))
            encoded_raw=source_trim_counts[name] if value == source else cylinder_trim.counts(target)
            effective=cylinder_trim.value(encoded_raw)
            relocated=cylinder_trim.raw_deltas(cell['offset'],encoded_raw,source_trim_counts[name])
        elif cell.get('encoding') == 'pressure-count-u16-le':
            if source_pressure_counts is None or name not in source_pressure_counts:
                raise ValueError('Pressure edits require exact decoded source counts')
            pressure_module = {'fuel-map-low-cut': pressure, 'fuel-map-low-recover': recovery_pressure,
                               'fuel-map-high-cut': high_cut_pressure,
                               'fuel-map-high-recover': high_recover_pressure}[cell['curve_id']]
            value=float(Decimal(str(target)))
            encoded_raw=source_pressure_counts[name] if value == source else pressure.counts(target)
            effective=encoded_raw/7.6
            relocated=pressure_module.raw_deltas(cell['offset'],encoded_raw,source_pressure_counts[name])
        elif cell.get('encoding') == 'fuel-delay-u16-le':
            value=effective=fuel_delay.counts(target)
            relocated=fuel_delay.deltas(cell['offset'],target,source)
        elif cell.get('encoding') == 'fuel-cut-u16-le':
            value=effective=fuel_cut_min.counts(target)
            relocated=fuel_cut_min.deltas(cell['offset'],target,source)
        elif cell.get('encoding') == 'vtec-linked-u16-le':
            value=effective=vtec.counts(target)
            relocated=vtec.deltas(name,target,source_vtec_linked)
        elif cell.get('encoding') == 'linked-u16-le':
            value=effective=rev_limits.counts(target)
            relocated=rev_limits.deltas(name,target,source_linked,
                synchronize_restart=name=='rev-high-limit' and 'rev-high-restart' not in plan)
        elif cell.get('encoding') == 'u8-reciprocal-display':
            local, effective, encoded_raw = wot_cell.encode(target,source)
            relocated = {cell['offset']+offset-wot_cell.OFFSET:delta for offset,delta in local.items()}
            value = float(Decimal(str(target)))
        elif cell.get('encoding') == 'float32-le':
            local, effective = float_deltas(target,source)
            relocated = {cell['offset']+offset-407401:delta for offset,delta in local.items()}
            value = float(Decimal(str(target)))
        else:
            local = cell_deltas(target,source)
            value = float(Decimal(str(target)))
            relocated = {cell['offset']+offset-OFFSET:delta for offset,delta in local.items()}
            effective = value
        if not cell['numeric_encoding_observed'] and value not in [0.5,1.0,1.5]:
            raise ValueError('High-table cell supports only observed targets 0.5, 1.0 or restore 1.5')
        if changes.keys() & relocated.keys():
            raise ValueError('Overlapping edits')
        changes.update(relocated)
        readback = [2.0] if name in ('afm-flow-first','afm-flow-second') else [1.0,0.5,-0.5,25.6] if name=='ect-low-104' else [0.5]
        readback = cell.get('independent_readback_targets',readback)
        edits.append({'cell':name,'table':cell['table'],'axis':cell.get('axis',{'ECT':104}),
                      'axis_breakpoint_exact':cell.get('axis_breakpoint_exact',True),
                      'label':cell.get('label',cell['table']+' / ECT=104 Corr'),
                      'row':cell.get('row','Corr'),'from':source,
                      'location_evidence':cell.get('location_evidence','reproduced local cell'),
                      'to':value,'encoded_value':effective,'ui_units':cell.get('units'),
                      'conversion_evidence':cell.get('conversion_evidence'),
                      'quantization':cell.get('quantization'),
                      'encoded_storage_count':encoded_raw,
                      'display_model_inferred':cell.get('display_model_inferred',False),
                      'decoded_byte_deltas':relocated,
                      'linked_offsets':cell.get('linked_offsets'),
                      'restart_copies_synchronized':name=='rev-high-limit' and 'rev-high-restart' not in plan,
                      'target_has_prior_independent_readback': value in readback})
    return changes, edits


def parse_plan(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate cell ID in plan')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def load_plan(path):
    return parse_plan(path.read_text(encoding='utf-8-sig'))


def patch(data, offset, delta, expected_sha256):
    return patch_bytes(data, {offset: delta}, expected_sha256)


def patch_bytes(data, changes, expected_sha256):
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('Baseline SHA256 mismatch; no edit performed')
    metadata = inspect(data)
    payload = bytearray(gzip.decompress(data[35:]))
    for offset, delta in changes.items():
        if not 0 <= offset < len(payload):
            raise ValueError('Offset outside decoded body')
        payload[offset] = (payload[offset]+delta) % 256
    packed = gzip.compress(payload, mtime=0)
    header = bytearray(data[:35])
    header[31:35] = len(packed).to_bytes(4, 'big')
    output = bytes(header)+packed
    verified = inspect(output)
    if verified['decoded_size'] != metadata['decoded_size']:
        raise ValueError('Repacked size mismatch')
    return output


def generate(data, plan):
    """Shared offline serializer used by CLI and local editor."""
    observed = decode(data)
    changes, edits = plan_changes(plan,observed['values'],observed['rev_linked_values'],observed['vtec_linked_values'],observed['pressure_counts'],observed['trim_counts'])
    output = patch_bytes(data, changes, observed['input_sha256'])
    verified = decode(output)
    for edit in edits:
        if verified['values'][edit['cell']] != edit['encoded_value']:
            raise ValueError('Export did not decode to the intended cell value')
        linked=verified['vtec_linked_values'] if edit['cell'] in vtec.GROUPS else verified['rev_linked_values']
        if edit['linked_offsets'] and any(linked[offset] != edit['encoded_value']
                                          for offset in edit['linked_offsets']):
            raise ValueError('Export did not update all linked fields')
        if edit['restart_copies_synchronized']:
            restart=verified['values']['rev-high-restart']
            if any(verified['rev_linked_values'][offset] != restart
                   for offset in rev_limits.GROUPS['rev-high-restart']):
                raise ValueError('Export did not synchronize restart copies')
    manifest = {'baseline_sha256':observed['input_sha256'],
                'family_sha256':observed['family_sha256'],
                'output_sha256':hashlib.sha256(output).hexdigest(),
                'edits':edits,'decoded_byte_deltas':changes,
                'decoded_bytes_changed':len(changes),'offline_only':True,
                'ecu_flash_compatibility_verified':False,
                'ktuner_readback_required':True}
    return output, manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path)
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--target',
                   help='Experimental ECT=104 Corr value in 0.1 increments; source is read from the loaded file. Offline readback required.')
    selection.add_argument('--plan', type=Path, help='JSON object mapping observed cell IDs to display targets')
    p.add_argument('--cell', help='Observed scalar or ignition matrix cell ID')
    p.add_argument('--out', type=Path, required=True, help='New private .kcl experiment file')
    p.add_argument('--manifest', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.out.suffix.lower() != '.kcl':
            raise ValueError('Output must be a private .kcl file')
        inputs = {a.baseline.resolve()}
        if a.plan:
            inputs.add(a.plan.resolve())
        if a.out.resolve() in inputs or a.manifest.resolve() in inputs | {a.out.resolve()}:
            raise ValueError('Manifest must be separate from input and output')
        if a.out.exists() or a.manifest.exists():
            raise ValueError('Output and manifest must both be new files')
        data = a.baseline.read_bytes()
        if a.plan and a.cell:
            raise ValueError('--cell cannot be combined with --plan')
        plan = load_plan(a.plan) if a.plan else {a.cell or 'ect-low-104':a.target}
        output, result = generate(data, plan)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open('xb') as fh:
            fh.write(output)
        with a.manifest.open('x', encoding='utf-8') as fh:
            fh.write(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
        return 0
    except (OSError, ValueError) as error:
        p.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
