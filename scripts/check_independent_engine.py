"""Validate one real package per champion without altering the installation."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.prepare import prepare
from engine.selection import Selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--game', required=True, type=Path)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    supported = json.loads(args.audit.read_text(encoding='utf-8'))['results']
    choices = {}
    library = args.library.resolve()
    for item in supported:
        if not item['supported']:
            continue
        path = Path(item['path'])
        relative = path.relative_to(library)
        champion = int(relative.parts[0])
        skin = int(path.stem)
        if skin == champion*1000:
            continue
        # Exercise the largest supported carrier rather than only tiny cases.
        size = path.stat().st_size
        if champion not in choices or size > choices[champion][0]:
            choices[champion] = (size, skin)
    started = time.monotonic()
    results = []
    for champion, (_, skin) in sorted(choices.items()):
        case_start = time.monotonic()
        try:
            # Only files created by this validation are removed on scope exit.
            with tempfile.TemporaryDirectory(prefix='engine-check-', dir=ROOT/'output') as temporary:
                _, manifest = prepare(Selection('validation',champion,skin),library,args.game,Path(temporary))
                result = {'champion':champion,'skin':skin,'ok':True,
                          'verified_payloads':sum(a['verified_payloads'] for a in manifest['archives']),
                          'output_bytes':sum(a['bytes'] for a in manifest['archives'])}
        except (OSError, ValueError) as error:
            result = {'champion':champion,'skin':skin,'ok':False,'error':str(error)}
        result['elapsed_seconds'] = round(time.monotonic()-case_start,3)
        results.append(result)
        print(json.dumps(result),flush=True)
    report = {'champions':len(results),'passed':sum(r['ok'] for r in results),
              'elapsed_seconds':round(time.monotonic()-started,3),
              'runtime_available':False,'game_ready':False,'results':results}
    with args.report.open('x',encoding='utf-8') as output:
        json.dump(report,output,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='results'}),flush=True)
    return 0 if report['passed']==report['champions'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
