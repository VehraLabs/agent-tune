"""The outer .kcl container: a KTUNERK header followed by a gzip stream.

Only the header and gzip integrity are checked here. The decompressed body is
interpreted by `decode`.
"""
import hashlib
import zlib

MAX_PAYLOAD = 16 * 1024 * 1024
GZIP_OFFSET = 35


def inspect(data, max_payload=MAX_PAYLOAD):
    if len(data) < GZIP_OFFSET or data[:7] != b'KTUNERK':
        raise ValueError('Not a KTuner .kcl file (missing KTUNERK header)')
    declared = int.from_bytes(data[31:35], 'big')
    if declared != len(data) - GZIP_OFFSET:
        raise ValueError('Header length field does not match the file size')
    if data[GZIP_OFFSET:GZIP_OFFSET + 3] != b'\x1f\x8b\x08':
        raise ValueError('No gzip stream after the header')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    payload = decoder.decompress(data[GZIP_OFFSET:], max_payload + 1)
    if len(payload) > max_payload or decoder.unconsumed_tail:
        raise ValueError('Decompressed body exceeds the size limit')
    if not decoder.eof or decoder.unused_data:
        raise ValueError('Truncated gzip stream or trailing data')
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'compressed_size': declared,
            'decoded_size': len(payload), 'decoded_sha256': hashlib.sha256(payload).hexdigest()}
