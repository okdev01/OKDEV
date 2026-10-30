"""Generate installer/version metadata from config.py without importing the app."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def synchronize(check=False):
    match = re.search(r'^APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', (ROOT / 'config.py').read_text(encoding='utf-8'), re.M)
    if not match:
        raise ValueError('APP_VERSION must be a three-part release version')
    version = match[1]
    numeric = version + '.0'
    tuple_version = ','.join(numeric.split('.'))
    replacements = {
        'installer.iss': [(r'(?m)^#define MyAppVersion "[^"]+"', f'#define MyAppVersion "{version}"'),
                          (r'(?m)^#define MyAppVersionInfo "[^"]+"', f'#define MyAppVersionInfo "{numeric}"')],
        'setup_app/setup.py': [(r"(?m)^VERSION = '[^']+'", f"VERSION = '{version}'")],
        'okdev_version.txt': [(r'(filevers|prodvers)=\([^)]*\)', lambda m: m[1] + '=(' + tuple_version + ')'),
                              (r"StringStruct\('(FileVersion|ProductVersion)', '[^']+'\)",
                               lambda m: "StringStruct('" + m[1] + "', '" + version + "')")],
    }
    stale = []
    for name, rules in replacements.items():
        path = ROOT / name
        before = after = path.read_text(encoding='utf-8')
        for pattern, replacement in rules:
            after, count = re.subn(pattern, replacement, after)
            if not count:
                raise ValueError('Missing version field: ' + name)
        if before != after:
            stale.append(name)
            if not check:
                path.write_text(after, encoding='utf-8')
    if check and stale:
        raise ValueError('Stale release metadata: ' + ', '.join(stale))
    return version


def component_metadata(name, filename, description):
    """Give each shipped executable its own identity and the shared version."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid component name')
    synchronize(check=True)
    from PyInstaller.utils.win32 import versioninfo
    info = versioninfo.load_version_info_from_text_file(str(ROOT / 'okdev_version.txt'))
    fields = {'InternalName': name, 'OriginalFilename': filename, 'FileDescription': description}
    for block in info.kids:
        if isinstance(block, versioninfo.StringFileInfo):
            for table in block.kids:
                for item in table.kids:
                    if item.name in fields:
                        item.val = fields[item.name]
    target = ROOT / 'build' / f'{name}-version.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(info), encoding='utf-8')
    return target


if __name__ == '__main__':
    print(synchronize(check='--check' in sys.argv))
