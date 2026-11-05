import struct
import unittest

from scripts.skin_bin_patch import BIN, Entry, name_to_hex


class SkinBinPatchTests(unittest.TestCase):
    def test_opaque_new_fields_survive_identity_change(self):
        payload = b'\x01\x00' + bytes(range(256))
        original = BIN(links=['DATA/Characters/Ahri/Ahri.bin'], entries=[
            Entry(name_to_hex('SkinCharacterDataProperties'), name_to_hex('Characters/Ahri/Skins/Skin97'), payload)])
        encoded = original.write()
        parsed = BIN()
        parsed.read(raw=encoded)
        self.assertEqual(parsed.write(), encoded)
        parsed.entries[0].hash = name_to_hex('Characters/Ahri/Skins/Skin0')
        changed = BIN()
        changed.read(raw=parsed.write())
        self.assertEqual(changed.entries[0].payload, payload)
        self.assertEqual(changed.links, original.links)
        self.assertNotEqual(parsed.write(), encoded)

    def test_rejects_truncation_wrong_version_and_trailing_bytes(self):
        raw = BIN(entries=[Entry('12345678', '87654321', b'\x00\x00')]).write()
        for invalid in (raw[:-1], raw + b'\x00', b'PTCH' + raw[4:], raw[:4] + struct.pack('<I', 4) + raw[8:]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    BIN().read(raw=invalid)

    def test_rejects_entry_size_that_would_consume_next_entry(self):
        raw = bytearray(BIN(entries=[Entry('12345678', '87654321', b'\x00\x00')]).write())
        struct.pack_into('<I', raw, 20, 0xffffffff)
        with self.assertRaises(ValueError):
            BIN().read(raw=bytes(raw))
