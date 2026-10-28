#!/usr/bin/env python3
"""Offline receipt registry for the authorized Beijing 04/16 Stillpoint slots.

No scheduler, network, data collection or deployment is performed here. Mutation
commands are explicit attestations; scan/list never create files. Python 3.9+;
mutations use POSIX flock (macOS/Linux), not expiring filesystem lock files.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time

BJ = timezone(timedelta(hours=8), "Asia/Shanghai")
ORIGIN = datetime(2026, 10, 28, 4, tzinfo=BJ)
STATUSES = {"planned", "started", "failed", "partial", "published_verified"}
DEFAULT_PATH = Path("operations/automation-runs/registry.json")


class RegistryError(ValueError):
    pass


def parse_time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise RegistryError("时间须为带时区的 ISO-8601")
    if result.tzinfo is None or result.utcoffset() is None:
        raise RegistryError("时间不得省略时区")
    return result.astimezone(BJ)


def stamp(value):
    if value.tzinfo is None:
        raise RegistryError("内部时钟须带时区")
    return value.astimezone(BJ).isoformat(timespec="seconds")


def slot_time(slot):
    if not re.fullmatch(r"\d{8}-(04|16)", slot):
        raise RegistryError("批次格式为 YYYYMMDD-04 或 YYYYMMDD-16")
    try:
        result = datetime.strptime(slot, "%Y%m%d-%H").replace(tzinfo=BJ)
    except ValueError:
        raise RegistryError("批次日期无效")
    if result < ORIGIN:
        raise RegistryError("批次早于用户授权起点 2026-10-28 04:00 +08:00")
    return result


def due_slots(now):
    now = parse_time(stamp(now))
    result = []
    day = ORIGIN.date()
    while day <= now.date():
        for hour in (4, 16):
            planned = datetime(day.year, day.month, day.day, hour, tzinfo=BJ)
            if ORIGIN <= planned <= now:
                result.append(planned.strftime("%Y%m%d-%H"))
        day += timedelta(days=1)
    return result


def blank_registry():
    return {"schema_version": 1, "timezone": "Asia/Shanghai",
            "authorized_start": stamp(ORIGIN), "slots": {}, "runs": {}}


def load_registry(path):
    if not path.exists():
        return blank_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError("登记簿不可读，不覆盖损坏文件: " + str(exc))
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("authorized_start") != stamp(ORIGIN)
            or data.get("timezone") != "Asia/Shanghai"
            or not isinstance(data.get("slots"), dict)
            or not isinstance(data.get("runs"), dict)):
        raise RegistryError("登记簿结构/授权起点不匹配，不覆盖")
    for slot, record in data["slots"].items():
        slot_time(slot)
        if (not isinstance(record, dict) or record.get("status") not in STATUSES
                or record.get("planned_at") != stamp(slot_time(slot))
                or not isinstance(record.get("attempts"), list)):
            raise RegistryError("批次状态损坏，不覆盖")
    for run_id, run in data["runs"].items():
        if (not isinstance(run, dict) or run.get("run_id") != run_id
                or run.get("status") not in STATUSES - {"planned"}
                or not isinstance(run.get("slots"), list)):
            raise RegistryError("运行回执结构损坏，不覆盖")
        if not run["slots"] or run["slots"] != sorted(set(run["slots"])):
            raise RegistryError("运行覆盖批次损坏，不覆盖")
        parse_time(run.get("actual_started_at"))
        parse_time(run.get("heartbeat_at"))
        for slot in run["slots"]:
            if slot not in data["slots"] or run_id not in data["slots"][slot]["attempts"]:
                raise RegistryError("运行与批次关联损坏，不覆盖")
        if run["status"] == "published_verified" and (
                not re.fullmatch(r"[0-9a-f]{64}", str(run.get("receipt_sha256", "")))
                or run.get("blocking_gaps") != [] or run.get("required_checks_passed") is not True
                or not run.get("receipt_path")):
            raise RegistryError("验证发布状态缺实际回执，不认定成功")
        if run["status"] == "published_verified":
            try:
                with Path(run["receipt_path"]).open("rb") as handle:
                    raw_receipt = handle.read(1024 * 1024 + 1)
            except (OSError, TypeError, ValueError) as exc:
                raise RegistryError("已发布回执缺失或不可读，不能按成功跳过；先核回执，不覆盖登记簿: " + str(exc))
            if (len(raw_receipt) > 1024 * 1024
                    or hashlib.sha256(raw_receipt).hexdigest() != run["receipt_sha256"]):
                raise RegistryError("已发布回执SHA256不匹配，不能按成功跳过；先核回执，不覆盖登记簿")
    if sum(r["status"] == "started" for r in data["runs"].values()) > 1:
        raise RegistryError("存在多个活动运行，需先核冲突，不覆盖")
    for slot, record in data["slots"].items():
        if record["status"] == "planned":
            if record["attempts"]:
                raise RegistryError("计划状态与历史回执不一致")
            continue
        latest = data["runs"].get(record.get("last_run"))
        if (not latest or slot not in latest["slots"] or latest["status"] != record["status"]
                or (record["status"] == "started" and record.get("active_run") != latest["run_id"])):
            raise RegistryError("批次缺匹配运行回执，不认定成功或覆盖")
    return data


def planned_record(slot):
    return {"planned_at": stamp(slot_time(slot)), "status": "planned", "attempts": []}


def scan(path, now, include_runs=False):
    data = load_registry(path)
    rows = []
    for slot in due_slots(now):
        record = data["slots"].get(slot, planned_record(slot))
        rows.append(dict(record, slot=slot, pending=record["status"] != "published_verified"))
    return {"schema_version": 1, "timezone": "Asia/Shanghai",
            "authorized_start": stamp(ORIGIN), "as_of": stamp(now),
            "registry_exists": path.exists(), "slots": rows,
            "pending_slots": [r["slot"] for r in rows if r["pending"]],
            "missed_slots": [r["slot"] for r in rows if r["status"] == "planned"],
            "retry_slots": [r["slot"] for r in rows if r["status"] in ("failed", "partial")],
            "active_runs": [r["run_id"] for r in data["runs"].values() if r["status"] == "started"],
            **({"runs": data["runs"]} if include_runs else {})}


def atomic_write(path, data):
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def transaction(path, lock_timeout=3.0):
    try:
        import fcntl
    except ImportError:
        raise RegistryError("写登记簿需要 POSIX flock；当前平台仅支持只读 scan/list")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Kernel locks disappear when the process dies. Never unlink/reclaim a live
    # lock file based on mtime: doing so would permit two writers on two inodes.
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + lock_timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RegistryError("登记簿正被其他事务写入；稍后重试，不抢锁")
                time.sleep(0.05)
        data = load_registry(path)
        before = json.dumps(data, sort_keys=True)
        yield data
        if json.dumps(data, sort_keys=True) != before:
            atomic_write(path, data)
    finally:
        os.close(fd)


def pid_is_dead(pid):
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False  # Unknown ownership is not proof of death.
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.ESRCH
    return False


def finish_run(data, run, status, now, details):
    run.update(status=status, actual_finished_at=stamp(now), **details)
    for slot in run["slots"]:
        record = data["slots"][slot]
        if record.get("active_run") != run["run_id"]:
            raise RegistryError("运行已被后续批次接手，禁止旧回执覆盖")
        record.update(status=status, last_run=run["run_id"], actual_finished_at=stamp(now))
        record.pop("active_run", None)
        for field in ("blocking_gaps", "disclosed_limits", "publication_outcome"):
            if field in details:
                record[field] = details[field]


def start(path, now, run_id, slots=None, all_due=False, owner_pid=None,
          recover_stale=False, lease_ttl=21600, note=""):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", run_id):
        raise RegistryError("run-id 使用不超过120位的字母、数字、点、下划线或短横线")
    if lease_ttl < 60:
        raise RegistryError("租约TTL不得少于60秒")
    if owner_pid is not None and (owner_pid <= 0 or pid_is_dead(owner_pid)):
        raise RegistryError("owner-pid 须为实际仍存活的长期执行进程；不能填临时命令PID")
    with transaction(path) as data:
        if run_id in data["runs"]:
            prior = data["runs"][run_id]
            if slots is not None and sorted(set(slots)) != prior["slots"]:
                raise RegistryError("相同run-id不得改变覆盖批次；重试/新范围使用新run-id")
            return dict(prior, idempotent=True)
        available = due_slots(now)
        selected = sorted(set(slots or [])) if not all_due else [
            s for s in available if data["slots"].get(s, {}).get("status") != "published_verified"]
        if not selected:
            raise RegistryError("没有待执行批次")
        for slot in selected:
            slot_time(slot)
            if slot not in available:
                raise RegistryError("不得开始未来批次")
            if data["slots"].get(slot, {}).get("status") == "published_verified":
                raise RegistryError("批次已有验证发布回执，禁止重复执行")
        for active in data["runs"].values():
            if active["status"] != "started":
                continue
            old = (now - parse_time(active["heartbeat_at"])).total_seconds() >= lease_ttl
            dead = active.get("owner_host") == socket.gethostname() and pid_is_dead(active.get("owner_pid"))
            if not (recover_stale and old and dead):
                raise RegistryError("已有运行 " + active["run_id"] +
                                    "；TTL到期不证明死亡，先续做/核活性，不能抢活锁")
            finish_run(data, active, "failed", now,
                       {"failure_reason": "TTL已过且同机执行PID确证不存在；显式恢复",
                        "recovered_by": run_id})
        # Persist the due plan, including slots not selected by this attempt.
        for slot in available:
            data["slots"].setdefault(slot, planned_record(slot))
        previous = sorted({data["slots"][s]["last_run"] for s in selected
                           if data["slots"][s].get("last_run")})
        run = {"run_id": run_id, "status": "started", "slots": selected,
               "actual_started_at": stamp(now), "heartbeat_at": stamp(now),
               "coverage_from": data["slots"][selected[0]]["planned_at"],
               "coverage_through": data["slots"][selected[-1]]["planned_at"],
               "coverage_mode": "one_latest_legal_refresh_for_due_slots",
               "historical_snapshots_reconstructed": False,
               "owner_pid": owner_pid, "owner_host": socket.gethostname(),
               "retry_of": previous, "note": note}
        data["runs"][run_id] = run
        for slot in selected:
            record = data["slots"][slot]
            record["attempts"].append(run_id)
            for field in ("blocking_gaps", "disclosed_limits", "publication_outcome"):
                record.pop(field, None)
            record.update(status="started", active_run=run_id, last_run=run_id,
                          actual_started_at=stamp(now))
        return dict(run, idempotent=False)


def receipt_issues(receipt, run, now):
    if receipt.get("run_id") != run["run_id"] or receipt.get("covered_slots") != run["slots"]:
        raise RegistryError("回执run_id/covered_slots必须准确匹配本次运行")
    issues = []
    gaps = receipt.get("blocking_gaps")
    if not isinstance(gaps, list) or any(not isinstance(g, str) or not g.strip() for g in gaps):
        issues.append("blocking_gaps须显式为字符串列表（无阻断缺项时[]）")
    elif gaps:
        issues.extend(gaps)
    limits = receipt.get("disclosed_limits")
    if not isinstance(limits, list) or any(not isinstance(g, str) or not g.strip() for g in limits):
        issues.append("disclosed_limits须显式为字符串列表（无限制时[]）")
    try:
        if parse_time(receipt.get("actual_data_cutoff")) > now:
            issues.append("actual_data_cutoff在未来")
    except RegistryError:
        issues.append("缺实际数据截止时间及时区")
    def evidence_refs(value):
        return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)

    checks = receipt.get("required_checks", {})
    if (not isinstance(checks, dict) or checks.get("passed") is not True
            or not evidence_refs(checks.get("evidence"))):
        issues.append("缺本次检查通过及证据引用")
    publication = receipt.get("publication", {})
    if not isinstance(publication, dict):
        publication = {}
    for field in ("private_sha", "public_sha"):
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", str(publication.get(field, ""))):
            issues.append("缺有效" + field)
    if (publication.get("pages_status") != "success" or not publication.get("pages_run_id")
            or publication.get("online_bytes_match") is not True
            or publication.get("readonly_verified") is not True
            or not evidence_refs(publication.get("evidence"))):
        issues.append("缺目标Pages成功、线上字节/只读验证或证据引用")
    outcome = publication.get("outcome", "published")
    if outcome not in ("published", "verified_no_change"):
        issues.append("publication.outcome无效")
    if outcome == "verified_no_change" and (
            publication.get("no_changes") is not True or publication.get("last_usable_verified") is not True):
        issues.append("无变化回执缺实际无变化检查及线上最后可用版核验")
    try:
        verified = parse_time(publication.get("verified_at"))
        if not parse_time(run["actual_started_at"]) <= verified <= now:
            issues.append("发布核验时间不在本次实际运行范围")
    except RegistryError:
        issues.append("缺实际发布核验时间及时区")
    return issues


def complete(path, now, run_id, receipt_path):
    try:
        raw = receipt_path.read_bytes()
        if len(raw) > 1024 * 1024:
            raise RegistryError("回执超过1MiB；仅记录状态与证据引用")
        receipt = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise RegistryError("需要实际JSON运行回执: " + str(exc))
    if not isinstance(receipt, dict):
        raise RegistryError("回执须为JSON对象")
    digest = hashlib.sha256(raw).hexdigest()
    with transaction(path) as data:
        run = data["runs"].get(run_id)
        if run is None:
            raise RegistryError("没有start回执，不能宣称完成")
        if run["status"] != "started":
            if run.get("receipt_sha256") == digest:
                return dict(run, idempotent=True)
            raise RegistryError("已结束运行不可重写；补齐缺项使用新run-id续做")
        issues = receipt_issues(receipt, run, now)
        status = "partial" if issues else "published_verified"
        limits = receipt.get("disclosed_limits")
        finish_run(data, run, status, now,
                   {"receipt_path": str(receipt_path.resolve()), "receipt_sha256": digest,
                    "blocking_gaps": issues,
                    "disclosed_limits": limits if isinstance(limits, list) else [],
                    "required_checks_passed": isinstance(receipt.get("required_checks"), dict)
                    and receipt["required_checks"].get("passed") is True,
                    "publication_outcome": receipt.get("publication", {}).get("outcome", "published")
                    if isinstance(receipt.get("publication"), dict) else None,
                    "actual_data_cutoff": receipt.get("actual_data_cutoff")})
        return dict(run, idempotent=False)


def fail(path, now, run_id, reason):
    if not reason.strip():
        raise RegistryError("失败须注明实际原因")
    with transaction(path) as data:
        run = data["runs"].get(run_id)
        if run is None:
            raise RegistryError("没有start回执")
        if run["status"] == "failed" and run.get("failure_reason") == reason:
            return dict(run, idempotent=True)
        if run["status"] != "started":
            raise RegistryError("已结束运行不可重写；重试使用新run-id")
        finish_run(data, run, "failed", now, {"failure_reason": reason})
        return dict(run, idempotent=False)


def heartbeat(path, now, run_id):
    with transaction(path) as data:
        run = data["runs"].get(run_id)
        if run is None or run["status"] != "started":
            raise RegistryError("只能延续仍在执行的运行")
        run["heartbeat_at"] = stamp(now)
        return dict(run)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "list", "start", "complete", "fail", "heartbeat"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--registry", type=Path, help="测试/迁移可显式选择文件，默认工作区operations/automation-runs/registry.json")
    parser.add_argument("--now", help="只读scan/list的观察时点；写命令使用真实时钟")
    parser.add_argument("--run-id")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--slot", action="append", help="可重复；YYYYMMDD-04/16")
    group.add_argument("--all-due", action="store_true")
    parser.add_argument("--owner-pid", type=int, help="可选真实长期执行PID；未记录时不自动回收执行租约")
    parser.add_argument("--recover-stale", action="store_true")
    parser.add_argument("--lease-ttl", type=int, default=21600, help="秒；过期仍需同机PID确证死亡")
    parser.add_argument("--note", default="")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    try:
        if not args.workspace.is_dir():
            raise RegistryError("工作区目录不存在")
        path = args.registry or args.workspace / DEFAULT_PATH
        now = datetime.now(BJ)
        if args.now:
            if args.command not in ("scan", "list"):
                raise RegistryError("写回执不得覆盖真实时钟；--now仅供只读观察")
            now = parse_time(args.now)
        if args.command in ("scan", "list"):
            result = scan(path, now, include_runs=args.command == "list")
        else:
            if not args.run_id:
                raise RegistryError("写命令需要--run-id")
            if args.command == "start":
                if not args.slot and not args.all_due:
                    raise RegistryError("start需要显式--slot或--all-due")
                result = start(path, now, args.run_id, args.slot, args.all_due, args.owner_pid,
                               args.recover_stale, args.lease_ttl, args.note)
            elif args.command == "complete":
                if not args.receipt:
                    raise RegistryError("complete需要--receipt JSON文件")
                result = complete(path, now, args.run_id, args.receipt)
            elif args.command == "fail":
                if not args.reason:
                    raise RegistryError("fail需要--reason")
                result = fail(path, now, args.run_id, args.reason)
            else:
                result = heartbeat(path, now, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RegistryError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
