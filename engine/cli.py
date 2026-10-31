"""Independent OKDEV archive tools. No in-game runtime is implemented."""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('status','inspect','plan','build','prepare','verify','native-check'))
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'status':
        if args.arguments:
            parser.error('status takes no arguments')
        print(json.dumps({'engine':'okdev-independent','offline_archive_tools':True,
                          'runtime_available':False,'game_ready':False},indent=2))
        return 0
    if args.command == 'inspect':
        from .package import main as command
    elif args.command == 'plan':
        from .plan import main as command
    elif args.command == 'build':
        from .build import main as command
    elif args.command == 'verify':
        from .validate import validate
        from pathlib import Path
        verifier = argparse.ArgumentParser(prog='engine verify')
        verifier.add_argument('directory',type=Path)
        verifier.add_argument('--game',type=Path)
        options = verifier.parse_args(args.arguments)
        print(json.dumps(validate(options.directory,game=options.game),indent=2))
        return 0
    elif args.command == 'native-check':
        from .native_lab import main as command
    else:
        from .prepare import main as command
    return command(args.arguments) or 0


if __name__ == '__main__':
    raise SystemExit(main())
