"""Read-only envelope measurements derived from our own KTuner 1.0.14.1 saves.

No calibration bytes are emitted. gzip is checked using the standard library;
the inner payload remains opaque and is not claimed to be an ECU ROM.
"""
import argparse
import hashlib
import json
import sys
import zlib
from pathlib import Path

MAX_PAYLOAD = 16 * 1024 * 1024


def inspect(data, max_payload=MAX_PAYLOAD):
    if len(data) < 35 or data[:7] != b"KTUNERK":
        raise ValueError("Not the observed KTUNERK envelope")
    declared = int.from_bytes(data[31:35], "big")
    if declared != len(data) - 35:
        raise ValueError("Envelope length field does not match remaining bytes")
    if data[35:38] != b"\x1f\x8b\x08":
        raise ValueError("No observed gzip stream at offset 35")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    payload = decoder.decompress(data[35:], max_payload + 1)
    if len(payload) > max_payload or decoder.unconsumed_tail:
        raise ValueError("Decoded payload exceeds size limit")
    if not decoder.eof or decoder.unused_data:
        raise ValueError("Truncated stream or trailing/concatenated data")
    return {
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "magic": "KTUNERK", "gzip_offset": 35,
        "length_field_offset": 31, "length_field_byte_order": "big",
        "compressed_size": declared, "gzip_integrity_verified": True,
        "decoded_size": len(payload),
        "decoded_sha256": hashlib.sha256(payload).hexdigest(),
        "inner_format": "unknown", "parameter_confirmed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = {p.name: inspect(p.read_bytes()) for p in args.files}
        if len(result) != len(args.files):
            raise ValueError("Input basenames must be unique")
        encoded = json.dumps(result, indent=2) + "\n"
        if args.out:
            args.out.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
    except (OSError, ValueError, zlib.error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
