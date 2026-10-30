"""Verify the launcher progress connection with a real local release archive."""
import hashlib
import json
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def run(dialog, capture, root):
    from launcher.core.launcher import _perform_update
    from launcher.update.update_installer import UpdateInstaller
    from utils.system.win32_base import user32
    source = root / 'release/OKDEV_Update_2.0.0.zip'
    observed = []
    captured = False
    with tempfile.TemporaryDirectory(prefix='okdev-progress-qa-', dir=root/'build') as temp:
        from pathlib import Path
        archive = Path(temp) / 'update.zip'
        shutil.copy2(source, archive)
        def perform(status, progress, bytes_callback, **kwargs):
            nonlocal captured
            bytes_callback(source.stat().st_size, source.stat().st_size)
            dialog.pump_messages()
            assert user32.SendMessageW(dialog.progress_hwnd, 0x0408, 0, 0) == 100
            def measured(value):
                nonlocal captured
                progress(value)
                dialog.pump_messages()
                actual = user32.SendMessageW(dialog.progress_hwnd, 0x0408, 0, 0)
                assert actual == value, (actual, value)
                assert not dialog._transfer_text and not dialog._marquee_enabled
                assert dialog._current_status == 'Güncelleme paketi hazırlanıyor…'
                observed.append(value)
                if value >= 40 and not captured:
                    capture('preparation')
                    captured = True
            result = UpdateInstaller().extract_update(archive, Path(temp)/'staging', measured, status)
            assert result and (result/'OKDEV.exe').is_file()
            return False  # Presentation/extraction only: never install or relaunch.
        with patch('launcher.core.launcher.UpdateSequence', return_value=SimpleNamespace(perform_update=perform)):
            assert _perform_update(dialog) is False
    assert observed[0] == 0 and observed[-1] == 100 and observed == sorted(set(observed))
    assert any(0 < value < 100 for value in observed)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'ok':True, 'values':observed, 'archive_sha256':digest,
              'scope':'Actual local release extraction and Win32 progress; mocked release lookup, no public network, install or game launch.'}
    (root/'output/ui2-20261030/startup-preparation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
