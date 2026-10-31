"""Build an unsigned offline WAD artifact; never modify the installed game.

This is archive tooling, not an in-game runtime or a game-ready signature.
"""
import argparse
import json
import os
import struct
import tempfile
import zipfile
from pathlib import Path
from .package import inspect_package
from .wad import read_index, payload_digest
from .payload import read_payload


def merge_wads(original, replacement, output, *, protected_hashes=()):
    if output is original or output is replacement:
        raise ValueError('Output stream must be separate from inputs')
    original_entries = read_index(original)
    replacement_entries = read_index(replacement)
    if any(entry.path_hash in protected_hashes for entry in replacement_entries):
        raise ValueError('Replacing a shared subchunk table requires normalization')
    if any(entry.compression not in (0,1,3) for entry in replacement_entries):
        raise ValueError('Replacement redirects and subchunk tables are unsupported for now')
    for entry in replacement_entries:
        read_payload(replacement,entry)
    original.seek(0)
    header = original.read(272)
    replacement.seek(0)
    if replacement.read(4) != header[:4]:
        raise ValueError('WAD versions must match')
    # Preserve the complete entry records, including subchunk indices and flags.
    records = {}
    for source, entries in ((original, original_entries), (replacement, replacement_entries)):
        source.seek(272)
        raw_records = [source.read(32) for _ in entries]
        for entry, raw in zip(entries, raw_records):
            records[entry.path_hash] = (source, entry, raw)
    count = len(records)
    cursor = 272 + count * 32
    total = cursor + sum(entry.compressed_size for _, entry, _ in records.values())
    if total > 0xFFFFFFFF:
        raise ValueError('Output exceeds WAD offset capacity')
    # Deliberately unsigned. Do not masquerade as a signed game archive.
    output.write(header[:4] + bytes(264) + struct.pack('<I', count))
    ordered = [records[key] for key in sorted(records)]
    for _, entry, raw in ordered:
        output.write(raw[:8] + struct.pack('<I', cursor) + raw[12:])
        cursor += entry.compressed_size
    for source, entry, _ in ordered:
        source.seek(entry.offset)
        remaining = entry.compressed_size
        while remaining:
            block = source.read(min(remaining, 1024**2))
            if not block:
                raise ValueError('Source changed or was truncated during build')
            output.write(block)
            remaining -= len(block)
    return {'entries': count, 'replacements': len(replacement_entries),
            'bytes': total, 'signed': False, 'runtime_available': False,
            'game_ready': False}


def verify_merge(original, replacement, output):
    """Verify every merged record and stored payload against its source."""
    expected = {e.path_hash: (original, e) for e in read_index(original)}
    expected.update({e.path_hash: (replacement, e) for e in read_index(replacement)})
    actual = read_index(output)
    if len(actual) != len(expected):
        raise ValueError('Output entry count mismatch')
    for entry in actual:
        if entry.path_hash not in expected:
            raise ValueError('Unexpected output entry')
        source, previous = expected[entry.path_hash]
        fields = ('compressed_size', 'size', 'compression', 'subchunks', 'checksum', 'first_subchunk_index')
        if any(getattr(entry, field) != getattr(previous, field) for field in fields):
            raise ValueError('Output entry metadata mismatch')
        if payload_digest(output, entry) != payload_digest(source, previous):
            raise ValueError('Output payload mismatch')
    return len(actual)


def build(package: Path, original: Path, destination: Path):
    info = inspect_package(package)
    matches = [name for name in info['wad_entries']
               if name.split('/')[-1].casefold() == original.name.casefold()]
    if len(matches) != 1:
        raise ValueError('Expected one matching WAD payload')
    if destination.resolve() in (original.resolve(), package.resolve()):
        raise ValueError('Output cannot replace a source')
    # Exclusive creation prevents accidental overwrite, including existing links.
    created = False
    protected_hashes = set()
    normalized = original.as_posix().casefold()
    if '/data/final/' in normalized and normalized.endswith('.wad.client'):
        import xxhash
        logical = 'data/final/' + normalized.split('/data/final/',1)[1]
        toc_path = logical.removesuffix('.client') + '.subchunktoc'
        protected_hashes.add(xxhash.xxh64_intdigest(toc_path.encode('utf-8')))
    try:
        with original.open('rb') as base, zipfile.ZipFile(package) as archive:
            with tempfile.TemporaryFile() as payload:
                with archive.open(matches[0]) as source:
                    while block := source.read(1024**2):
                        payload.write(block)
                with destination.open('xb') as output:
                    created = True
                    report = merge_wads(base, payload, output,protected_hashes=protected_hashes)
                    output.flush()
                    os.fsync(output.fileno())
                with destination.open('rb') as check:
                    report['verified_payloads'] = verify_merge(base, payload, check)
        return report
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('original', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.package, args.original, args.destination), indent=2))


if __name__ == '__main__':
    main()
