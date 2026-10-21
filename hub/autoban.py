"""Opt-in champion bans. All decisions use fresh client state."""
from . import preferences


class AutoBan:
    def __init__(self):
        self.game = None
        self.attempted = set()

    @staticmethod
    def read(lcu, path):
        response = lcu.s.get(lcu.base + path, timeout=3)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def candidate(session, priority, available):
        if not isinstance(session, dict):
            return None
        cell = session.get('localPlayerCellId')
        if type(cell) is not int or cell < 0:
            return None
        actions = [a for group in session.get('actions', []) for a in group if isinstance(a, dict)]
        own = [a for a in actions if a.get('type') == 'ban' and a.get('actorCellId') == cell
               and a.get('isInProgress') is True and a.get('completed') is False
               and a.get('championId') == 0 and type(a.get('id')) is int]
        if len(own) != 1:
            return None
        protected = set()
        for team in ('myTeam', 'theirTeam'):
            for player in session.get(team, []):
                protected.add(player.get('championId', 0))
                if team == 'myTeam':
                    protected.add(player.get('championPickIntent', 0))
        for values in session.get('bans', {}).values():
            if isinstance(values, list):
                protected.update(values)
        protected.update(a.get('championId', 0) for a in actions if a.get('type') == 'ban')
        target = next((c for c in priority if c in available and c not in protected), None)
        return (own[0]['id'], target) if target is not None else None

    def tick(self, lcu, phase):
        if phase != 'ChampSelect':
            if phase:  # A transient disconnect must not permit a duplicate request.
                self.game = None
                self.attempted.clear()
            return False
        prefs = preferences.get()
        if not prefs['auto_ban_enabled'] or not prefs['auto_ban_priority']:
            return False
        session = self.read(lcu, '/lol-champ-select/v1/session')
        game = session.get('gameId')
        if game != self.game:
            self.game = game
            self.attempted.clear()
        available = self.read(lcu, '/lol-champ-select/v1/bannable-champion-ids')
        if not isinstance(available, list) or any(type(c) is not int for c in available):
            return False
        first = self.candidate(session, prefs['auto_ban_priority'], set(available))
        if first is None or first[0] in self.attempted:
            return False
        # Respect late teammate hovers, manual selection and preference changes.
        session = self.read(lcu, '/lol-champ-select/v1/session')
        prefs = preferences.get()
        if not prefs['auto_ban_enabled'] or session.get('gameId') != game:
            return False
        choice = self.candidate(session, prefs['auto_ban_priority'], set(available))
        if choice is None or choice[0] != first[0]:
            return False
        self.attempted.add(choice[0])  # Timeouts have an unknown result: never repeat.
        response = lcu.s.patch(lcu.base + '/lol-champ-select/v1/session/actions/' + str(choice[0]),
                               json={'championId': choice[1], 'completed': True}, timeout=3)
        return response.ok
