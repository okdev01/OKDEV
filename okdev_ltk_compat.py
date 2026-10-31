"""Pinned, unmodified official compatibility pair for a visually tested build.

The original binary's game-build cutoff and all verification remain enabled.
This is a version-specific compatibility path, not an independent runtime.
"""
import json
from pathlib import Path
import tempfile
from nacl.exceptions import BadSignatureError
from injection.tools.patcher import read_game_build,read_dll_eol
from utils.core.atomic_file import atomic_write

VERSION='1.29.1'
GAME_SHA256='a00077e3e50345076e2e1a7d31b8d58dd76119d87e5b6ecbd6124dd04ab8989c'
# Release QA: base Kayn -> HEARTSTEEL, then installed OKDEV's normal selection
# -> Spring Petals Katarina; both visually confirmed on 2026-10-31.
# Keep this separate from GAME_SHA256 so changing a candidate never inherits QA.
RELEASE_TESTED_GAME_SHA256='a00077e3e50345076e2e1a7d31b8d58dd76119d87e5b6ecbd6124dd04ab8989c'
FILES={
    'ltk_patcher_host.exe':'23fa1aaeda1a0c743da44227f179084e1fb81c7cd262144a3c8604ffc49d3bc1',
    'ltk_patcher_dll.dll':'3dce3ac99e55839559129e32ae9de75ddaec40f310118475248f99c61656ecf5',
}
ASSET={'name':'LTK.Manager_1.29.1_x64-setup.exe',
       'browser_download_url':'https://github.com/LeagueToolkit/ltk-manager/releases/download/v1.29.1/LTK.Manager_1.29.1_x64-setup.exe',
       'size':22667880,'digest':'sha256:8c8119b0eb8df61fe0697de047f21d55bfe2c4ccf97684945b11b8c9ebd0bd30'}


def _root():
    from okdev_ltk_delivery import runtime_root
    return runtime_root()


def _digest(path):
    from okdev_ltk_update import digest
    return digest(path)


def game_matches(game):
    try:
        return game is not None and _digest(Path(game))==GAME_SHA256
    except OSError:
        return False


def candidate(game):
    """Read-only candidate validation; does not assert game rendering works."""
    try:
        if not game_matches(game):
            return None
        root=_root();target=root/'compat-candidate-1.29.1'
        if any(p.is_symlink() or p.is_junction() for p in (root,target,*[target/n for n in FILES])):
            return None
        if not all((target/n).is_file() and _digest(target/n)==sha for n,sha in FILES.items()):
            return None
        eol,build=read_dll_eol(target/'ltk_patcher_dll.dll'),read_game_build(Path(game))
        if eol is None or build is None or build>eol:
            return None
        from okdev_ltk_delivery import delivery_root,_read_json,verify_manifest
        state=delivery_root()/'delivery.json'
        if state.is_file():
            for channel in _read_json(state).get('channels',{}).values():
                if FILES['ltk_patcher_dll.dll'] in verify_manifest(channel['envelope'])['revoked']:
                    return None
        return target
    except (OSError,ValueError,KeyError,TypeError,AttributeError,BadSignatureError):
        return None


def resolve_verified(game):
    """Only an exact, visually tested build may select this pair automatically."""
    if release_qualified(game):
        return candidate(game)
    try:
        marker=_root()/'compat-visual-qa.json'
        if marker.is_symlink() or marker.stat().st_size>8192:
            return None
        data=json.loads(marker.read_bytes())
        if (not isinstance(data,dict) or type(data.get('schema')) is not int or data.get('schema')!=1 or data.get('visual_verified') is not True
                or data.get('game_sha256')!=GAME_SHA256 or data.get('runtime')!=VERSION):
            return None
        return candidate(game)
    except (OSError,ValueError,TypeError):
        return None


def release_qualified(game):
    """Release-level QA is portable; never write a fake local visual-test marker."""
    return GAME_SHA256 == RELEASE_TESTED_GAME_SHA256 and game_matches(game)


def record_visual_qa(game):
    """Explicit operator action after observing the chosen skin in practice."""
    if candidate(game) is None:
        raise ValueError('Compatibility candidate is not valid for this game')
    with atomic_write(_root()/'compat-visual-qa.json') as output:
        json.dump({'schema':1,'visual_verified':True,'game_sha256':GAME_SHA256,'runtime':VERSION},output)


def prepare_candidate(game,status=lambda message:None):
    if not game_matches(game):
        raise ValueError('This compatibility candidate has not been evaluated for this game build')
    if candidate(game):
        return candidate(game)
    from okdev_ltk_update import require_idle,download_official,extract_pair
    require_idle()
    root=_root();root.mkdir(parents=True,exist_ok=True)
    target=root/'compat-candidate-1.29.1'
    if root.is_symlink() or root.is_junction() or target.is_symlink() or target.is_junction():
        raise ValueError('Compatibility directory cannot be a link')
    with tempfile.TemporaryDirectory(prefix='okdev-compatible-') as temporary:
        temporary=Path(temporary)
        download_official(temporary/'manager.exe',status,ASSET)
        extract_pair(temporary/'manager.exe',temporary/'pair')
        if not all(_digest(temporary/'pair'/name)==sha for name,sha in FILES.items()):
            raise ValueError('Official compatibility pair does not match pinned files')
        target.mkdir(exist_ok=True)
        for name in FILES:
            with atomic_write(target/name,'wb') as output:
                output.write((temporary/'pair'/name).read_bytes())
    if candidate(game) is None:
        raise ValueError('Compatibility candidate failed validation')
    return target
