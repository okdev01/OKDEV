"""Pure role and champion-selection decisions. No client mutations here."""
from .guides import ROLES


def assigned_lane(session):
    if not isinstance(session, dict) or session.get('benchEnabled') is True:
        return None
    cell = session.get('localPlayerCellId')
    team = session.get('myTeam')
    if type(cell) is not int or cell < 0 or not isinstance(team, list):
        return None
    player = next((p for p in team if isinstance(p, dict) and p.get('cellId') == cell), {})
    role = ROLES.get(str(player.get('assignedPosition', '')).lower())
    return role if role in ('top', 'jungle', 'mid', 'adc', 'support') else None


def priority_for(prefs, session, action):
    lane = assigned_lane(session)
    if lane is None:
        return []
    # Role automation deliberately has no fallback for unknown/empty roles.
    if action == 'pick' or prefs['lane_automation']:
        priority = prefs['lane_profiles'].get(lane, {}).get(action, [])
    else:
        priority = prefs['auto_ban_priority']
    if action == 'ban' and prefs['auto_pick_enabled']:
        planned = prefs['lane_profiles'].get(lane, {}).get('pick', [])
        return [champion for champion in priority if champion not in planned]
    return priority


def pick_candidate(session, priority, available):
    if not assigned_lane(session):
        return None
    cell = session['localPlayerCellId']
    groups = session.get('actions')
    if not isinstance(groups, list):
        return None
    actions = [a for group in groups if isinstance(group, list) for a in group if isinstance(a, dict)]
    own = [a for a in actions if a.get('type') == 'pick' and a.get('actorCellId') == cell
           and a.get('isInProgress') is True and a.get('completed') is False
           and a.get('championId') in (0, -1) and type(a.get('id')) is int]
    if len(own) != 1:
        return None
    protected = set()
    for team in ('myTeam', 'theirTeam'):
        players = session.get(team) or []
        if not isinstance(players, list):
            return None
        for player in players:
            if not isinstance(player, dict):
                return None
            protected.add(player.get('championId', 0))
            if team == 'myTeam' and player.get('cellId') != cell:
                protected.add(player.get('championPickIntent', 0))
    protected.update(a.get('championId', 0) for a in actions if a.get('type') == 'ban' or a.get('completed') is True)
    for ids in (session.get('bans') or {}).values():
        if isinstance(ids, list):
            protected.update(ids)
    target = next((c for c in priority if c in available and c not in protected), None)
    return (own[0]['id'], target) if target is not None else None
