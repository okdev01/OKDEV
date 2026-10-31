"""Capture the existing champion-select choice for the independent engine.

This bridge does not change catalogue visibility, send LCU writes, start native
processes, or claim that an offline build has been applied in game.
"""
from pathlib import Path
from .selection import Selection
from .manifest import write_manifest


def capture_selection(state):
    state.independent_selection = None
    if getattr(state,'phase',None) not in ('ChampSelect','FINALIZATION'):
        return None
    if getattr(state,'is_swiftplay_mode',False):
        return None  # Multi-slot loadouts need a separate selection model.
    champion = getattr(state,'locked_champ_id',None)
    generation = getattr(state,'champ_select_generation',None)
    if type(generation) is not int or generation < 0:
        return None
    if getattr(state,'ui_last_text_generation',None) != generation:
        return None
    if getattr(state,'ui_last_text_champion_id',None) != champion:
        return None
    try:
        selection = Selection(f'champselect:{generation}',champion,getattr(state,'ui_skin_id',None))
    except ValueError:
        return None
    state.independent_selection = selection
    return selection


def prepare_current(state, library: Path, game: Path, output_root: Path):
    """Developer-only offline preparation; discard stale choices as results."""
    from .prepare import prepare
    selection = capture_selection(state)
    if selection is None:
        raise ValueError('No current champion-select skin selection')
    directory, manifest = prepare(selection,library,game,output_root)
    if capture_selection(state) != selection:
        manifest['state'] = 'superseded'
        write_manifest(directory,manifest)
        raise ValueError('Selection changed while building; result was not applied')
    return directory, manifest
