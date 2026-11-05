"""OKDEV maintenance: offline diagnosis by default; explicit official repair."""
import argparse
import configparser
import json
import os
from pathlib import Path
import sys
import time
import okdev_ltk_delivery as delivery
from okdev_ltk_policy import HOST_MANAGER_VERSION, SUPPORTED_PROTOCOL
from okdev_ltk_update import ensure_patcher, PatcherUnavailable
from injection.tools.patcher import read_game_build
from utils.core.atomic_file import atomic_write


def diagnose(game, tools):
    game,tools=Path(game),Path(tools)
    report={'schema':1,'checked_at':time.time(),'supported_manager':HOST_MANAGER_VERSION,
            'supported_protocol':SUPPORTED_PROTOCOL,'game_build':read_game_build(game),
            'checks':{},'ready':False,'game_rendering_verified':False}
    checks=report['checks']
    checks['game']='ok' if report['game_build'] is not None else 'missing_or_unreadable'
    checks['tools']='ok' if tools.is_dir() else 'missing'
    host=delivery.manager_dir()/delivery.HOST
    checks['host']='missing'
    if host.is_file():
        report['host_sha256']=delivery._sha(host)
        checks['host']='ok' if report['host_sha256']==delivery.HOST_SHA256 else 'unreviewed_host'
    try:
        state=delivery._read_json(delivery.delivery_root()/'delivery.json')
        manifest=delivery.verify_manifest(state['channels']['stable']['envelope'])
        # Deliberately include only public release metadata, never delivery credentials.
        release=manifest['release']
        report['release']={k:release[k] for k in ('version','digest','size','protocol','managers','eol')}
        checks['manifest']='verified'
        checks['protocol']='ok' if release['protocol']==SUPPORTED_PROTOCOL else 'requires_okdev_update'
        checks['game_compatibility']='ok' if report['game_build'] is not None and report['game_build']<=release['eol'] else 'unsupported_game_build'
        checks['revocation']='revoked' if release['digest'] in manifest['revoked'] else 'not_revoked_in_stable'
    except Exception as error:
        checks['manifest']='unavailable_or_invalid'
        report['manifest_error_type']=type(error).__name__
    from okdev_ltk_compat import resolve_verified
    resolved=resolve_verified(game) or delivery.select_cached(game)
    report['ready']=bool(resolved)
    checks['runtime']='verified_and_staged' if resolved else 'not_ready'
    report['action']='no_repair_needed' if resolved else 'run_repair_outside_game'
    return report


def default_game():
    path=Path(os.environ.get('LOCALAPPDATA',''))/'OKDEV/config.ini'
    settings=configparser.ConfigParser(interpolation=None)
    from config import read_config_file
    read_config_file(settings,path)
    root=settings.get('General','leaguePath',fallback=r'C:\Riot Games\League of Legends\Game')
    return Path(root)/'League of Legends.exe'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('diagnose','repair'),nargs='?',default='diagnose')
    parser.add_argument('--game',type=Path,default=None)
    parser.add_argument('--tools',type=Path,default=Path(os.environ.get('LOCALAPPDATA',''))/'Programs/OKDEV/_internal/injection/tools')
    parser.add_argument('--report',type=Path,default=Path(os.environ.get('LOCALAPPDATA',''))/'OKDEV/logs/maintenance.json')
    args=parser.parse_args(argv)
    game=args.game or default_game()
    failure=None
    if args.command=='repair':
        try:
            ensure_patcher(args.tools,game,status=lambda msg:print(msg,flush=True),force=True)
        except Exception as error:
            failure={'type':type(error).__name__,'message':str(error)}
    report=diagnose(game,args.tools)
    if failure:report['repair_error']=failure
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with atomic_write(args.report) as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return 0 if report['ready'] else 2


if __name__=='__main__':
    raise SystemExit(main())
