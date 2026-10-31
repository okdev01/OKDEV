"""Compile and test the original OKDEV in-process file-I/O prototype."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def find_vcvars():
    import os
    vswhere=Path(os.environ.get('ProgramFiles(x86)',''))/'Microsoft Visual Studio/Installer/vswhere.exe'
    if not vswhere.is_file():
        return None
    found=subprocess.run([str(vswhere),'-latest','-products','*','-requires',
                          'Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],
                         capture_output=True,text=True,check=True)
    for value in found.stdout.splitlines():
        candidate=Path(value.strip())/'VC/Auxiliary/Build/vcvars64.bat'
        if candidate.is_file():
            return candidate
    return None


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda:source.read(1024**2),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'output/io-lab-validation.json')
    parser.add_argument('--original-wad',type=Path)
    parser.add_argument('--replacement-wad',type=Path)
    args=parser.parse_args()
    if bool(args.original_wad)!=bool(args.replacement_wad):
        parser.error('Both original and replacement WAD paths are required')
    vcvars=find_vcvars()
    if not vcvars:
        raise RuntimeError('MSVC x64 compiler is unavailable')
    source=ROOT/'native/okdev_io_lab'
    output=ROOT/'output/io-lab'
    output.mkdir(parents=True,exist_ok=True)
    testing=output/'testing'
    (testing/'unsupported').mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='io-lab-build-',dir=ROOT/'output') as temporary:
        work=Path(temporary)
        script=work/'build.cmd'
        script.write_text(
            '@echo off\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n'+f'call "{vcvars}" >nul || exit /b 1\n'+
            f'cl /nologo /std:c++17 /EHsc /utf-8 /W4 /WX /O2 /MT /LD "{source / "okdev_io_lab.cpp"}" /link /OUT:"{output / "okdev_io_lab.dll"}" || exit /b 1\n'+
            f'cl /nologo /std:c++17 /EHsc /utf-8 /W4 /WX /O2 /MT /LD /DOKDEV_IO_TEST_FAULT "{source / "okdev_io_lab.cpp"}" /link /OUT:"{testing / "okdev_io_lab_fault.dll"}" || exit /b 1\n'+
            f'cl /nologo /std:c++17 /EHsc /utf-8 /W4 /WX /O2 /MT "{source / "unsupported_host.cpp"}" /link /OUT:"{testing / "unsupported/OKDEV_Engine_Harness.exe"}" || exit /b 1\n'+
            f'cl /nologo /std:c++17 /EHsc /utf-8 /W4 /WX /O2 /MT "{source / "harness.cpp"}" /link bcrypt.lib /OUT:"{output / "OKDEV_Engine_Harness.exe"}" || exit /b 1\n',encoding='utf-8')
        subprocess.run(['cmd','/d','/c',str(script)],cwd=work,check=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix='io-lab-fixture-',dir=ROOT/'output') as temporary:
        root=Path(temporary).resolve()
        assert root.is_relative_to((ROOT/'output').resolve())
        result=subprocess.run([str(output/'OKDEV_Engine_Harness.exe'),str(output/'okdev_io_lab.dll'),str(root/'normal')],capture_output=True,text=True,check=True)
        results.append(json.loads(result.stdout))
        result=subprocess.run([str(output/'OKDEV_Engine_Harness.exe'),str(output/'okdev_io_lab.dll'),
                               str(root/'reload'),'--reload'],capture_output=True,text=True,check=True)
        results.append(json.loads(result.stdout))
        result=subprocess.run([str(output/'OKDEV_Engine_Harness.exe'),str(testing/'okdev_io_lab_fault.dll'),
                               str(root/'rollback'),'--rollback'],capture_output=True,text=True,check=True)
        results.append(json.loads(result.stdout))
        result=subprocess.run([str(testing/'unsupported/OKDEV_Engine_Harness.exe'),str(output/'okdev_io_lab.dll'),
                               str(root/'unsupported')],capture_output=True,text=True,check=True)
        results.append(json.loads(result.stdout))
        if args.original_wad:
            before=sha256(args.original_wad)
            result=subprocess.run([str(output/'OKDEV_Engine_Harness.exe'),str(output/'okdev_io_lab.dll'),str(root/'real-wad'),
                                   '--wad',str(args.original_wad.resolve()),str(args.replacement_wad.resolve())],capture_output=True,text=True,check=True)
            assert sha256(args.original_wad)==before
            results.append(json.loads(result.stdout))
        denied=output/'OKDEV_Engine_NotHarness.exe'
        shutil.copyfile(output/'OKDEV_Engine_Harness.exe',denied)
        result=subprocess.run([str(denied),str(output/'okdev_io_lab.dll'),str(root/'denied'),'--deny'],capture_output=True,text=True,check=True)
        results.append(json.loads(result.stdout))
    report={'scope':'own executable only; no League process accessed','game_runtime_available':False,
            'checks':results,'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in source.glob('*') if p.is_file()}}
    args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
