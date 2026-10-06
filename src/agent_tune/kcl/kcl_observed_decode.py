"""Read selected own observed cells after phase normalization, never raw maps.

Restricted to the measured save family. This is not an ECU ROM decoder.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

from .inspect_kcl import inspect
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

# Family mask includes independently read-back ignition, WOT and all103 AFM points.
FAMILY_SHA256 = '9ecb7bf01197ef1a11bc3b2ea0ed0f30612cd1b444ba0bfd55836bcd9efa2d70'
START, END, SIZE = 64, 524288, 524352
EXCLUSIONS = ((77432,77435),(80143,80147),(83405,83406),(maximum_map.OFFSET,maximum_map.END),(afm_curve.OFFSET,afm_curve.END),(wot_map.OFFSET,wot_map.END),(ignition_map.OFFSET,ignition_map.END),(base_h_map.OFFSET,base_h_map.END),(maximum_h_map.OFFSET,maximum_h_map.END),(wot_h_map.OFFSET,wot_h_map.END))


def normalize(body):
    if len(body) != SIZE:
        raise ValueError('Unsupported decoded body size')
    phases, shares, margins = [], [], []
    for phase in range(256):
        start = START + ((phase-START) % 256)
        values = body[start:END:256]
        ranked = Counter(values).most_common(2)
        first, count = ranked[0]
        second = ranked[1][1] if len(ranked)>1 else 0
        shares.append(count/len(values))
        margins.append((count-second)/len(values))
        if shares[-1] < 0.35 or margins[-1] < 0.30:
            raise ValueError('Unsupported or ambiguous phase normalization')
        phases.append(first)
    normalized = bytearray((value-phases[i%256])%256
                           for i,value in enumerate(body[START:END],START))
    return normalized, {'minimum_modal_share':min(shares),
                        'minimum_modal_margin':min(margins)}


def fingerprint(normalized):
    masked = bytearray(normalized)
    for start,end in EXCLUSIONS + rev_limits.EXCLUSIONS + vtc_low.EXCLUSIONS + vtc_high.EXCLUSIONS + vtec.EXCLUSIONS + fuel_cut_min.EXCLUSIONS + fuel_recover.EXCLUSIONS + fuel_delay.EXCLUSIONS + pressure.EXCLUSIONS + recovery_pressure.EXCLUSIONS + high_cut_pressure.EXCLUSIONS + high_recover_pressure.EXCLUSIONS + cylinder_trim.EXCLUSIONS:
        masked[start-START:end-START] = bytes(end-start)
    return hashlib.sha256(masked).hexdigest()


def decode(data):
    try:
        metadata = inspect(data, max_payload=SIZE)
    except zlib.error as error:
        raise ValueError('Invalid gzip integrity') from error
    normalized, quality = normalize(gzip.decompress(data[35:]))
    digest = fingerprint(normalized)
    if digest != FAMILY_SHA256:
        raise ValueError('File is outside the measured normalized save family')
    def read(fmt,offset):
        return struct.unpack_from(fmt,normalized,offset-START)[0]
    values = {'ect-low-32':read('<h',80143)/10,
              'ect-low-104':read('<h',80145)/10,
              'ect-high-104':read('<h',83405)/10,
              'afm-flow-first':read('<f',407401),
              'afm-flow-second':read('<f',407405),
              'ign-max-l-500-0':read('<h',193267)/10,
              'ign-base-l-500-131':read('<h',410515)/10}
    values.update(afm_curve.read(normalized,START))
    values.update(vtc_low.read(normalized,START))
    values.update(vtc_high.read(normalized,START))
    rev_values, linked = rev_limits.read(normalized,START)
    values.update(rev_values)
    vtec_values, vtec_linked = vtec.read(normalized,START)
    values.update(vtec_values)
    values.update(fuel_cut_min.read(normalized,START))
    values.update(fuel_recover.read(normalized,START))
    values.update(fuel_delay.read(normalized,START))
    pressure_values, pressure_counts = pressure.read(normalized,START)
    values.update(pressure_values)
    recover_values, recover_counts = recovery_pressure.read(normalized,START)
    values.update(recover_values)
    pressure_counts.update(recover_counts)
    high_cut_values, high_cut_counts = high_cut_pressure.read(normalized,START)
    values.update(high_cut_values)
    pressure_counts.update(high_cut_counts)
    high_recover_values, high_recover_counts = high_recover_pressure.read(normalized,START)
    values.update(high_recover_values)
    pressure_counts.update(high_recover_counts)
    trim_values, trim_counts = cylinder_trim.read(normalized,START)
    values.update(trim_values)
    values.update(wot_map.read(normalized,START))
    values.update(wot_h_map.read(normalized,START))
    values.update(ignition_map.read(normalized,START))
    values.update(base_h_map.read(normalized,START))
    values.update(maximum_map.read(normalized,START))
    values.update(maximum_h_map.read(normalized,START))
    if any(not math.isfinite(values[name]) or values[name]<0
           for name in ('afm-flow-first','afm-flow-second')):
        raise ValueError('Invalid observed AFM value')
    if values['ect-high-104'] not in (0.5,1.0,1.5):
        raise ValueError('Unsupported high-table source value')
    return {'input_sha256':metadata['sha256'],'family_sha256':digest,
            'trim_counts':trim_counts,'pressure_counts':pressure_counts,'rev_linked_values':linked,'vtec_linked_values':vtec_linked,
            'values':values,'normalization_quality':quality,'matrix':ignition_map.metadata(),
            'offline_only':True,'ecu_flash_compatibility_verified':False,
            'curves':[afm_curve.metadata()],
            'matrices':[ignition_map.metadata(),base_h_map.metadata(),maximum_map.metadata(),maximum_h_map.metadata(),wot_map.metadata(),wot_h_map.metadata(),vtc_low.metadata(),vtc_high.metadata()],
            'wot_display_model':wot_cell.metadata(),
            'scope':'measured scalar values, AFM curve and eight layouts; individual cell evidence varies'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    args = parser.parse_args(argv)
    try:
        if args.file.stat().st_size > 16*1024*1024:
            raise ValueError('Input exceeds size limit')
        print(json.dumps(decode(args.file.read_bytes()),indent=2))
        return 0
    except (OSError,ValueError) as error:
        parser.exit(2,f'Error: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
