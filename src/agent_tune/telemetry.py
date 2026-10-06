"""Read live values from a KTuner dongle over USB. Read-only.

The only byte ever sent is the B0 poll that KTuner itself uses for live data.
There is no write, storage, update, registration or flash command in this
package. Close the KTuner app first: it holds the same COM port.

Where each channel sits in the reply is described by a platform file in
`platforms/`. You can also pass the path of your own platform JSON to try a
car that is not bundled yet; unrecognized frames are logged raw so they can be
compared with a KTuner datalog.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import time

FTDI_VID, FTDI_PID, SERIAL_PREFIX = 0x0403, 0x6001, 'KTFLV'
BAUD = 1_000_000
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


@lru_cache(maxsize=None)
def _platform_file(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for key in ('id', 'name', 'transport', 'channels'):
        if key not in data:
            raise ValueError(f'Platform file {path} is missing "{key}"')
    return data


def platform(platform_id=DEFAULT_PLATFORM):
    """A bundled platform by id, or a platform JSON file by path."""
    if platform_id in platforms():
        return platforms()[platform_id]
    if str(platform_id).lower().endswith('.json') and Path(platform_id).is_file():
        return _platform_file(str(Path(platform_id).resolve()))
    raise ValueError(f'Unknown platform {platform_id!r}; bundled: {", ".join(platforms())}, '
                     'or pass the path of a platform .json file')


def transport(platform_id=DEFAULT_PLATFORM):
    return platform(platform_id)['transport']


class B0Stream:
    """Reassemble B0-framed replies (B0, u16le body length, body) from UART chunks."""

    def __init__(self, body_lengths=None):
        self.body_lengths = frozenset(body_lengths or transport()['frame_body_lengths'])
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
                if size not in self.body_lengths:
                    del self.buffer[0]
                    self.discarded += 1
                    continue
                if len(self.buffer) < size + 3:
                    break
                frames.append(bytes(self.buffer))
                self.buffer.clear()
        return frames


def split_groups(frame, platform_id=DEFAULT_PLATFORM):
    """Return {group name: bytes} for a telemetry frame that matches the platform layout, else None."""
    t = transport(platform_id)
    if len(frame) != t['frame_bytes']:
        return None
    for first, last in t.get('zero_ranges', ()):
        if any(frame[first:last]):
            return None
    out = {}
    for name, group in t['groups'].items():
        offset, size, dids = group['offset'], group['size'], [int(d, 16) for d in group['dids']]
        payload = frame[offset:offset + size]
        if len(payload) != size or payload[0] != 0x62:
            return None
        if [int.from_bytes(payload[i:i + 2], 'big') for i in range(1, size, group.get('did_stride', 56))] != dids:
            return None
        out[name] = bytes(payload)
    return out


def decode_groups(groups, platform_id=DEFAULT_PLATFORM):
    """Decode the platform's channels from group payloads (offsets include the leading 0x62 byte)."""
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
    """Open a serial port with the dongle's settings. Any port name is accepted when given explicitly."""
    import serial
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
    unknown_frames: int
    bytes_received: int

    def as_dict(self):
        return dict(self.__dict__, writes_supported=False)


def record(port, seconds, out_path, platform_id=DEFAULT_PLATFORM, interval=0.05, on_values=None, stop=None):
    """Poll B0 for up to `seconds`, writing one JSON line per reply frame.

    Telemetry frames: {"t": seconds, "ch": {decoded channels}, "raw": {"A": hex, ...}}.
    Frames that do not match the platform layout: {"t": seconds, "frame": hex}.
    Raw bytes are kept so logs can be re-decoded when platform definitions improve.
    """
    if not 0 < seconds <= 3600 or not 0.02 <= interval <= 1:
        raise ValueError('Duration must be 0-3600 s and poll interval 0.02-1 s')
    plat = platform(platform_id)
    stream = B0Stream(plat['transport']['frame_body_lengths'])
    polls = frames = telemetry = unknown = received = 0
    start = time.monotonic()
    next_poll = start
    with Path(out_path).open('x', encoding='utf-8') as out:
        out.write(json.dumps({'format': 'agent-tune.log.v1', 'platform': plat['id'],
                              'platform_file': None if platform_id in platforms() else str(Path(platform_id).resolve()),
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
                t = round(time.monotonic() - start, 4)
                groups = split_groups(frame, platform_id)
                if groups is None:
                    unknown += 1
                    out.write(json.dumps({'t': t, 'frame': frame.hex()}) + '\n')
                    continue
                telemetry += 1
                values = decode_groups(groups, platform_id)
                out.write(json.dumps({'t': t, 'ch': values, 'raw': {k: v.hex() for k, v in groups.items()}}) + '\n')
                if on_values is not None:
                    on_values(t, values)
    return Summary(round(time.monotonic() - start, 3), polls, frames, telemetry, unknown, received)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
