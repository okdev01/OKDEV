import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile
from .package import inspect_package


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)/'test.fantome'

    def write(self, name='WAD/Kayn.wad.client', metadata=None, extra=None):
        with zipfile.ZipFile(self.path,'w') as archive:
            archive.writestr('META/info.json',json.dumps({'Name':'Test'} if metadata is None else metadata))
            entry = zipfile.ZipInfo()
            # ZipInfo's constructor normalizes Windows separators; assign the
            # wire name afterwards so this really tests a hostile archive.
            entry.filename = name
            archive.writestr(entry,b'payload')
            if extra:
                extra(archive)

    def test_valid_package_is_read_without_extraction(self):
        self.write()
        before = self.path.read_bytes()
        info = inspect_package(self.path)
        self.assertEqual(info['name'],'Test')
        self.assertEqual(info['wad_entries'],['WAD/Kayn.wad.client'])
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(list(self.path.parent.iterdir()),[self.path])

    def test_unsafe_paths_are_rejected(self):
        for name in ('../escape','WAD/../escape','/absolute','C:/absolute','WAD\\escape','WAD/./escape'):
            self.write(name=name)
            with self.subTest(name=name),self.assertRaises(ValueError):
                inspect_package(self.path)

    def test_case_collisions_and_duplicate_entries_are_rejected(self):
        for name in ('WAD/Kayn.wad.client','wad/kayn.wad.client'):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                self.write(extra=lambda archive:archive.writestr(name,b'other'))
            with self.subTest(name=name),self.assertRaises(ValueError):
                inspect_package(self.path)

    def test_symlink_is_rejected(self):
        link = zipfile.ZipInfo('WAD/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK|0o777)<<16
        self.write(extra=lambda archive:archive.writestr(link,b'/outside'))
        with self.assertRaises(ValueError):
            inspect_package(self.path)

    def test_invalid_name_is_rejected(self):
        for metadata in ({'Name':''},{'Name':123},{'Name':' '},[],{'Author':'test'}):
            self.write(metadata=metadata)
            with self.subTest(metadata=metadata),self.assertRaises(ValueError):
                inspect_package(self.path)


if __name__ == '__main__':
    unittest.main()
