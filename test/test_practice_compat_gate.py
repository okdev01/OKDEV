import unittest
from unittest.mock import patch
from scripts.practice_compat_test import practice_ready


class Client:
    def __init__(self,phase='ChampSelect',queue=3140,skin=141000):
        self.routes={'/lol-gameflow/v1/session':{'phase':phase,'gameData':{'queue':{'id':queue}}},
          '/lol-game-queues/v1/queues':[{'id':3140,'gameMode':'PRACTICETOOL'}],
          '/lol-champ-select/v1/session/my-selection':{'championId':141,'selectedSkinId':skin},
          '/lol-lobby/v2/lobby':{'gameConfig':{'queueId':3140}}}
    def get(self,path):return self.routes.get(path)


class PracticeGateTests(unittest.TestCase):
    def test_only_base_kayn_in_practice_can_arm(self):
        with patch('scripts.practice_compat_test.psutil.process_iter',return_value=[]):
            self.assertTrue(practice_ready(Client())[0])
            self.assertFalse(practice_ready(Client(queue=420))[0])
            self.assertFalse(practice_ready(Client(phase='InProgress'))[0])
            self.assertFalse(practice_ready(Client(skin=141032))[0])

    def test_running_game_blocks_even_when_client_reports_champion_select(self):
        from types import SimpleNamespace
        process=SimpleNamespace(info={'name':'League of Legends.exe'})
        with patch('scripts.practice_compat_test.psutil.process_iter',return_value=[process]):
            self.assertFalse(practice_ready(Client())[0])


if __name__=='__main__':unittest.main()
