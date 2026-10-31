from dataclasses import replace
import gzip
import io
import struct
import unittest
import xxhash
import zstandard
from .wad import Entry
from .payload import read_payload


class PayloadTests(unittest.TestCase):
    def entry(self, data, size, compression, **kwargs):
        return Entry(1, 0, len(data), size, compression, 0, 0, **kwargs)

    def test_plain_gzip_zstd(self):
        raw = b'PROP' + bytes(range(256))*10
        for kind, data in ((0,raw),(1,gzip.compress(raw)),(3,zstandard.ZstdCompressor().compress(raw))):
            with self.subTest(kind=kind):
                self.assertEqual(read_payload(io.BytesIO(data), self.entry(data,len(raw),kind)),raw)

    def test_expansion_cannot_exceed_declared_size(self):
        raw = b'x'*10000
        for kind, data in ((1,gzip.compress(raw)),(3,zstandard.ZstdCompressor().compress(raw))):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                read_payload(io.BytesIO(data),self.entry(data,1,kind))

    def test_streamed_frame_without_content_size(self):
        raw = b'PROP' + b'x'*4000
        compressor = zstandard.ZstdCompressor().compressobj()
        packed = compressor.compress(raw) + compressor.flush()
        self.assertGreater(zstandard.get_frame_parameters(packed).window_size, 128*1024)
        self.assertEqual(read_payload(io.BytesIO(packed),self.entry(packed,len(raw),3)),raw)

    def test_subchunks_mix_raw_and_compressed_with_checksums(self):
        raw = b'abc'
        expanded = b'z'*100
        packed = zstandard.ZstdCompressor().compress(expanded)
        data = raw + packed
        table = b''.join(struct.pack('<IIQ',len(chunk),size,xxhash.xxh3_64_intdigest(chunk))
                         for chunk,size in ((raw,len(raw)),(packed,len(expanded))))
        entry = replace(self.entry(data,103,4),subchunks=2)
        self.assertEqual(read_payload(io.BytesIO(data),entry,table),raw+expanded)
        with self.assertRaises(ValueError):
            read_payload(io.BytesIO(b'X'+data[1:]),entry,table)
        with self.assertRaises(ValueError):
            read_payload(io.BytesIO(data),entry,table[:16])

    def test_redirect_is_not_followed(self):
        data = b'not-a-path'
        with self.assertRaises(ValueError):
            read_payload(io.BytesIO(data),self.entry(data,len(data),2))

    def test_stored_wad_checksum_detects_valid_length_corruption(self):
        original = b'abc'
        entry = replace(self.entry(original,3,0),checksum=xxhash.xxh3_64_intdigest(original))
        self.assertEqual(read_payload(io.BytesIO(original),entry),original)
        with self.assertRaises(ValueError):
            read_payload(io.BytesIO(b'xbc'),entry)

    def test_truncated_and_malformed_payloads(self):
        for kind in (0,1,3):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                read_payload(io.BytesIO(b'x'),Entry(1,0,50,10,kind,0,0))

    def test_incomplete_compressed_frame_is_not_accepted_as_complete(self):
        raw = b'content'*100
        for kind, packed in ((1,gzip.compress(raw)),
                             (3,zstandard.ZstdCompressor(write_checksum=True).compress(raw))):
            for data in (packed[:-1],packed+b'garbage'):
                with self.subTest(kind=kind,length=len(data)),self.assertRaises(ValueError):
                    read_payload(io.BytesIO(data),self.entry(data,len(raw),kind))


if __name__ == '__main__':
    unittest.main()
