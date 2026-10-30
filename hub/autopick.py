"""Opt-in role-based picks; one request per action, never a live test."""
from . import preferences
from .autoban import AutoBan
from .draft import assigned_lane, pick_candidate, priority_for


class AutoPick(AutoBan):
    def tick(self, lcu, phase):
        if phase != 'ChampSelect':
            self.status = 'waiting-for-champion-select'
            if phase:
                self.game = None
                self.attempted.clear()
            return False
        prefs = preferences.get()
        if not prefs['auto_pick_enabled']:
            self.status = 'disabled'
            return False
        session = self.read(lcu, '/lol-champ-select/v1/session')
        if not isinstance(session, dict):
            self.status = 'invalid-session'
            return False
        lane = assigned_lane(session)
        priority = priority_for(prefs, session, 'pick')
        if not priority:
            self.status = 'unknown-role-or-empty-list'
            return False
        game = session.get('gameId')
        if game != self.game:
            self.game = game
            self.attempted.clear()
        available = self.read(lcu, '/lol-champ-select/v1/pickable-champion-ids')
        if not isinstance(available, list) or any(type(c) is not int for c in available):
            self.status = 'invalid-pickable-champions'
            return False
        first = pick_candidate(session, priority, set(available))
        if first is None or first[0] in self.attempted:
            self.status = 'waiting-for-eligible-pick'
            return False
        # Availability can change during another player's simultaneous selection.
        available = self.read(lcu, '/lol-champ-select/v1/pickable-champion-ids')
        if not isinstance(available, list) or any(type(c) is not int for c in available):
            return False
        session = self.read(lcu, '/lol-champ-select/v1/session')
        prefs = preferences.get()
        if not prefs['auto_pick_enabled'] or not isinstance(session, dict) or session.get('gameId') != game or assigned_lane(session) != lane:
            self.status = 'preferences-or-role-changed'
            return False
        choice = pick_candidate(session, priority_for(prefs, session, 'pick'), set(available))
        if choice is None or choice[0] != first[0]:
            self.status = 'selection-changed'
            return False
        self.attempted.add(choice[0])
        self.status = 'request-outcome-unknown'
        response = lcu.s.patch(lcu.base + '/lol-champ-select/v1/session/actions/' + str(choice[0]),
                               json={'championId': choice[1], 'completed': True}, timeout=3)
        self.status = 'pick-completed' if response.ok else 'request-rejected-' + str(response.status_code)
        return response.ok
