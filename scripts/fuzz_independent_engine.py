"""Bounded, reproducible randomized WAD merge/content validation."""
import argparse
import gzip
import io
import json
from pathlib import Path
import random
import struct
import sys
import time
import zstandard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.build import merge_wads, verify_merge
from engine.wad import read_index
from engine.payload import read_payload


def make_archive(randomizer, entries):
    records, payloads = [], []
    cursor = 272 + 32*len(entries)
    for key, data in entries.items():
        kind = randomizer.choice((0,1,3))
        packed = (data if kind==0 else gzip.compress(data,mtime=0) if kind==1
                  else zstandard.ZstdCompressor().compress(data))
        records.append(struct.pack('<QIIIBBHQ',key,cursor,len(packed),len(data),kind,0,0,0))
        payloads.append(packed)
        cursor += len(packed)
    return b'RW\x03\x04'+bytes(264)+struct.pack('<I',len(entries))+b''.join(records)+b''.join(payloads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration-seconds',type=int,default=60)
    parser.add_argument('--seed',type=int,default=20261031)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    if not 1 <= args.duration_seconds <= 300:
        parser.error('Duration must be between 1 and 300 seconds')
    randomizer = random.Random(args.seed)
    started = time.monotonic()
    iterations = verified = 0
    next_progress = started+20
    while time.monotonic()-started < args.duration_seconds:
        original = {key:randomizer.randbytes(randomizer.randrange(1,4096))
                    for key in randomizer.sample(range(200),randomizer.randrange(1,40))}
        replacement = {key:randomizer.randbytes(randomizer.randrange(1,4096))
                       for key in randomizer.sample(range(200),randomizer.randrange(1,10))}
        left, right = make_archive(randomizer,original),make_archive(randomizer,replacement)
        output = io.BytesIO()
        merge_wads(io.BytesIO(left),io.BytesIO(right),output)
        verified += verify_merge(io.BytesIO(left),io.BytesIO(right),output)
        expected = original | replacement
        entries = read_index(output)
        assert {entry.path_hash for entry in entries} == set(expected)
        for entry in entries:
            assert read_payload(output,entry) == expected[entry.path_hash]
        # Malformed tables must never yield a payload outside the supplied file.
        damaged = bytearray(left)
        position = randomizer.randrange(268,min(len(damaged),304))
        damaged[position] ^= randomizer.randrange(1,256)
        try:
            parsed = read_index(io.BytesIO(damaged))
        except ValueError:
            pass
        else:
            assert all(272+32*len(parsed) <= e.offset <= len(damaged)
                       and e.offset+e.compressed_size <= len(damaged) for e in parsed)
        iterations += 1
        if time.monotonic() >= next_progress:
            print(json.dumps({'iterations':iterations,'verified_payloads':verified}),flush=True)
            next_progress = time.monotonic()+20
    report = {'seed':args.seed,'iterations':iterations,'verified_payloads':verified,
              'elapsed_seconds':round(time.monotonic()-started,3),'passed':True,
              'scope':'offline archive merge/decompression; no game interaction'}
    with args.report.open('x',encoding='utf-8') as target:
        json.dump(report,target,indent=2)
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
