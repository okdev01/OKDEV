"""Preserve opaque PROP entry payloads when preparing base-slot skin supplements.

Only the entry identity changes; field data (including newer game types) stays
byte-for-byte identical. This is an offline build helper, not a game writer.
"""
from dataclasses import dataclass
import struct


def name_to_hex(name):
    value = 2166136261
    for byte in name.lower().encode('utf-8'):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return f'{value:08x}'


@dataclass
class Entry:
    type: str
    hash: str
    payload: bytes


class BIN:
    def __init__(self, signature='PROP', version=3, links=None, entries=None):
        if signature != 'PROP' or version != 3:
            raise ValueError('Only PROP v3 is supported')
        self.links = list(links or [])
        self.entries = list(entries or [])

    def read(self, path='', *, raw):
        offset = 0

        def take(size):
            nonlocal offset
            if size < 0 or offset + size > len(raw):
                raise ValueError('Truncated PROP')
            result = raw[offset:offset + size]
            offset += size
            return result

        def integer(fmt):
            return struct.unpack(fmt, take(struct.calcsize(fmt)))[0]

        if take(8) != b'PROP\x03\x00\x00\x00':
            raise ValueError('Only PROP v3 is supported')
        count = integer('<I')
        if count > 10000:
            raise ValueError('Excessive link count')
        self.links = [take(integer('<H')).decode('utf-8') for _ in range(count)]
        count = integer('<I')
        if count > 100000:
            raise ValueError('Excessive entry count')
        types = [integer('<I') for _ in range(count)]
        self.entries = []
        for kind in types:
            size = integer('<I')
            if size < 6:
                raise ValueError('Invalid entry size')
            identity = integer('<I')
            payload = take(size - 4)
            self.entries.append(Entry(f'{kind:08x}', f'{identity:08x}', payload))
        if offset != len(raw):
            raise ValueError('Unexpected trailing PROP data')

    def write(self, path='', *, raw=True):
        result = bytearray(b'PROP\x03\x00\x00\x00')
        result += struct.pack('<I', len(self.links))
        for link in self.links:
            encoded = link.encode('utf-8')
            result += struct.pack('<H', len(encoded)) + encoded
        result += struct.pack('<I', len(self.entries))
        for entry in self.entries:
            result += struct.pack('<I', int(entry.type, 16))
        for entry in self.entries:
            result += struct.pack('<II', 4 + len(entry.payload), int(entry.hash, 16)) + entry.payload
        return bytes(result)
