#!/usr/bin/env python3
"""Compatibility launcher for the maintained Stillpoint private collector."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from workspace import resolve_workspace


def command_for(workspace, forwarded):
    private = workspace / 'stillpoint-data'
    target = private / 'scripts' / 'invest_snapshot.py'
    if not target.is_file() or target.resolve() == Path(__file__).resolve():
        raise ValueError('Maintained private scripts/invest_snapshot.py is missing; no legacy fallback')
    args = list(forwarded)
    if '--out' not in args and not any(x.startswith('--out=') for x in args):
        args += ['--out', str(private / 'snapshots')]
    return [sys.executable, str(target)] + args, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog='Other options are forwarded to the maintained collector; --resolve-only never runs it.')
    parser.add_argument('--workspace')
    parser.add_argument('--resolve-only', action='store_true')
    args, forwarded = parser.parse_known_args(argv)
    try:
        workspace = resolve_workspace(args.workspace)
        command, private = command_for(workspace, forwarded)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.resolve_only:
        print(json.dumps({'workspace': str(workspace), 'collector': command[1], 'private_output_default': str(private / 'snapshots'), 'executed': False}, ensure_ascii=False))
        return 0
    env = dict(os.environ, INVEST_BASE=str(private))
    # Keep the caller cwd: explicit relative --compare/--out paths retain meaning.
    return subprocess.run(command, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
