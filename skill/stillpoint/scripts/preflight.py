#!/usr/bin/env python3
"""Read-only Stillpoint maintenance preflight. No freshness/deployment certificate."""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from workspace import resolve_workspace

try:
    import tomllib as toml_loader
except ImportError:
    toml_loader = None  # Python 3.9/3.10: no unsafe hand-written TOML parser.

REQUIRED = ('scripts/invest_snapshot.py', 'scripts/extra_feeds.py', 'scripts/archive_raw.py',
            'scripts/attractor_client.py', 'scripts/public_market_feeds.py', 'scripts/market_sources.py',
            'scripts/source_quality.py', 'scripts/confidence.py', 'scripts/evidence_candidates.py',
            'scripts/build_cases.mjs', 'docs/source-readers.md', 'docs/daily-publish.md',
            'confidence/rubric.json', 'confidence/lamps.json', 'confidence/ledger.csv',
            'analysis/case-reviews.json', 'analysis/mainline-review.json', 'private/cases.json')


def read_json(path, issues, required=True):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('expected JSON object')
        return value
    except (OSError, ValueError) as exc:
        issues.append({'level': 'blocked' if required else 'warning', 'file': str(path.name), 'reason': 'missing or invalid JSON', 'type': type(exc).__name__})
        return {}


def git_state(path):
    def run(args):
        r = subprocess.run(['git', '--no-optional-locks', '-C', str(path)] + args, capture_output=True, text=True, timeout=8)
        return r.stdout.strip() if r.returncode == 0 else None
    try:
        head = run(['rev-parse', 'HEAD'])
        status = run(['status', '--porcelain'])
        return {'head': head, 'dirty': bool(status) if status is not None else None, 'changed_files': len(status.splitlines()) if status is not None else None, 'remote_checked': False}
    except (OSError, subprocess.TimeoutExpired):
        return {'head': None, 'dirty': None, 'remote_checked': False}


def automation_state(home):
    matches = []
    unparsed_candidates = 0
    for p in sorted((home / 'automations').glob('*/automation.toml')):
        try:
            raw = p.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            unparsed_candidates += 1
            continue
        if toml_loader is None:
            # Discovery hint only. Raw strings may be inside prompts/comments.
            if re.search(r'stillpoint|静观|靜觀', raw, re.I):
                unparsed_candidates += 1
            continue
        try:
            task = toml_loader.loads(raw)
        except ValueError:
            if re.search(r'stillpoint|静观|靜觀', raw, re.I):
                unparsed_candidates += 1
            continue
        if not any(re.search(r'stillpoint|静观|靜觀', str(task.get(k, '')), re.I) for k in ('name', 'prompt')):
            continue
        # Metadata values must come from parsed top-level fields, never prompt text.
        fields = {k: task[k] for k in ('id', 'name', 'kind', 'status', 'rrule') if isinstance(task.get(k), str)}
        matches.append(fields)
    state = 'SAVED_UNVERIFIED' if matches else ('LOCAL_MATCH_UNPARSED' if unparsed_candidates else 'LOCAL_NOT_FOUND')
    return {'state': state, 'matches': matches, 'unparsed_candidates': unparsed_candidates,
            'metadata_parser': 'stdlib tomllib' if toml_loader else 'unavailable on this Python; use Python 3.11+ for metadata',
            'active_proven': False, 'scope': 'local files only; migrated/cloud records not enumerated',
            'next': 'Verify real ID/status/thread/persisted timezone/next run across DST in the native scheduler'}


