"""Durable publication of a small, local build manifest."""
import json
import os
import tempfile
from pathlib import Path


def write_manifest(directory: Path, manifest: dict):
    data = json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
    if len(data) > 4*1024**2:
        raise ValueError('Build manifest exceeds limit')
    descriptor, name = tempfile.mkstemp(prefix='.manifest-',dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary,directory/'manifest.json')
    finally:
        temporary.unlink(missing_ok=True)
