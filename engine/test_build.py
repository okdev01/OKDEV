import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from .build import merge_wads, build, verify_merge
from .test_wad import fixture
from .wad import read_index


class BuildTests(unittest.TestCase):
    def test_shared_subchunk_table_cannot_be_replaced(self):
        output = io.BytesIO()
        with self.assertRaises(ValueError):
            merge_wads(io.BytesIO(fixture()),io.BytesIO(fixture()),output,protected_hashes={42})
        self.assertEqual(output.getvalue(),b'')

    def test_aliasing_input_stream_is_rejected_without_changes(self):
        original = io.BytesIO(fixture())
        with self.assertRaises(ValueError):
            merge_wads(original,io.BytesIO(fixture()),original)
        self.assertEqual(original.getvalue(),fixture())

    def test_corrupted_output_is_rejected(self):
        output = io.BytesIO()
        merge_wads(io.BytesIO(fixture()),io.BytesIO(fixture()),output)
        output.seek(-1,2)
        output.write(b'X')
        with self.assertRaises(ValueError):
            verify_merge(io.BytesIO(fixture()),io.BytesIO(fixture()),output)

    def test_chunked_replacement_is_rejected_before_output(self):
        data = bytearray(fixture())
        data[292] = 0x14
        output = io.BytesIO()
        with self.assertRaises(ValueError):
            merge_wads(io.BytesIO(fixture()),io.BytesIO(data),output)
        self.assertEqual(output.getvalue(),b'')

    def test_replacement_payload_and_unsigned_output(self):
        base = io.BytesIO(fixture())
        mod = io.BytesIO(fixture()[:-3] + b'xyz')
        result = io.BytesIO()
        report = merge_wads(base, mod, result)
        entry, = read_index(result)
        result.seek(entry.offset)
        self.assertEqual(result.read(3), b'xyz')
        self.assertEqual(base.getvalue(), fixture())
        self.assertFalse(report['game_ready'])
        self.assertEqual(result.getvalue()[4:268], bytes(264))

    def test_added_entry_and_preserved_original_payload(self):
        modified = bytearray(fixture()[:-3] + b'xyz')
        struct.pack_into('<Q', modified, 272, 43)
        output = io.BytesIO()
        merge_wads(io.BytesIO(fixture()), io.BytesIO(modified), output)
        entries = read_index(output)
        self.assertEqual([e.path_hash for e in entries], [42, 43])
        for entry, expected in zip(entries, (b'abc', b'xyz')):
            output.seek(entry.offset)
            self.assertEqual(output.read(3), expected)

    def test_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, original, output = root/'mod.fantome', root/'Kayn.wad.client', root/'out.wad'
            original.write_bytes(fixture())
            output.write_bytes(b'keep')
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('META/info.json', '{"Name":"fixture"}')
                archive.writestr('WAD/Kayn.wad.client', fixture())
            with self.assertRaises(FileExistsError):
                build(package, original, output)
            self.assertEqual(output.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
