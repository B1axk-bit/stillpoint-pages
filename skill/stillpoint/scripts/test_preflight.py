#!/usr/bin/env python3
"""Isolated behavioral tests: never call production collection or scheduler."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from preflight import REQUIRED, automation_state, build_report, toml_loader, git_state
from invest_snapshot import command_for
from workspace import resolve_workspace

SCRIPTS = Path(__file__).resolve().parent


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / 'workspace'
        self.private = self.root / 'stillpoint-data'
        self.public = self.root / 'stillpoint-pages'
        self.home = self.base / 'codex'
        self.public.mkdir(parents=True)
        for rel in REQUIRED:
            p = self.private / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}' if p.suffix == '.json' else '')
        (self.public / 'scripts').mkdir()
        (self.public / 'scripts/check_publish_data.py').touch()
        self.ledger = self.private / 'confidence/ledger.csv'
        self.ledger.write_text('date,theme,class\n2026-10-15,AI,入格\n')
        self.review = self.private / 'analysis/mainline-review.json'
        self.save_review()
        self.put('confidence/latest.json', {'version': 'fixture-only', 'snapshot': 'snapshot_fixture.json', 'lamps': [{'raw': 'green', 'confirmed': 'red', 'valid': 3}], 'themes': []})
        (self.private / 'snapshots').mkdir()
        (self.private / 'snapshots/snapshot_fixture.json').write_text('{}')
        self.put('analysis/case-reviews.json', {'cases': {'2': {'status': 'completed_with_scoring_limits'}}})

    def put(self, rel, value):
        p = self.private / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))

    def save_review(self):
        self.review.write_text(json.dumps({'review_complete': True, 'asof': '2026-10-28T01:00:00+08:00', 'status': 'completed_conditional_H1', 'ledger_sha256': hashlib.sha256(self.ledger.read_bytes()).hexdigest()}))

    def report(self):
        return build_report(self.root, self.home)

    def test_workspace_parent_and_explicit_missing(self):
        nested = self.private / 'scripts'
        self.assertEqual(resolve_workspace(cwd=nested), self.root)
        self.assertEqual(resolve_workspace(self.private), self.root)
        with self.assertRaises(ValueError):
            resolve_workspace(self.base / 'absent')

    def test_read_only_no_remote_or_probability_claim(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        report = self.report()
        self.assertFalse(report['blocked'])
        self.assertFalse(report['network_used'])
        self.assertFalse(report['snapshot']['freshness_checked'])
        self.assertFalse(report['git']['private']['remote_checked'])
        self.assertEqual(report['research']['lamps'][0]['confirmed'], 'red')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_canonical_blocks(self):
        (self.private / 'scripts/source_quality.py').unlink()
        self.assertTrue(self.report()['blocked'])

    def test_snapshot_path_escape_blocks(self):
        self.put('confidence/latest.json', {'snapshot': '../secret.json'})
        self.assertTrue(self.report()['blocked'])

    def test_multiple_entry_blocks_switch_claim(self):
        self.ledger.write_text(self.ledger.read_text() + '2026-10-28,AI,入格\n')
        self.save_review()
        report = self.report()
        self.assertTrue(report['blocked'])
        self.assertTrue(any('multiple entry' in x['reason'] for x in report['issues']))

    def test_changed_basis_requires_triage(self):
        self.ledger.write_text(self.ledger.read_text() + '2026-10-28,AI,新独立\n')
        report = self.report()
        self.assertTrue(any('basis differs' in x['reason'] for x in report['issues']))

    def test_completed_conditional_is_not_reset_to_pending(self):
        report = self.report()
        self.assertTrue(report['research']['review_complete'])
        self.assertEqual(report['research']['review_status'], 'completed_conditional_H1')

    def test_completed_review_requires_date(self):
        self.review.write_text('{"review_complete": true}')
        self.assertTrue(self.report()['blocked'])

    def test_review_boolean_and_timestamp_strict(self):
        for flag, stamp in [('false', '2026-10-28T01:00:00+08:00'), (True, 'NOT_A_DATE'), (True, '2026-10-28'), (True, '2099-01-01T00:00:00+08:00')]:
            self.review.write_text(json.dumps({'review_complete': flag, 'completed_at': stamp}))
            self.assertTrue(self.report()['blocked'], (flag, stamp))

    def test_git_inspection_does_not_refresh_index(self):
        subprocess.run(['git', 'init', '-q', str(self.public)], check=True)
        watched = self.public / 'fixture.txt'
        watched.write_text('same content')
        subprocess.run(['git', '-C', str(self.public), 'add', '.'], check=True)
        index = self.public / '.git/index'
        before = (index.read_bytes(), index.stat().st_mtime_ns)
        st = watched.stat()
        os.utime(watched, ns=(st.st_atime_ns, st.st_mtime_ns + 2000000000))
        git_state(self.public)
        self.assertEqual(before, (index.read_bytes(), index.stat().st_mtime_ns))

    def test_invalid_object_is_structured_failure(self):
        self.put('confidence/latest.json', [])
        self.assertTrue(self.report()['blocked'])

    def test_invalid_collections_report_blocked(self):
        for value in (None, 42, 'bad'):
            self.put('confidence/latest.json', {'snapshot': 'snapshot_fixture.json', 'themes': value, 'lamps': value})
            self.put('analysis/case-reviews.json', {'cases': value})
            self.assertTrue(self.report()['blocked'])

    def test_bad_automation_encoding_is_unparsed(self):
        folder = self.home / 'automations/fixture'
        folder.mkdir(parents=True)
        (folder / 'automation.toml').write_bytes(b'\xff\xfe')
        result = automation_state(self.home)
        self.assertEqual(result['state'], 'LOCAL_MATCH_UNPARSED')
        self.assertFalse(result['active_proven'])

    def test_automation_absent_not_global_absent(self):
        result = automation_state(self.home)
        self.assertEqual(result['state'], 'LOCAL_NOT_FOUND')
        self.assertFalse(result['active_proven'])
        self.assertIn('not enumerated', result['scope'])

    def test_saved_active_is_unverified_and_prompt_secret_not_emitted(self):
        folder = self.home / 'automations/fixture'
        folder.mkdir(parents=True)
        (folder / 'automation.toml').write_text('name = "静观"\nid = "fixture"\nstatus = "ACTIVE"\nprompt = "private-secret-marker"\nrrule = "FREQ=DAILY;BYHOUR=4,16"\n')
        result = automation_state(self.home)
        self.assertEqual(result['state'], 'SAVED_UNVERIFIED' if toml_loader else 'LOCAL_MATCH_UNPARSED')
        self.assertFalse(result['active_proven'])
        self.assertNotIn('private-secret-marker', json.dumps(result))

    def test_multiline_prompt_cannot_spoof_metadata(self):
        folder = self.home / 'automations/fixture'
        folder.mkdir(parents=True)
        triple = chr(34) * 3
        raw = '\n'.join(['prompt = ' + triple + '静观\nname = "prompt-secret-marker"\nstatus = "ACTIVE"\n' + triple, 'name = "Stillpoint"', 'status = "PAUSED"', 'rrule = ' + triple + 'DTSTART;TZID=Asia/Shanghai:20261028T040000\nRRULE:FREQ=DAILY;BYHOUR=4,16' + triple])
        (folder / 'automation.toml').write_text(raw)
        result = automation_state(self.home)
        self.assertNotIn('prompt-secret-marker', json.dumps(result))
        self.assertFalse(result['active_proven'])
        if toml_loader:
            self.assertEqual(result['matches'][0]['status'], 'PAUSED')
            self.assertIn('Asia/Shanghai', result['matches'][0]['rrule'])
        else:
            self.assertEqual(result['matches'], [])
            self.assertEqual(result['state'], 'LOCAL_MATCH_UNPARSED')

    def test_locator_never_runs_collector(self):
        marker = self.base / 'executed'
        (self.private / 'scripts/invest_snapshot.py').write_text('from pathlib import Path\nPath(%r).touch()\n' % str(marker))
        r = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'invest_snapshot.py'), '--workspace', str(self.root), '--resolve-only'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(json.loads(r.stdout)['executed'])
        self.assertFalse(marker.exists())

    def test_launcher_delegates_with_private_base_and_forwards_args(self):
        target = self.private / 'scripts/invest_snapshot.py'
        target.write_text('import os,sys,json\nprint(json.dumps({"base":os.environ["INVEST_BASE"], "args":sys.argv[1:], "cwd":os.getcwd()}))\n')
        r = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'invest_snapshot.py'), '--workspace', str(self.root), '--days', '3'], cwd=str(self.base), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertEqual(d['base'], str(self.private))
        self.assertEqual(d['cwd'], str(self.base))
        self.assertEqual(d['args'], ['--days', '3', '--out', str(self.private / 'snapshots')])
        command, _ = command_for(self.root, ['--out=custom'])
        self.assertEqual(command[-1], '--out=custom')
        self.assertEqual(command.count('--out'), 0)

    def test_missing_collector_never_uses_legacy(self):
        (self.private / 'scripts/invest_snapshot.py').unlink()
        with self.assertRaises(ValueError):
            command_for(self.root, [])


if __name__ == '__main__':
    unittest.main()
