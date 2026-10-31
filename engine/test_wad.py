import io
import struct
import unittest
from .wad import read_index, compare_indexes


def fixture(offset=304, packed=3, size=3, flags=0, count=1):
    header = b'RW\x03\x04' + bytes(264) + struct.pack('<I', count)
    return header + struct.pack('<QIIIBBHQ', 42, offset, packed, size, flags, 0, 0, 0) + b'abc'


class WadTests(unittest.TestCase):
    def test_index_and_override(self):
        entries = read_index(io.BytesIO(fixture()))
        self.assertEqual(entries[0].path_hash, 42)
        plan = compare_indexes(entries, entries)
        self.assertEqual(plan['replaced_hashes'], ['000000000000002a'])
        self.assertFalse(plan['runtime_available'])

    def test_rejects_truncated_table(self):
        with self.assertRaises(ValueError):
            read_index(io.BytesIO(fixture(count=2)))

    def test_rejects_invalid_ranges_and_compression(self):
        for kwargs in ({'offset': 0}, {'packed': 100}, {'size': 4}, {'flags': 15}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                read_index(io.BytesIO(fixture(**kwargs)))

    def test_rejects_unknown_version(self):
        with self.assertRaises(ValueError):
            read_index(io.BytesIO(b'RW\x04\x00' + fixture()[4:]))


if __name__ == '__main__':
    unittest.main()
