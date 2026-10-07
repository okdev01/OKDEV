"""Preparing a missing carrier must not hold the next game for 60 seconds."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from threads.handlers.injection_trigger import InjectionTrigger


class CustomInjectionCleanupTests(unittest.TestCase):
    def trigger(self):
        manager = Mock()
        manager._monitor_active = False
        state = SimpleNamespace(locked_champ_id=141, hovered_champ_id=141)
        return InjectionTrigger(Mock(), state, manager), manager

    def test_missing_chroma_stops_monitor_and_releases_game(self):
        trigger, manager = self.trigger()
        manager.injector._resolve_zip.return_value = None
        trigger._inject_custom_mod({'skin_id': 141034}, 'chroma_141034', 'Kayn')
        manager._start_monitor.assert_called_once()
        manager.resume_game.assert_called_once()
        manager._stop_monitor.assert_called_once()
        manager.injector.overlay_manager.mk_run_overlay.assert_not_called()

    def test_extraction_failure_releases_game(self):
        trigger, manager = self.trigger()
        manager.injector._resolve_zip.return_value.exists.return_value = True
        manager.injector._extract_zip_to_mod.side_effect = OSError('bad archive')
        trigger._inject_custom_mod({'skin_id': 141032}, 'skin_141032', 'Kayn')
        manager.resume_game.assert_called_once()
        manager._stop_monitor.assert_called_once()
        manager.injector.overlay_manager.mk_run_overlay.assert_not_called()

    def test_missing_injector_still_cleans_up_prestarted_monitor(self):
        trigger, manager = self.trigger()
        manager.injector = None
        trigger._inject_custom_mod({}, 'skin_141032', 'Kayn')
        manager.resume_game.assert_called_once()
        manager._stop_monitor.assert_called_once()


if __name__ == '__main__':
    unittest.main()
