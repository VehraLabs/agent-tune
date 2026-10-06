"""Decode a .kcl file into named values.

The save body is stored with a repeating 256-byte offset pattern. `normalize`
recovers it from the most common byte at each position modulo 256 and removes
it. A SHA-256 of the normalized body, with every editable region masked out,
identifies a verified file family. Files outside the verified families are
refused unless the caller opts in with `allow_unverified`; then the known
layout is applied anyway and a set of plausibility checks says whether the
values look like a real tune, so owners of other cars can try it and confirm
the result in KTuner. This reads KTuner's save format only; it is not an ECU
ROM decoder.
"""
from collections import Counter
import gzip
import hashlib
import struct
import zlib

from . import afm_curve, cylinder_trim, ect_ignition, envelope, fuel_cut, ignition, map_cut, rev_limits, vtc_intake, vtec, wot

# Verified families: fingerprint -> description. Add a line here once a family's layout has been confirmed in KTuner.
FAMILIES = {
    '9ecb7bf01197ef1a11bc3b2ea0ed0f30612cd1b444ba0bfd55836bcd9efa2d70':
        'Honda Civic 11th gen 2.0 L (64S ECU, 37805-64S-AC20), KTuner 1.0.14.1 save format',
}
START, END, SIZE = 64, 524288, 524352
# Byte ranges masked out before fingerprinting: every editable table plus a few bytes that are not part of the family identity.
MASKED = ((77432, 77435),) + (ect_ignition.REGIONS + ignition.REGIONS + wot.REGIONS + vtc_intake.REGIONS + vtec.REGIONS
                               + rev_limits.REGIONS + afm_curve.REGIONS + fuel_cut.REGIONS + map_cut.REGIONS
                               + cylinder_trim.REGIONS)
TABLE_MODULES = (ignition, wot, vtc_intake, vtec, rev_limits, afm_curve, fuel_cut, map_cut, cylinder_trim, ect_ignition)


def normalize(body):
    """Remove the repeating 256-byte offset pattern from the save body."""
    if len(body) != SIZE:
        raise ValueError('Unsupported .kcl body size')
    offsets = []
    for phase in range(256):
        first = START + ((phase - START) % 256)
        column = body[first:END:256]
        ranked = Counter(column).most_common(2)
        value, count = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        if count / len(column) < 0.35 or (count - second) / len(column) < 0.30:
            raise ValueError('Unsupported .kcl body layout')
        offsets.append(value)
    return bytearray((value - offsets[i % 256]) % 256 for i, value in enumerate(body[START:END], START))


def fingerprint(normalized):
    masked = bytearray(normalized)
    for first, last in MASKED:
        masked[first - START:last - START] = bytes(last - first)
    return hashlib.sha256(masked).hexdigest()


def plausibility(values):
    """Heuristic checks that decoded values look like a real tune. Used for unverified files."""
    def group(prefix):
        return [v for k, v in values.items() if k.startswith(prefix)]
    afm = [values[afm_curve.cell_id(i)] for i in range(afm_curve.COUNT)]
    return {
        'ignition_timing_between_-20_and_70': all(-20 <= v <= 70 for v in group('ign-')),
        'wot_afr_between_9_and_16': all(v is not None and 9 <= v <= 16 for v in group('wot-')),
        'intake_vtc_between_-5_and_60': all(-5 <= v <= 60 for v in group('vtc-intake-')),
        'afm_curve_increasing': all(a < b for a, b in zip(afm, afm[1:])),
        'rev_limits_ordered_3000_to_9500': (3000 <= values['rev-low-restart'] < values['rev-low-limit'] <= 9500
                                            and 3000 <= values['rev-high-restart'] < values['rev-high-limit'] <= 9500),
        'vtec_ordered_1500_to_8000': 1500 <= values['vtec-lower-disengage'] < values['vtec-lower-engage'] <= 8000,
        'fuel_cut_rpm_between_500_and_5000': all(500 <= v <= 5000 for v in group('fuel-cut-min-') + group('fuel-recover-')),
        'map_cut_pressure_between_50_and_3000_mbar': all(50 <= v <= 3000 for v in group('fuel-map-')),
        'cylinder_trims_between_-10_and_10': all(-10 <= v <= 10 for v in group('cylinder-trim-')),
        'ect_high_correction_known_value': values['ect-high-104'] in ect_ignition.CELLS['ect-high-104']['choices'],
    }


def decode(data, allow_unverified=False):
    """Values of every editable cell plus the stored counts some encodings need.

    Raises ValueError for files outside the verified families unless `allow_unverified`
    is set; then `verified` is False and `checks` holds the plausibility results.
    """
    try:
        metadata = envelope.inspect(data, max_payload=SIZE)
    except zlib.error as error:
        raise ValueError('Corrupt gzip stream') from error
    normalized = normalize(gzip.decompress(data[envelope.GZIP_OFFSET:]))
    digest = fingerprint(normalized)
    family = FAMILIES.get(digest)
    if family is None and not allow_unverified:
        raise ValueError('This .kcl is not from a verified family (' + '; '.join(FAMILIES.values())
                         + '). Pass allow_unverified / --unverified to try the known layout anyway and confirm it in KTuner.')
    values = {}
    for module in (ignition, wot, vtc_intake, afm_curve, fuel_cut, ect_ignition):
        values.update(module.read(normalized, START))
    rev_values, rev_linked = rev_limits.read(normalized, START)
    vtec_values, vtec_linked = vtec.read(normalized, START)
    map_values, map_counts = map_cut.read(normalized, START)
    trim_values, trim_counts = cylinder_trim.read(normalized, START)
    values.update(rev_values)
    values.update(vtec_values)
    values.update(map_values)
    values.update(trim_values)
    checks = plausibility(values)
    if family is not None and not checks['ect_high_correction_known_value']:
        raise ValueError('Unsupported ECT Ignition High value')
    return {'input_sha256': metadata['sha256'], 'family_sha256': digest, 'family': family, 'verified': family is not None,
            'checks': checks, 'plausible': all(checks.values()), 'values': values, 'rev_linked': rev_linked,
            'vtec_linked': vtec_linked, 'map_counts': map_counts, 'trim_counts': trim_counts}
