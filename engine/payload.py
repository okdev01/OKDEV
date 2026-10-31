"""Bounded decompression for independently read WAD entries.

The caller supplies the archive's subchunk table for type-4 content. Redirect
entries are deliberately not followed; this reader never resolves disk paths.
"""
import struct
import zlib
import xxhash
import zstandard
from .wad import Entry

MAX_PAYLOAD = 128 * 1024**2


def _zstd(data, expected):
    if expected > MAX_PAYLOAD:
        raise ValueError('Expanded payload exceeds limit')
    try:
        # Inspect the frame's byte-sized window explicitly: backend versions
        # differ in how max_window_size is interpreted by streaming APIs.
        parameters = zstandard.get_frame_parameters(data)
        if parameters.window_size > MAX_PAYLOAD:
            raise ValueError('Zstandard window exceeds limit')
        if parameters.content_size not in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR, expected):
            raise ValueError('Zstandard frame size differs from WAD entry')
        result = zstandard.ZstdDecompressor().decompress(
            data,max_output_size=max(expected,1),allow_extra_data=False)
    except zstandard.ZstdError as error:
        raise ValueError('Invalid Zstandard payload') from error
    if len(result) != expected:
        raise ValueError('Zstandard payload length mismatch')
    return result


def read_payload(source, entry: Entry, subchunk_table=None):
    if entry.size > MAX_PAYLOAD or entry.compressed_size > MAX_PAYLOAD:
        raise ValueError('Payload exceeds read limit')
    source.seek(entry.offset)
    data = source.read(entry.compressed_size)
    if len(data) != entry.compressed_size:
        raise ValueError('Truncated payload')
    if entry.checksum and xxhash.xxh3_64_intdigest(data) != entry.checksum:
        raise ValueError('WAD payload checksum mismatch')
    if entry.compression == 0:
        result = data
    elif entry.compression == 1:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            result = decoder.decompress(data, entry.size + 1)
        except zlib.error as error:
            raise ValueError('Invalid gzip payload') from error
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Incomplete, oversized or concatenated gzip payload')
    elif entry.compression == 3:
        result = _zstd(data, entry.size)
    elif entry.compression == 4:
        if subchunk_table is None or not entry.subchunks:
            raise ValueError('Subchunk table is required')
        start = entry.first_subchunk_index * 16
        end = start + entry.subchunks * 16
        if end > len(subchunk_table):
            raise ValueError('Subchunk table index out of bounds')
        chunks, offset, expanded = [], 0, 0
        for position in range(start, end, 16):
            packed, size, checksum = struct.unpack_from('<IIQ', subchunk_table, position)
            if offset + packed > len(data) or expanded + size > entry.size:
                raise ValueError('Subchunk range exceeds payload')
            chunk = data[offset:offset+packed]
            if xxhash.xxh3_64_intdigest(chunk) != checksum:
                raise ValueError('Subchunk checksum mismatch')
            chunks.append(chunk if packed == size else _zstd(chunk, size))
            offset += packed
            expanded += size
        if offset != len(data):
            raise ValueError('Unconsumed subchunk data')
        result = b''.join(chunks)
    else:
        raise ValueError('Redirect or unsupported payload type')
    if len(result) != entry.size:
        raise ValueError('Expanded payload length mismatch')
    return result
