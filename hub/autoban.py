"""Opt-in champion bans. All decisions use fresh client state."""
from . import preferences
from .draft import priority_for


class AutoBan:
    def __init__(self):
        self.game = None
        self.attempted = set()
        self.match_attempted = False
        self.status = 'idle'

    @staticmethod
    def read(lcu, path):
        response = lcu.s.get(lcu.base + path, timeout=3)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def active_ban(session, action, group):
        if action.get('isInProgress') is True:
            return True
        # Simultaneous bans belong to one active action group. Some client
        # snapshots flag only a member of that group, rather than every row.
        if session.get('hasSimultaneousBans') is not True or session.get('isSpectating') is True:
            return False
        timer = session.get('timer') or {}
        if not isinstance(timer, dict) or timer.get('phase') != 'BAN_PICK':
            return False
        if not group or not all(isinstance(a, dict) and a.get('type') == 'ban' for a in group):
            return False
        return any(a.get('isInProgress') is True and a.get('completed') is False for a in group)

    @staticmethod
    def candidate(session, priority, available):
        if not isinstance(session, dict):
            return None
        cell = session.get('localPlayerCellId')
        if type(cell) is not int or cell < 0:
            return None
        groups = session.get('actions')
        if not isinstance(groups, list):
            return None
        actions = [a for group in groups if isinstance(group, list) for a in group if isinstance(a, dict)]
        own = [a for group in groups if isinstance(group, list) for a in group if isinstance(a, dict)
               and a.get('type') == 'ban' and a.get('actorCellId') == cell
               and AutoBan.active_ban(session, a, group) and a.get('completed') is False
               and a.get('championId') in (0, -1) and type(a.get('id')) is int]
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

    @staticmethod
    def waiting_reason(session, priority, available):
        """Record decision inputs without names, accounts or connection secrets."""
        cell = session.get('localPlayerCellId')
        actions = [a for group in session.get('actions', []) if isinstance(group, list)
                   for a in group if isinstance(a, dict) and a.get('type') == 'ban'
                   and a.get('actorCellId') == cell]
        fields = ','.join('id={};active={};done={};champion={}'.format(
            a.get('id'), a.get('isInProgress'), a.get('completed'), a.get('championId')) for a in actions)
        return 'waiting-for-eligible-ban cell={} own=[{}] available-priority={}'.format(
            cell, fields, [champion for champion in priority if champion in available])

    def tick(self, lcu, phase):
        if phase != 'ChampSelect':
            self.status = 'waiting-for-champion-select'
            if phase:  # A transient disconnect must not permit a duplicate request.
                self.game = None
                self.attempted.clear()
                self.match_attempted = False
            return False
        prefs = preferences.get()
        if not prefs['auto_ban_enabled']:
            self.status = 'disabled-or-empty-priority'
            return False
        session = self.read(lcu, '/lol-champ-select/v1/session')
        priority = priority_for(prefs, session, 'ban')
        if not priority:
            self.status = 'unknown-role-or-empty-list'
            return False
        game = session.get('gameId')
        if game != self.game:
            self.game = game
            self.attempted.clear()
            self.match_attempted = False
        if self.match_attempted:
            self.status = 'already-attempted'
            return False
        available = self.read(lcu, '/lol-champ-select/v1/bannable-champion-ids')
        if not isinstance(available, list) or any(type(c) is not int for c in available):
            self.status = 'invalid-bannable-champions'
            return False
        first = self.candidate(session, priority, set(available))
        if first is None or first[0] in self.attempted:
            self.status = 'already-attempted' if first else self.waiting_reason(session, priority, set(available))
            return False
        # Respect late teammate hovers, manual selection and preference changes.
        session = self.read(lcu, '/lol-champ-select/v1/session')
        prefs = preferences.get()
        if not prefs['auto_ban_enabled'] or session.get('gameId') != game:
            self.status = 'preferences-or-session-changed'
            return False
        choice = self.candidate(session, priority_for(prefs, session, 'ban'), set(available))
        if choice is None or choice[0] != first[0]:
            self.status = 'selection-changed'
            return False
        self.attempted.add(choice[0])  # Timeouts have an unknown result: never repeat.
        self.match_attempted = True  # Pick-order swaps can assign a different action ID.
        self.status = 'request-outcome-unknown'
        response = lcu.s.patch(lcu.base + '/lol-champ-select/v1/session/actions/' + str(choice[0]),
                               json={'championId': choice[1], 'completed': True}, timeout=3)
        self.status = 'ban-completed' if response.ok else 'request-rejected-' + str(response.status_code)
        return response.ok
