"""WOT Enrichment tables (map 0), low-cam (L) and high-cam (H).

Each cell is one byte; the displayed AFR target is 1881.6 / byte. Only bytes
120 through 192 (AFR 15.68 down to 9.8) are accepted, the range KTuner has been
seen to display.
"""
from decimal import Decimal, InvalidOperation

from .common import grid
from .ignition import RPM

CONSTANT = Decimal('1881.6')
MIN_RAW, MAX_RAW = 120, 192
MGSTK = (100, 250, 300, 350, 400, 450, 500, 530, 550, 600)
ROW_STRIDE, COLUMN_STRIDE = 1, 20
TABLES = (('wot-l', 'L', 427034), ('wot-h', 'H', 426834))
REGIONS = tuple((offset, offset + len(MGSTK) * COLUMN_STRIDE) for _, _, offset in TABLES)


def display(raw):
    return float(CONSTANT / raw) if raw else None


def encode(target, source):
    """Byte delta (keyed 0), effective displayed value and stored byte for a target AFR."""
    try:
        value = Decimal(str(target))
        if not value.is_finite() or not CONSTANT / MAX_RAW <= value <= CONSTANT / MIN_RAW:
            raise ValueError('WOT target must be between 9.8 and 15.68')
        raw = min(range(MIN_RAW, MAX_RAW + 1), key=lambda count: abs(CONSTANT / count - value))
        old = int(round(float(CONSTANT) / source))
        if not MIN_RAW <= old <= MAX_RAW:
            raise ValueError('Current WOT value is outside the supported range')
    except (InvalidOperation, ZeroDivisionError, OverflowError, TypeError) as error:
        raise ValueError('WOT target must be a number between 9.8 and 15.68') from error
    delta = (raw - old + 128) % 256 - 128
    return ({0: delta} if delta else {}), display(raw), raw


def cells():
    out = {}
    for prefix, branch, offset in TABLES:
        out.update(grid('WOT Enrichment', lambda rpm, mg, p=prefix: f'{p}-{rpm}-{mg}', offset, RPM, MGSTK,
                        ROW_STRIDE, COLUMN_STRIDE, 'u8-reciprocal',
                        lambda rpm, mg, b=branch: {'RPM': rpm, 'MgStk_display': mg, 'branch': b, 'map_selector': 0},
                        lambda rpm, mg, b=branch: f'WOT Enrichment / {b}, map 0 / RPM={rpm}, MgStk display={mg}'))
    for cell in out.values():
        cell.update({'min': display(MAX_RAW), 'max': display(MIN_RAW), 'step': 'any'})
    return out


def read(normalized, start):
    return {name: display(normalized[cell['offset'] - start]) for name, cell in cells().items()}
