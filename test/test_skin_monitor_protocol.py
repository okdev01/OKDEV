import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pengu.communication.message_handler import MessageHandler
from pengu.processing.skin_processor import SkinProcessor


def fixture():
    state=SimpleNamespace(is_swiftplay_mode=False,selected_chroma_id=None,last_hovered_skin_id=None,
                          ui_skin_id=None,ui_last_text=None,last_hovered_skin_key=None)
    processor=SkinProcessor(state,skin_scraper=Mock())
    processor._find_skin_id=lambda name: (516001,name)
    handler=MessageHandler.__new__(MessageHandler)
    handler.shared_state=state;handler.skin_processor=processor;handler.broadcaster=Mock()
    handler.flow_controller=Mock();handler.flow_controller.should_process_payload.return_value=True
    return handler,state


class SkinWireProtocolTests(unittest.TestCase):
    def test_normal_client_choice_reaches_independent_engine_request(self):
        handler,state=fixture()
        state.phase='ChampSelect'
        state.locked_champ_id=516
        state.champ_select_generation=7
        handler.handle_message(json.dumps({'type':'skin-hover','skin':'Fırtınanın Efendisi Ornn'}))
        self.assertEqual(state.independent_selection.skin_id,516001)
        self.assertEqual(state.independent_selection.champion_id,516)
        self.assertEqual(state.independent_selection.session_id,'champselect:7')

    def test_regular_hover_reaches_selection_state(self):
        handler,state=fixture()
        handler.handle_message(json.dumps({'type':'skin-hover','skin':'Fırtınanın Efendisi Ornn'}))
        self.assertEqual(state.last_hovered_skin_id,516001)
        handler.broadcaster.broadcast_skin_state.assert_called_once_with('Fırtınanın Efendisi Ornn',516001)

    def test_legacy_plugin_hover_is_supported_during_upgrade(self):
        handler,state=fixture()
        handler.handle_message(json.dumps({'skin':'Fırtınanın Efendisi Ornn','timestamp':1793404158}))
        self.assertEqual(state.last_hovered_skin_id,516001)

    def test_reconnect_and_before_lock_retains_label(self):
        handler,state=fixture();handler.flow_controller.should_process_payload.return_value=False
        handler.handle_message(json.dumps({'type':'skin-sync','skin':'Fırtınanın Efendisi Ornn'}))
        self.assertEqual(state.ui_last_text,'Fırtınanın Efendisi Ornn')
        self.assertIsNone(state.last_hovered_skin_id)
        handler.flow_controller.should_process_payload.return_value=True
        handler.handle_message(json.dumps({'type':'skin-sync','skin':'Fırtınanın Efendisi Ornn'}))
        self.assertEqual(state.last_hovered_skin_id,516001)

    def test_malformed_and_unknown_messages_do_not_select_skins(self):
        for payload in [[],None,{}, {'type':9,'skin':'Ornn'},{'type':None,'skin':'Ornn'},
                        {'skin':17},{'skin':' '},{'skin':'x'*513},{'type':'unknown','skin':'Ornn'},
                        {'type':'skin-hover','skin':[]},{'type':'skin-sync','skin':'x'*513}]:
            with self.subTest(payload=str(payload)[:60]):
                handler,state=fixture();handler.handle_message(json.dumps(payload))
                self.assertIsNone(state.last_hovered_skin_id)

    def test_invalid_windows_command_output_cannot_crash_reader_thread(self):
        from utils.system.admin_utils import is_registered_for_autostart
        import subprocess,sys
        actual_run=subprocess.run
        def simulated_task_query(*args,**kwargs):
            kwargs['encoding']='cp1254'
            return actual_run([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'\\x8d');sys.exit(1)"],**kwargs)
        with patch('utils.system.admin_utils.subprocess.run',side_effect=simulated_task_query):
            self.assertFalse(is_registered_for_autostart())
