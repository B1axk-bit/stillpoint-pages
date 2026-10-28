#!/usr/bin/env python3
"""Behavioral fixtures: all receipts/registries live in TemporaryDirectory."""
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("run_registry.py")
spec = importlib.util.spec_from_file_location("run_registry", SCRIPT)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.path = self.workspace / "ops" / "registry.json"
        self.now = registry.parse_time("2026-10-28T05:15:00+08:00")

    def start(self, run="run-one", slots=None, **kwargs):
        return registry.start(self.path, self.now, run, slots=slots or ["20261028-04"], **kwargs)

    def receipt(self, run, gaps=None):
        value = {
            "run_id": run["run_id"], "covered_slots": run["slots"],
            "actual_data_cutoff": registry.stamp(self.now), "blocking_gaps": gaps or [], "disclosed_limits": [],
            "required_checks": {"passed": True, "evidence": ["isolated-fixture-checks.json"]},
            "publication": {
                "private_sha": "a" * 40, "public_sha": "b" * 40,
                "pages_status": "success", "pages_run_id": "1234567",
                "online_bytes_match": True, "readonly_verified": True,
                "verified_at": registry.stamp(self.now + timedelta(minutes=5)),
                "evidence": ["isolated-fixture-online-check.json"]}}
        p = self.workspace / (run["run_id"] + ".receipt.json")
        p.write_text(json.dumps(value), encoding="utf-8")
        return p, value

    def complete(self, run, gaps=None):
        p, _ = self.receipt(run, gaps)
        return registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)

    def test_read_only_scan_is_anchored_and_creates_nothing(self):
        result = registry.scan(self.path, self.now)
        self.assertEqual(result["missed_slots"], ["20261028-04"])
        self.assertEqual(result["slots"][0]["status"], "planned")
        self.assertFalse(self.path.parent.exists())
        before = registry.scan(self.path, registry.parse_time("2026-10-28T03:59:59+08:00"))
        self.assertEqual(before["pending_slots"], [])

    def test_exact_slots_and_us_dst_do_not_change_beijing_anchor(self):
        self.assertEqual(registry.due_slots(registry.parse_time("2026-10-27T13:00:00-07:00")), ["20261028-04"])
        after = registry.due_slots(registry.parse_time("2026-11-01T12:00:00-08:00"))
        self.assertEqual(after[-1], "20261102-04")
        self.assertEqual(len(after), 11)
        self.assertEqual(registry.due_slots(registry.parse_time("2026-10-28T16:00:00+08:00")),
                         ["20261028-04", "20261028-16"])

    def test_invalid_and_future_slots_are_not_started(self):
        for slot in ["20261027-16", "20260230-04", "20261028-12", "20261028-16"]:
            with self.subTest(slot=slot), self.assertRaises(registry.RegistryError):
                self.start(slots=[slot])
        self.assertFalse(self.path.exists())

    def test_start_is_idempotent_and_never_expands_old_attempt(self):
        first = self.start()
        before = self.path.read_bytes()
        again = registry.start(self.path, self.now + timedelta(days=2), "run-one", all_due=True)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["slots"], first["slots"])
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(registry.RegistryError):
            registry.start(self.path, self.now, "run-one", slots=["20261028-16"])

    def test_complete_requires_actual_matching_run_receipt(self):
        run = self.start()
        missing = self.workspace / "absent.json"
        with self.assertRaises(registry.RegistryError):
            registry.complete(self.path, self.now, run["run_id"], missing)
        p, value = self.receipt(run)
        value["run_id"] = "someone-elses-run"
        p.write_text(json.dumps(value))
        with self.assertRaises(registry.RegistryError):
            registry.complete(self.path, self.now, run["run_id"], p)
        self.assertEqual(registry.scan(self.path, self.now)["pending_slots"], ["20261028-04"])
        self.assertEqual(registry.load_registry(self.path)["runs"][run["run_id"]]["status"], "started")

    def test_verified_receipt_clears_queue_once_without_second_publish(self):
        run = self.start()
        p, _ = self.receipt(run)
        done = registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        self.assertEqual(done["status"], "published_verified")
        before = self.path.read_bytes()
        again = registry.complete(self.path, self.now + timedelta(minutes=20), run["run_id"], p)
        self.assertTrue(again["idempotent"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(registry.scan(self.path, self.now)["pending_slots"], [])
        with self.assertRaises(registry.RegistryError):
            self.start(run="duplicate-publication")

    def test_missing_published_receipt_fails_closed_without_rewriting_registry(self):
        run = self.start()
        p, _ = self.receipt(run)
        registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        before = self.path.read_bytes()
        p.unlink()
        with self.assertRaisesRegex(registry.RegistryError, "回执缺失或不可读"):
            registry.scan(self.path, self.now)
        with self.assertRaises(registry.RegistryError):
            registry.start(self.path, self.now + timedelta(days=1), "must-not-overwrite", all_due=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_published_receipt_fails_closed_without_rewriting_registry(self):
        run = self.start()
        p, value = self.receipt(run)
        registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        before = self.path.read_bytes()
        value["publication"]["online_bytes_match"] = False
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(registry.RegistryError, "SHA256不匹配"):
            registry.scan(self.path, self.now)
        with self.assertRaises(registry.RegistryError):
            registry.start(self.path, self.now + timedelta(days=1), "must-not-overwrite", all_due=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_partial_receipt_keeps_retryable_slot_instead_of_blocking_registry(self):
        run = self.start()
        p, _ = self.receipt(run, ["必要检查未完成"])
        registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        p.unlink()
        self.assertEqual(registry.scan(self.path, self.now)["retry_slots"], ["20261028-04"])
        self.assertEqual(self.start(run="resume-after-partial")["retry_of"], ["run-one"])

    def test_partial_with_permanent_source_gap_stays_pending_until_new_verified_attempt(self):
        run = self.start()
        partial = self.complete(run, ["某源缺凭据；本轮已隔离，未取得新数据"])
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(registry.scan(self.path, self.now)["retry_slots"], ["20261028-04"])
        retry = self.start(run="retry-one")
        self.assertEqual(retry["retry_of"], ["run-one"])
        self.assertEqual(self.complete(retry)["status"], "published_verified")
        data = registry.load_registry(self.path)
        self.assertEqual(data["runs"]["run-one"]["status"], "partial")
        self.assertEqual(data["slots"]["20261028-04"]["attempts"], ["run-one", "retry-one"])

    def test_disclosed_legal_limits_remain_visible_without_repeating_finished_batch(self):
        run = self.start()
        p, value = self.receipt(run)
        value["disclosed_limits"] = ["SEC原件403，未核总额不进入结论", "过旧观测隔离，未投票"]
        p.write_text(json.dumps(value))
        done = registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        self.assertEqual(done["status"], "published_verified")
        self.assertEqual(done["disclosed_limits"], value["disclosed_limits"])
        status = registry.scan(self.path, self.now)
        self.assertEqual(status["pending_slots"], [])
        self.assertEqual(status["slots"][0]["disclosed_limits"], value["disclosed_limits"])

    def test_verified_no_change_requires_last_usable_checks_and_creates_no_commit(self):
        run = self.start()
        p, value = self.receipt(run)
        value["publication"].update(outcome="verified_no_change", no_changes=True, last_usable_verified=True)
        p.write_text(json.dumps(value))
        done = registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        self.assertEqual(done["status"], "published_verified")
        self.assertEqual(done["publication_outcome"], "verified_no_change")
        self.assertFalse((self.workspace / ".git").exists())

    def test_no_change_without_verification_does_not_clear_queue(self):
        run = self.start()
        p, value = self.receipt(run)
        value["publication"].update(outcome="verified_no_change", no_changes=True)
        p.write_text(json.dumps(value))
        done = registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
        self.assertEqual(done["status"], "partial")
        self.assertEqual(registry.scan(self.path, self.now)["retry_slots"], ["20261028-04"])

    def test_weak_or_future_evidence_can_only_be_partial(self):
        mutations = [
            lambda v: v["publication"].update(online_bytes_match=False),
            lambda v: v["publication"].update(pages_status="queued"),
            lambda v: v["publication"].update(verified_at="2026-10-28T04:00:00+08:00"),
            lambda v: v.update(actual_data_cutoff="2026-10-29T00:00:00+08:00"),
            lambda v: v["required_checks"].update(passed=False),
            lambda v: v["required_checks"].update(evidence="not-a-list"),
            lambda v: v.pop("blocking_gaps"),
        ]
        for i, mutate in enumerate(mutations):
            run = self.start(run="weak-" + str(i))
            p, value = self.receipt(run)
            mutate(value)
            p.write_text(json.dumps(value))
            result = registry.complete(self.path, self.now + timedelta(minutes=10), run["run_id"], p)
            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["blocking_gaps"])
            self.assertEqual(registry.scan(self.path, self.now)["pending_slots"], ["20261028-04"])

    def test_fail_is_preserved_and_retry_resumes_instead_of_erasing(self):
        run = self.start()
        result = registry.fail(self.path, self.now, run["run_id"], "网络中断；未发布")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(registry.fail(self.path, self.now, run["run_id"], "网络中断；未发布")["idempotent"])
        again = self.start(run="resumed")
        self.assertEqual(again["retry_of"], ["run-one"])
        self.assertEqual(registry.load_registry(self.path)["runs"]["run-one"]["failure_reason"], "网络中断；未发布")

    def test_offline_multiple_slots_share_actual_catchup_and_do_not_fabricate_history(self):
        later = registry.parse_time("2026-10-30T17:00:00+08:00")
        run = registry.start(self.path, later, "one-catchup", all_due=True)
        self.assertEqual(len(run["slots"]), 6)
        self.assertEqual(run["actual_started_at"], "2026-10-30T17:00:00+08:00")
        self.assertEqual(run["coverage_from"], "2026-10-28T04:00:00+08:00")
        self.assertEqual(run["coverage_through"], "2026-10-30T16:00:00+08:00")
        self.assertFalse(run["historical_snapshots_reconstructed"])
        self.now = later
        self.complete(run)
        rows = registry.scan(self.path, later)["slots"]
        self.assertTrue(all(r["last_run"] == "one-catchup" for r in rows))
        self.assertTrue(all(r["actual_started_at"] == run["actual_started_at"] for r in rows))
        self.assertTrue(all(r["status"] == "published_verified" for r in rows))

    def test_new_run_is_globally_blocked_by_unknown_or_live_owner_even_after_ttl(self):
        self.start()
        later = self.now + timedelta(days=2)
        with self.assertRaises(registry.RegistryError):
            registry.start(self.path, later, "cannot-steal-unknown", all_due=True, recover_stale=True)
        registry.fail(self.path, self.now, "run-one", "人工核对并停止旧运行")
        self.start(run="known-live", owner_pid=os.getpid())
        with self.assertRaises(registry.RegistryError):
            registry.start(self.path, later, "cannot-steal-live", all_due=True, recover_stale=True)

    def test_dead_owner_requires_ttl_and_explicit_recovery(self):
        self.start(owner_pid=os.getpid())
        with patch.object(registry, "pid_is_dead", return_value=True):
            with self.assertRaises(registry.RegistryError):
                registry.start(self.path, self.now + timedelta(seconds=30), "too-early", all_due=True,
                               recover_stale=True)
            with self.assertRaises(registry.RegistryError):
                registry.start(self.path, self.now + timedelta(days=1), "not-explicit", all_due=True)
            run = registry.start(self.path, self.now + timedelta(days=1), "recovered", all_due=True,
                                 recover_stale=True)
        self.assertEqual(run["status"], "started")
        self.assertEqual(registry.load_registry(self.path)["runs"]["run-one"]["status"], "failed")

    def test_heartbeat_prevents_dead_lease_recovery_before_new_ttl(self):
        self.start(owner_pid=os.getpid())
        later = self.now + timedelta(days=1)
        registry.heartbeat(self.path, later, "run-one")
        with patch.object(registry, "pid_is_dead", return_value=True), self.assertRaises(registry.RegistryError):
            registry.start(self.path, later + timedelta(seconds=20), "too-early", all_due=True,
                           recover_stale=True)

    def test_kernel_transaction_lock_is_never_reclaimed_by_ttl(self):
        with registry.transaction(self.path):
            with self.assertRaises(registry.RegistryError):
                with registry.transaction(self.path, lock_timeout=0.05):
                    self.fail("unexpected second writer")
        self.assertEqual(self.start()["status"], "started")

    def test_concurrent_processes_create_only_one_execution(self):
        code = ("import importlib.util,sys; from pathlib import Path; "
                "s=importlib.util.spec_from_file_location('r',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m.start(Path(sys.argv[2]),m.parse_time('2026-10-28T05:00:00+08:00'),"
                "sys.argv[3],slots=['20261028-04'])")
        processes = [subprocess.Popen([sys.executable, "-B", "-c", code, str(SCRIPT), str(self.path), name],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for name in ["worker-a", "worker-b"]]
        outcomes = [p.communicate(timeout=15) for p in processes]
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1], outcomes)
        data = registry.load_registry(self.path)
        self.assertEqual(len(data["runs"]), 1)
        self.assertEqual(len(data["slots"]["20261028-04"]["attempts"]), 1)
        self.assertEqual(list(self.path.parent.glob(".registry.json.*")), [])

    def test_corruption_or_unbacked_success_is_not_overwritten_or_trusted(self):
        self.path.parent.mkdir(parents=True)
        for text in ["{broken", json.dumps(dict(registry.blank_registry(), slots={
                "20261028-04": dict(registry.planned_record("20261028-04"), status="published_verified")}))]:
            self.path.write_text(text)
            with self.assertRaises(registry.RegistryError):
                registry.scan(self.path, self.now)
            with self.assertRaises(registry.RegistryError):
                self.start()
            self.assertEqual(self.path.read_text(), text)

    def test_cli_readonly_supports_clock_but_mutations_cannot_backdate(self):
        command = [sys.executable, "-B", str(SCRIPT), "scan", "--workspace", str(self.workspace),
                   "--now", "2026-10-28T05:00:00+08:00"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["missed_slots"], ["20261028-04"])
        self.assertEqual(list(self.workspace.iterdir()), [])
        command[3] = "start"
        result = subprocess.run(command + ["--run-id", "backdate", "--all-due"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(self.workspace.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
