"""Regression tests for false expiration after the wall-clock cutoff."""
import runpy
import struct
import tempfile
import unittest
from pathlib import Path

module = runpy.run_path(str(Path(__file__).parents[1] / 'injection/tools/patcher.py'))
Status = module['LtkPatcherStatus']
read_build = module['read_game_build']


class PatcherBuildDateTests(unittest.TestCase):
    def test_old_supported_build_does_not_expire_with_calendar(self):
        self.assertFalse(Status(Path('host'), Path('dll'), [], 100, 99).expired)

    def test_cutoff_is_inclusive(self):
        self.assertFalse(Status(Path('host'), Path('dll'), [], 100, 100).expired)

    def test_newer_build_still_requires_update(self):
        self.assertTrue(Status(Path('host'), Path('dll'), [], 100, 101).expired)

    def test_unknown_build_defers_to_native_check(self):
        self.assertFalse(Status(Path('host'), Path('dll'), [], 100).expired)

    def test_pe_timestamp_and_bad_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'game.exe'
            self.assertIsNone(read_build(path))
            data = bytearray(140)
            data[:2] = b'MZ'
            struct.pack_into('<I', data, 60, 128)
            data[128:132] = b'PE\0\0'
            struct.pack_into('<I', data, 136, 1790205875)
            path.write_bytes(data)
            self.assertEqual(read_build(path), 1790205875)
            for invalid in (b'', b'MZ', data[:135], b'not a PE file'):
                path.write_bytes(invalid)
                self.assertIsNone(read_build(path))


if __name__ == '__main__':
    unittest.main()
