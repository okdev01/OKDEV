"""Read-only comparison: python -m engine.plan package.fantome original.wad.client"""
import argparse
import json
import zipfile
from .package import inspect_package
from .wad import read_index, compare_indexes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('original')
    args = parser.parse_args(argv)
    from pathlib import Path
    package = Path(args.package)
    info = inspect_package(package)
    name = Path(args.original).name.casefold()
    matches = [p for p in info['wad_entries'] if p.split('/')[-1].casefold() == name]
    if len(matches) != 1:
        parser.error('Package must contain exactly one matching WAD archive')
    with open(args.original, 'rb') as source:
        original = read_index(source)
    with zipfile.ZipFile(package) as archive, archive.open(matches[0]) as source:
        replacement = read_index(source)
    print(json.dumps({'package': info['name'], **compare_indexes(original, replacement)}, indent=2))


if __name__ == '__main__':
    main()
