"""Champion-lock guide state. This module does not create windows or call LCU."""
import json
import re
import sys
import time
from functools import lru_cache
from pathlib import Path

from . import library, preferences

ROLES = {'top': 'top', 'jungle': 'jungle', 'middle': 'mid', 'mid': 'mid',
         'bottom': 'adc', 'adc': 'adc', 'utility': 'support', 'support': 'support', 'aram': 'aram'}
ROLE_LABELS = {'top': 'Üst koridor', 'jungle': 'Orman', 'mid': 'Orta koridor', 'adc': 'Alt koridor', 'support': 'Destek', 'aram': 'ARAM'}
GAME_PHASES = frozenset({'GameStart', 'InProgress', 'Reconnect'})
END_PHASES = frozenset({'WaitingForStats', 'PreEndOfGame', 'EndOfGame'})
SLUG_OVERRIDES = {62: 'monkeyking', 20: 'nunu', 888: 'renata'}


@lru_cache(maxsize=1)
def champions():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    data = json.loads((base / 'hub/web/champions.json').read_text(encoding='utf-8'))
    return {item['id']: dict(item, slug=SLUG_OVERRIDES.get(item['id'], re.sub('[^a-z0-9]', '', item['name'].lower())))
            for item in data['champions']}


def build_url(champion_id, role=''):
    if type(champion_id) is not int or champion_id not in champions():
        raise ValueError('Önce bir şampiyon seç.')
    role = ROLES.get(str(role).lower(), '')
    if role == 'aram':
        return 'https://mobalytics.gg/lol/champions/' + champions()[champion_id]['slug'] + '/aram-builds'
    return 'https://mobalytics.gg/lol/champions/' + champions()[champion_id]['slug'] + '/build' + ('/' + role if role else '')


def locked_pick(session):
    """Only a completed own pick (or an assigned ARAM champion) is a lock."""
    if not isinstance(session, dict):
        return None
    cell = session.get('localPlayerCellId')
    if type(cell) is not int or cell < 0:
        return None
    players = session.get('myTeam') or []
    if not isinstance(players, list):
        return None
    player = next((p for p in players if isinstance(p, dict) and p.get('cellId') == cell), None)
    if player is None:
        return None
    raw_actions = session.get('actions') or []
    if not isinstance(raw_actions, list):
        return None
    actions = [a for group in raw_actions if isinstance(group, list)
               for a in group if isinstance(a, dict) and a.get('actorCellId') == cell and a.get('type') == 'pick']
    completed = [a for a in actions if a.get('completed') is True]
    # Hovered champions must never open a build. ARAM can assign a champion
    # with no draft actions; benchEnabled is the explicit assignment signal.
    if not completed and not (not actions and session.get('benchEnabled') is True):
        return None
    champion_id = player.get('championId')
    if type(champion_id) is not int or champion_id <= 0:
        champion_id = completed[-1].get('championId') if completed else None
    if type(champion_id) is not int or champion_id not in champions():
        return None
    role = 'aram' if session.get('benchEnabled') is True else ROLES.get(str(player.get('assignedPosition', '')).lower(), '')
    return {'champion': champions()[champion_id], 'role': role, 'role_label': ROLE_LABELS.get(role, 'Otomatik rol'),
            'url': build_url(champion_id, role)}


def read_state(now=None):
    now = time.time() if now is None else now
    data = library.read_json(library.root() / 'guide.json', {})
    timestamp = data.get('updated_at')
    fresh = type(timestamp) in (int, float) and 0 <= now - timestamp < 20
    if not fresh:
        return {'connected': False, 'phase': None, 'pick': None, 'status': 'İstemci bekleniyor'}
    pick = data.get('pick')
    if pick:
        try:
            champion_id = pick['champion']['id']
            role = ROLES.get(pick.get('role', ''), '')
            pick = {'champion': champions()[champion_id], 'role': role,
                    'role_label': ROLE_LABELS.get(role, 'Otomatik rol'), 'url': build_url(champion_id, role)}
        except (KeyError, TypeError, ValueError):
            pick = None
    return {'connected': data.get('connected') is True, 'phase': data.get('phase'), 'pick': pick,
            'status': data.get('status', 'İstemci bekleniyor'), 'updated_at': timestamp}


class GuideTracker:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.phase = None
        self.pick = None
        self.shown_key = None
        self.last_write = 0
        self.signature = None
        self.missing_sessions = 0

    def update(self, phase, session=None, connected=True, prefs=None):
        prefs = preferences.get() if prefs is None else prefs
        now = self.clock()
        actions = []
        if not connected or phase not in {'ChampSelect', *GAME_PHASES, *END_PHASES}:
            if self.pick:
                actions.append('hide')
            self.pick = None
            self.shown_key = None
        elif phase == 'ChampSelect':
            if self.phase != 'ChampSelect':
                self.pick = None
                self.shown_key = None
            if isinstance(session, dict):
                self.missing_sessions = 0
                pick = locked_pick(session)
                if self.pick and not pick:
                    actions.append('hide')
                    self.shown_key = None
                self.pick = pick
            else:
                self.missing_sessions += 1
                if self.missing_sessions >= 3:
                    self.pick = None
                    self.shown_key = None
                    actions.append('hide')
            if self.pick and prefs['mobalytics_enabled']:
                key = (self.pick['champion']['id'], self.pick['role'])
                if key != self.shown_key:
                    self.shown_key = key
                    actions.append('show' if prefs['mobalytics_auto_show'] else 'prepare')
        elif phase in GAME_PHASES and self.phase not in GAME_PHASES:
            actions.append('hide')
        elif phase in END_PHASES and self.phase not in END_PHASES:
            actions.append('hide')
        if not prefs['mobalytics_enabled']:
            self.shown_key = None
            actions = ['disable']
        self.phase = phase
        status = ('İstemci bekleniyor' if not connected else 'Şampiyonunu kilitle' if phase == 'ChampSelect' and not self.pick
                  else 'Oyun devam ediyor' if phase in GAME_PHASES else 'Rehber hazır' if self.pick else 'Bir sonraki oyununa hazır')
        data = {'connected': bool(connected), 'phase': phase, 'pick': self.pick, 'status': status, 'updated_at': now}
        signature = json.dumps({k: v for k, v in data.items() if k != 'updated_at'}, sort_keys=True)
        if signature != self.signature or now - self.last_write >= 5:
            library.write_json(library.root() / 'guide.json', data)
            self.signature, self.last_write = signature, now
        return data, actions
