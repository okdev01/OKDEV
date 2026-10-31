"""Read-only WAD v3 index reader, with no LTK or mod-tools dependency.

Format reference: https://github.com/CommunityDragon/CDTB/blob/master/cdtb/wad.py
Only table metadata is read. No game files are changed or signatures generated.
"""
from dataclasses import dataclass
from typing import BinaryIO
import struct


@dataclass(frozen=True)
class Entry:
    path_hash: int
    offset: int
    compressed_size: int
    size: int
    compression: int
    subchunks: int
    checksum: int
    first_subchunk_index: int = 0


def payload_digest(source: BinaryIO, entry: Entry) -> str:
    """Hash stored bytes in bounded blocks, without decompression."""
    import hashlib
    source.seek(entry.offset)
    remaining = entry.compressed_size
    digest = hashlib.sha256()
    while remaining:
        block = source.read(min(remaining, 1024**2))
        if not block:
            raise ValueError('Truncated WAD payload')
        digest.update(block)
        remaining -= len(block)
    return digest.hexdigest()


def read_index(source: BinaryIO) -> tuple[Entry, ...]:
    source.seek(0, 2)
    length = source.tell()
    source.seek(0)
    header = source.read(272)
    if len(header) != 272 or header[:2] != b'RW':
        raise ValueError('Invalid or truncated WAD header')
    major, minor = header[2:4]
    if major != 3 or minor > 4:
        raise ValueError(f'Unsupported WAD version {major}.{minor}')
    count = struct.unpack_from('<I', header, 268)[0]
    table_end = 272 + count * 32
    if count > 1000000 or table_end > length:
        raise ValueError('Invalid WAD entry count')
    records = []
    hashes = set()
    for _ in range(count):
        raw = source.read(32)
        if len(raw) != 32:
            raise ValueError('Truncated WAD table')
        path_hash, offset, packed, size, flags, high, low, checksum = struct.unpack('<QIIIBBHQ', raw)
        if path_hash in hashes:
            raise ValueError('Duplicate WAD path hash')
        hashes.add(path_hash)
        if offset < table_end or offset + packed > length:
            raise ValueError('WAD payload outside data area')
        compression = flags & 15
        if compression > 4:
            raise ValueError('Unsupported WAD compression')
        if compression == 0 and packed != size:
            raise ValueError('Invalid uncompressed entry length')
        first_index = low + ((high << 16) if minor >= 4 else 0)
        records.append(Entry(path_hash, offset, packed, size, compression, flags >> 4, checksum, first_index))
    return tuple(records)


def compare_indexes(original: tuple[Entry, ...], replacement: tuple[Entry, ...]) -> dict:
    """Plan overrides; never write into the original archive."""
    original_hashes = {entry.path_hash for entry in original}
    return {
        'original_entries': len(original),
        'package_entries': len(replacement),
        'replaced_hashes': [f'{e.path_hash:016x}' for e in replacement if e.path_hash in original_hashes],
        'added_hashes': [f'{e.path_hash:016x}' for e in replacement if e.path_hash not in original_hashes],
        'runtime_available': False,
    }
