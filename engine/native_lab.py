"""Verify a prepared choice through our own native fixture, never the game."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from .validate import validate


def verify_response(response, archive):
    if (not isinstance(response,dict) or response.get('scope')!='own_process_copied_wad'
            or response.get('game_runtime_available') is not False
            or response.get('source_unchanged') is not True
            or any(response.get(key) is not True for key in ('wide','ansi','memory_mapped'))
            or response.get('original_sha256')!=archive['source_sha256']
            or response.get('redirected_sha256')!=archive['output_sha256']):
        raise ValueError('Native fixture did not verify the expected prepared archive')


def check_prepared(directory: Path, game: Path, lab_directory: Path, *, expected_selection=None):
    directory,game,lab_directory=(Path(p).resolve() for p in (directory,game,lab_directory))
    initial=validate(directory,expected_selection=expected_selection,game=game)
    raw=(directory/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=initial['manifest_sha256']:
        raise ValueError('Manifest changed before the native fixture started')
    manifest=json.loads(raw)
    executable=lab_directory/'OKDEV_Engine_Harness.exe'
    library=lab_directory/'okdev_io_lab.dll'
    if not executable.is_file() or not library.is_file():
        raise FileNotFoundError('Build the local native fixture with scripts/build_io_lab.py first')
    results=[]
    for archive in manifest['archives']:
        relative=archive['path']
        with tempfile.TemporaryDirectory(prefix='okdev-native-lab-') as temporary:
            command=[str(executable),str(library),temporary,'--wad',str(game/relative),str(directory/relative)]
            completed=subprocess.run(command,capture_output=True,text=True,check=True,timeout=120,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            response=json.loads(completed.stdout)
            verify_response(response,archive)
            results.append({'path':relative,**response})
    # A game update or output modification during the fixture invalidates it.
    final=validate(directory,expected_selection=expected_selection,game=game)
    if final['manifest_sha256']!=initial['manifest_sha256']:
        raise ValueError('Selection manifest changed during native verification')
    return {'state':'native_fixture_verified','selection':manifest['selection'],'archives':results,
            'scope':'own executable only; does not load code into League',
            'runtime_available':False,'game_ready':False,'applied':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--game',required=True,type=Path)
    parser.add_argument('--lab-directory',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args(argv)
    report=check_prepared(args.directory,args.game,args.lab_directory)
    with args.report.open('x',encoding='utf-8') as output:
        json.dump(report,output,indent=2)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