def build_report(workspace, codex_home=None):
    private = workspace / 'stillpoint-data'
    public = workspace / 'stillpoint-pages'
    issues = []
    for rel in REQUIRED:
        if not (private / rel).is_file():
            issues.append({'level': 'blocked', 'file': rel, 'reason': 'maintained project component missing'})
    if not (public / 'scripts/check_publish_data.py').is_file():
        issues.append({'level': 'blocked', 'file': 'stillpoint-pages/scripts/check_publish_data.py', 'reason': 'release gate missing'})
    latest = read_json(private / 'confidence/latest.json', issues)
    review = read_json(private / 'analysis/mainline-review.json', issues)
    cases = read_json(private / 'analysis/case-reviews.json', issues)
    quality = read_json(private / 'archive/attractor/latest-quality.json', issues, required=False)
    complete = review.get('review_complete')
    if not isinstance(complete, bool):
        issues.append({'level': 'blocked', 'file': 'analysis/mainline-review.json', 'reason': 'review_complete must be a JSON boolean'})
    elif not complete:
        issues.append({'level': 'warning', 'file': 'analysis/mainline-review.json', 'reason': 'research review not marked complete; do applicable checks'})
    if complete is True:
        try:
            stamp = review.get('completed_at') or review.get('asof')
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.tzinfo is None or parsed.utcoffset() is None or parsed > datetime.now(timezone.utc):
                raise ValueError('review timestamp requires timezone and must not be future')
        except (AttributeError, TypeError, ValueError):
            issues.append({'level': 'blocked', 'file': 'analysis/mainline-review.json', 'reason': 'completed review requires a valid nonfuture timestamp with timezone'})
    ledger = private / 'confidence/ledger.csv'
    if ledger.exists():
        digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
        if review.get('ledger_sha256') != digest:
            issues.append({'level': 'warning', 'file': 'analysis/mainline-review.json', 'reason': 'review basis differs from current ledger; triage new evidence before claiming current review'})
        try:
            with ledger.open(encoding='utf-8-sig', newline='') as f:
                entries = Counter(r.get('theme', '') for r in csv.DictReader(f) if r.get('class') == '入格')
            for theme, count in entries.items():
                if count > 1:
                    issues.append({'level': 'blocked', 'file': 'confidence/ledger.csv', 'reason': 'multiple entry rows require explicit effective-version resolution; first-row reader cannot prove switch', 'theme': theme, 'entries': count})
        except (OSError, csv.Error):
            issues.append({'level': 'blocked', 'file': 'confidence/ledger.csv', 'reason': 'cannot inspect entry ambiguity'})
    snapshot = latest.get('snapshot')
    snapshot_exists = isinstance(snapshot, str) and Path(snapshot).name == snapshot and (private / 'snapshots' / snapshot).is_file()
    if not snapshot_exists:
        issues.append({'level': 'blocked', 'file': 'confidence/latest.json', 'reason': 'referenced snapshot missing or unsafe path'})
    for value, kind, file_name in ((latest.get('themes'), list, 'confidence/latest.json:themes'), (latest.get('lamps'), list, 'confidence/latest.json:lamps'), (cases.get('cases'), dict, 'analysis/case-reviews.json:cases')):
        if not isinstance(value, kind):
            issues.append({'level': 'blocked', 'file': file_name, 'reason': 'invalid record collection type'})
    themes = [{k: t.get(k) for k in ('theme', 'cell', 'since', 'score')} for t in (latest.get('themes') if isinstance(latest.get('themes'), list) else []) if isinstance(t, dict)]
    lamps = [{k: t.get(k) for k in ('n', 'raw', 'confirmed', 'valid')} for t in (latest.get('lamps') if isinstance(latest.get('lamps'), list) else []) if isinstance(t, dict)]
    return {'preflight_version': '0.7.0', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'workspace': str(workspace), 'read_only': True, 'network_used': False,
            'git': {'private': git_state(private), 'public': git_state(public)},
            'snapshot': {'file': snapshot, 'exists': snapshot_exists, 'run_at': latest.get('run_at'), 'freshness_checked': False},
            'research': {'rule_version': latest.get('version'), 'themes': themes, 'lamps': lamps,
                         'review_status': review.get('status'), 'review_complete': review.get('review_complete'),
                         'review_at': review.get('completed_at') or review.get('asof'), 'case_review_records': len(cases.get('cases')) if isinstance(cases.get('cases'), dict) else 0},
            'attractor_collection': {k: quality.get(k) for k in ('status', 'collected_at', 'returned_count', 'usable_count', 'review_count', 'invalid_count')},
            'automation': automation_state(Path(codex_home or os.environ.get('CODEX_HOME', Path.home() / '.codex'))),
            'issues': issues, 'blocked': any(x['level'] == 'blocked' for x in issues),
            'limits': ['Source timestamps/identities/thresholds still require source-specific gates',
                       'Remote HEAD, current run, case export, public privacy and Pages bytes not verified here',
                       'Scores/vote agreement are not probabilities; no write, confirmation, trade or deployment performed']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace')
    args = p.parse_args(argv)
    try:
        report = build_report(resolve_workspace(args.workspace))
    except ValueError as exc:
        print(json.dumps({'blocked': True, 'reason': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report['blocked'] else 0


if __name__ == '__main__':
    sys.exit(main())
