$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    & .venv/Scripts/python.exe -m unittest test.test_ltk_maintenance test.test_ltk_update test.test_ltk_recovery test.test_ltk_delivery test.test_ltk_compat -q
    if ($LASTEXITCODE -ne 0) { throw 'Maintenance tests failed' }
    & .venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath output/maintained --workpath build/maintenance OKDEV_Maintenance.spec
    if ($LASTEXITCODE -ne 0) { throw 'Maintenance build failed' }
    $destination = 'output/maintained/OKDEV_Maintenance'
    foreach ($entry in @(@('Kontrol', 'diagnose'), @('Onar', 'repair'))) {
        $content = '@echo off' + "`r`n" + '"%~dp0OKDEV_Maintenance.exe" ' + $entry[1] + "`r`npause`r`n"
        [IO.File]::WriteAllText((Join-Path (Resolve-Path $destination) ($entry[0] + '.cmd')), $content, [Text.Encoding]::ASCII)
    }
    Copy-Item -LiteralPath 'docs/LTK_MAINTENANCE.md' -Destination "$destination/BAKIM.md"
} finally { Pop-Location }
