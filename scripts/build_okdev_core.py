"""Build the pinned open-source CEF 108 core and its OKDEV frontend."""
from pathlib import Path
import ctypes
import os
import shutil
import subprocess
import sys
from build_pengu_loader import _find_msbuild, _build_environment
from build_cslol_stub import _find_vcvars

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'vendor/PenguLoader-1.1.6'


def main():
    npm = shutil.which('npm.cmd')
    vcvars = _find_vcvars()
    msbuild = [str(vcvars.parents[3] / 'MSBuild/Current/Bin/MSBuild.exe')] if vcvars else None
    if not npm or not msbuild:
        raise SystemExit('Node.js and Visual Studio C++ build tools are required')
    frontend = SOURCE / 'plugins'
    subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=frontend, check=True)
    subprocess.run([npm, 'run', 'build'], cwd=frontend, check=True)
    output = ROOT / 'build/okdev-core'
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(msbuild + [str(SOURCE/'core/core.vcxproj'), '/t:Build', '/m', '/v:minimal',
        '/p:Configuration=Release', '/p:Platform=x64', f'/p:OutDir={output}{os.sep}',
        f'/p:IntDir={output / "obj"}{os.sep}'], cwd=SOURCE/'core', env=_build_environment(), check=True)
    core = output/'core.dll'
    # Version export is side-effect free in this build process (not a League process).
    dll = ctypes.WinDLL(str(core))
    if dll[5000]() != 108:
        raise SystemExit('Unexpected CEF ABI in compiled core')
    binary = core.read_bytes()
    for required in (r"\OKDEV\config.ini", "OKDEV Loader core module"):
        if required.encode('utf-16le') not in binary:
            raise SystemExit('Compiled core is missing OKDEV identity: ' + required)
    if r"\Rose\config.ini".encode('utf-16le') in binary:
        raise SystemExit('Legacy data path unexpectedly present in core')
    shutil.copy2(core, ROOT/'Pengu Loader/core.dll')
    print('OKDEV core built and CEF 108 export verified')


if __name__ == '__main__':
    main()
