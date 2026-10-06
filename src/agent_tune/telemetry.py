"""Read live values from a KTuner dongle over USB, read-only.

The only byte ever sent is the B0 read poll that KTuner itself uses for live
data. There is no write, storage, update, registration or flash command in
this package. Close the KTuner app first: it holds the same COM port.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import time

FTDI_VID, FTDI_PID, SERIAL_PREFIX = 0x0403, 0x6001, 'KTFLV'
BAUD = 1_000_000
FRAME_BODY_LENGTHS = frozenset((2, 531, 649))  # observed B0 reply bodies; 531 carries telemetry
GROUPS = {'A': (3, 169, (0x2610, 0x2611, 0x2612)),
          'B': (172, 113, (0x2613, 0x2660)),
          'C': (341, 169, (0x2662, 0x2663, 0x266C))}
READERS = {'u8': (1, 'big', False), 'u16be': (2, 'big', False), 'u16le': (2, 'little', False),
           's16be': (2, 'big', True)}
PLATFORM_DIR = Path(__file__).parent / 'platforms'
DEFAULT_PLATFORM = 'honda-civic-11g-2.0-64s'


@lru_cache(maxsize=None)
def platforms():
    out = {}
    for path in sorted(PLATFORM_DIR.glob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        out[data['id']] = data
    return out


def platform(platform_id=DEFAULT_PLATFORM):
    try:
        return platforms()[platform_id]
    except KeyError:
        raise ValueError(f'Unknown platform {platform_id!r}; known: {", ".join(platforms())}') from None


class B0Stream:
    """Reassemble B0-framed replies (B0, u16le body length, body) from UART chunks."""

    def __init__(self):
        self.buffer = bytearray()
        self.discarded = 0

    def feed(self, data):
        frames = []
        for value in data:
            self.buffer.append(value)
            while self.buffer:
                if self.buffer[0] != 0xB0:
                    del self.buffer[0]
                    self.discarded += 1
                    continue
                if len(self.buffer) < 3:
                    break
                size = int.from_bytes(self.buffer[1:3], 'little')
                if size not in FRAME_BODY_LENGTHS:
                    del self.buffer[0]
                    self.discarded += 1
                    continue
                if len(self.buffer) < size + 3:
                    break
                frames.append(bytes(self.buffer))
                self.buffer.clear()
        return frames


def split_groups(frame):
    """Return {'A': bytes, 'B': bytes, 'C': bytes} for a 534-byte telemetry frame, else None."""
    if len(frame) != 534 or any(frame[285:341]):
        return None
    out = {}
    for name, (offset, size, dids) in GROUPS.items():
        payload = frame[offset:offset + size]
        if payload[0] != 0x62 or [int.from_bytes(payload[i:i + 2], 'big') for i in range(1, size, 56)] != list(dids):
            return None
        out[name] = bytes(payload)
    return out


def decode_groups(groups, platform_id=DEFAULT_PLATFORM):
    """Decode validated channels from group payloads (offsets include the 0x62 byte)."""
    values = {}
    for ch in platform(platform_id)['channels']:
        raw = groups.get(ch['group'])
        width, order, signed = READERS[ch['type']]
        if raw is None or ch['offset'] + width > len(raw):
            continue
        value = int.from_bytes(raw[ch['offset']:ch['offset'] + width], order, signed=signed)
        values[ch['name']] = round(value * ch['scale'] + ch['bias'], 6)
    return values


def find_ports(ports=None):
    """KTuner dongle COM ports (FTDI 0403:6001 with a KTFLV serial number)."""
    if ports is None:
        from serial.tools import list_ports
        ports = list_ports.comports()
    return [{'port': p.device, 'description': p.description} for p in ports
            if p.vid == FTDI_VID and p.pid == FTDI_PID and (p.serial_number or '').upper().startswith(SERIAL_PREFIX)]


def open_port(name):
    import serial
    if name not in [p['port'] for p in find_ports()]:
        raise ValueError(f'{name} is not a detected KTuner dongle')
    port = serial.Serial(port=None, baudrate=BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.02,
                         write_timeout=0.2, xonxoff=False, rtscts=False, dsrdtr=False)
    port.dtr = False
    port.rts = False
    port.port = name
    port.open()
    return port


@dataclass
class Summary:
    seconds: float
    polls: int
    frames: int
    telemetry_frames: int
    bytes_received: int

    def as_dict(self):
        return dict(self.__dict__, writes_supported=False)


def record(port, seconds, out_path, platform_id=DEFAULT_PLATFORM, interval=0.05, on_values=None, stop=None):
    """Poll B0 for up to `seconds`, writing one JSON line per telemetry frame.

    Each line: {"t": seconds, "ch": {decoded channels}, "raw": {"A": hex, "B": hex, "C": hex}}.
    Raw bytes are kept so logs can be re-decoded when definitions improve.
    """
    if not 0 < seconds <= 3600 or not 0.02 <= interval <= 1:
        raise ValueError('Duration must be 0-3600 s and poll interval 0.02-1 s')
    stream = B0Stream()
    polls = frames = telemetry = received = 0
    start = time.monotonic()
    next_poll = start
    with Path(out_path).open('x', encoding='utf-8') as out:
        out.write(json.dumps({'format': 'agent-tune.log.v1', 'platform': platform_id,
                              'started': time.strftime('%Y-%m-%dT%H:%M:%S%z')}) + '\n')
        while time.monotonic() - start < seconds and not (stop is not None and stop.is_set()):
            now = time.monotonic()
            if now >= next_poll:
                if port.write(b'\xb0') != 1:
                    raise OSError('B0 poll was not written')
                polls += 1
                next_poll = now + interval
            chunk = port.read(1024)
            received += len(chunk)
            for frame in stream.feed(chunk):
                frames += 1
                groups = split_groups(frame)
                if groups is None:
                    continue
                telemetry += 1
                values = decode_groups(groups, platform_id)
                t = round(time.monotonic() - start, 4)
                out.write(json.dumps({'t': t, 'ch': values, 'raw': {k: v.hex() for k, v in groups.items()}}) + '\n')
                if on_values is not None:
                    on_values(t, values)
    return Summary(round(time.monotonic() - start, 3), polls, frames, telemetry, received)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
