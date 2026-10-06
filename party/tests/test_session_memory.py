import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from party.core import party_storage
from party.core.party_manager import PartyManager, RELAY_URL
from party.protocol.token_codec import create_token
from party.tests.test_party import make_state


class SessionMemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = patch.object(party_storage, 'get_user_data_dir', return_value=Path(self.temp.name))
        self.storage.start()
        self.addCleanup(self.storage.stop)

    def test_sessions_are_scoped_to_account_and_server(self):
        party_storage.save_party_session(1, RELAY_URL, {'enabled': True})
        self.assertTrue(party_storage.load_party_session(1, RELAY_URL + '/')['enabled'])
        self.assertEqual(party_storage.load_party_session(2, RELAY_URL), {})
        self.assertEqual(party_storage.load_party_session(1, 'wss://other'), {})

    async def test_restart_restores_enabled_preference(self):
        first = PartyManager(None, make_state())
        first._session_account = 1
        first._remember(enabled=True)
        restarted = PartyManager(None, make_state())
        restarted._enable = AsyncMock()
        with patch('party.core.party_manager.LobbyMatcher') as matcher:
            matcher.return_value.get_my_summoner_id.return_value = 1
            await restarted.restore_session()
        restarted._enable.assert_awaited_once()

    async def test_explicit_disable_persists_and_prevents_restore(self):
        manager = PartyManager(None, make_state())
        manager._session_account = 1
        manager._remember(enabled=True)
        await manager.disable()
        restarted = PartyManager(None, make_state())
        restarted._enable = AsyncMock()
        with patch('party.core.party_manager.LobbyMatcher') as matcher:
            matcher.return_value.get_my_summoner_id.return_value = 1
            await restarted.restore_session()
        restarted._enable.assert_not_awaited()

    async def test_temporary_failure_does_not_forget_intent(self):
        party_storage.save_party_session(1, RELAY_URL, {'enabled': True})
        manager = PartyManager(None, make_state())
        manager._enable = AsyncMock(side_effect=RuntimeError('offline'))
        with patch('party.core.party_manager.LobbyMatcher') as matcher:
            matcher.return_value.get_my_summoner_id.return_value = 1
            await manager.restore_session()
        self.assertTrue(party_storage.load_party_session(1, RELAY_URL)['enabled'])

    async def test_saved_room_rejoined_and_remove_is_remembered(self):
        manager = PartyManager(None, make_state())
        manager._session_account = 1
        manager._running = True
        token = create_token(summoner_id=2, encryption_key=b'x' * 32).encode()
        manager._saved_peers = {2: {'token': token, 'name': 'Friend'}}
        manager._join_room = AsyncMock(return_value=None)
        await manager._restore_saved_rooms()
        manager._join_room.assert_awaited_once()
        self.assertFalse(manager.party_state.peers[2].connected)
        await manager.remove_peer(2)
        saved = party_storage.load_party_session(1, RELAY_URL)
        self.assertEqual(saved['peers'], {})
        self.assertEqual(saved['ignored'], [2])

    def test_own_selection_is_in_ui_payload_only_when_enabled(self):
        manager = PartyManager(None, make_state())
        manager._skin_state = {'champion_id': 18, 'skin_id': 18080}
        manager.party_state.enabled = True
        self.assertEqual(manager.get_state_dict()['my_skin_selection']['skin_id'], 18080)
        manager.party_state.enabled = False
        self.assertIsNone(manager.get_state_dict()['my_skin_selection'])
