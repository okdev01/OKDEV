"""Controlled 1.29.1 compatibility test: never arm during a ranked/live game."""
import argparse
import json
from pathlib import Path
import sys
import time
import psutil
import urllib3

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lcu.core.client import LCU
from okdev_ltk_compat import candidate
from injection.overlay.overlay_manager import OverlayManager


def practice_ready(lcu):
    flow=lcu.get('/lol-gameflow/v1/session') or {}
    if flow.get('phase')!='ChampSelect':
        return False,'not_in_practice_champion_select',None
    data=flow.get('gameData') or {}
    queue=data.get('queue') or {}
    queue_id=queue.get('id')
    queues=lcu.get('/lol-game-queues/v1/queues') or []
    practice_ids={q['id'] for q in queues if isinstance(q,dict) and q.get('gameMode')=='PRACTICETOOL'}
    mode=queue.get('gameMode') or data.get('gameMode')
    if queue_id not in practice_ids and mode!='PRACTICETOOL':
        lobby=lcu.get('/lol-lobby/v2/lobby') or {}
        config=lobby.get('gameConfig') or {}
        custom=(config.get('customGameLobby') or {}).get('configuration') or {}
        if queue_id!=0 or config.get('queueId')!=0 or custom.get('gameMode')!='PRACTICETOOL':
            return False,'queue_is_not_practice_tool',queue_id
    selection=lcu.get('/lol-champ-select/v1/session/my-selection') or {}
    if selection.get('championId')!=141 or selection.get('selectedSkinId')!=141000:
        return False,'requires_base_kayn_141000',queue_id
    if any((p.info['name'] or '').casefold() in ('league of legends.exe','league of legends (tm) client.exe')
           for p in psutil.process_iter(['name'])):
        return False,'game_already_running',queue_id
    return True,'ready',queue_id


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-exe',required=True,type=Path)
    parser.add_argument('--overlay',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--wait-seconds',type=int,default=0)
    args=parser.parse_args()
    if not 0<=args.wait_seconds<=1200:
        parser.error('Wait must be between 0 and 1200 seconds')
    runtime=candidate(args.game_exe)
    if runtime is None:
        raise ValueError('Official candidate failed hash/build/revocation checks')
    if not (args.overlay/'DATA/FINAL/Champions/Kayn.wad.client').is_file():
        raise ValueError('Prepared Kayn overlay is missing')
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    lcu=LCU();deadline=time.monotonic()+args.wait_seconds
    report={'runtime':'1.29.1','status':'waiting','game_tested':False,'visual_verified':False}
    previous=None
    while True:
        ready,reason,queue_id=practice_ready(lcu)
        if reason!=previous:
            print(reason,flush=True);previous=reason
        report['waiting_reason']=reason
        args.report.write_text(json.dumps(report,indent=2))
        if ready:break
        if time.monotonic()>=deadline:
            return 2
        time.sleep(.5)
    manager=OverlayManager(runtime,args.overlay.parent/'mods',args.game_exe.parent)
    logfile=args.report.with_suffix('.log')
    manager._open_runoverlay_log=lambda:logfile.open('w',encoding='utf-8',buffering=1)
    session=manager._start_ltk_patcher(runtime/'ltk_patcher_host.exe',args.overlay)
    if session is None:
        raise RuntimeError('Candidate host failed to start')
    started=time.monotonic()
    report.update(status='armed_practice_only',queue_id=queue_id)
    try:
        while time.monotonic()-started<600:
            flow=lcu.get('/lol-gameflow/v1/session') or {}
            phase=flow.get('phase')
            active_id=((flow.get('gameData') or {}).get('queue') or {}).get('id')
            if active_id!=queue_id or phase in ('Lobby','Matchmaking','ReadyCheck','EndOfGame'):
                report['status']='session_ended_or_changed';break
            if phase=='ChampSelect':
                selected=lcu.get('/lol-champ-select/v1/session/my-selection') or {}
                if selected.get('championId')!=141 or selected.get('selectedSkinId')!=141000:
                    report['status']='selection_changed';break
            if session['session']['error']:
                report.update(status='failed',error=session['session']['error']);break
            if session['proc'].poll() is not None:
                report.update(status='host_exited',exit_code=session['proc'].returncode);break
            if session['session']['state'] in ('injected','waiting'):
                report.update(status='awaiting_visual_confirmation',game_tested=True)
            args.report.write_text(json.dumps(report,indent=2))
            time.sleep(.25)
    finally:
        manager._abort_ltk_patcher(session)
        args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
    return 1 if report.get('error') else 0


if __name__=='__main__':
    raise SystemExit(main())
