#!/bin/bash
# 静观：自动快照（由 launchd 调用，不用手动运行）
# 两种情况会运行：到了定时时间；或者 auto/request.txt 被改动（Claude 远程触发）。
# request.txt 的内容只当作一个编号记进状态文件，不会被执行。

BASE="${INVEST_BASE:-$HOME/学习}"
PY="${INVEST_PY:-python3}"
SNAP="$BASE/snapshots"
REQ="$BASE/auto/request.txt"
STATUS="$SNAP/auto_status.txt"
LOG="$SNAP/auto.log"
LOCK="$SNAP/.auto.lock"

mkdir -p "$SNAP"

# 防止两次运行重叠；超过 10 分钟的锁视为残留
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0
  else
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

trigger="schedule"
token=""
if [ -f "$REQ" ] && { [ ! -f "$STATUS" ] || [ "$REQ" -nt "$STATUS" ]; }; then
  trigger="request"
  token="$(head -n 1 "$REQ" | tr -cd 'A-Za-z0-9_-' | cut -c1-40)"
fi

start="$(date '+%Y-%m-%d %H:%M:%S')"
cd "$BASE" || exit 1
"$PY" invest_snapshot.py --days 2 > /dev/null 2> "$SNAP/.auto_last_err.txt"
code=$?
end="$(date '+%Y-%m-%d %H:%M:%S')"
latest="$(ls -t "$SNAP"/snapshot_*.md 2>/dev/null | head -n 1)"

{
  echo "last_start=$start"
  echo "last_end=$end"
  echo "exit_code=$code"
  echo "trigger=$trigger"
  echo "request_token=$token"
  echo "latest=$(basename "$latest" 2>/dev/null)"
} > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"

{
  echo "[$start → $end] trigger=$trigger token=$token exit=$code latest=$(basename "$latest" 2>/dev/null)"
  sed 's/^/  /' "$SNAP/.auto_last_err.txt" | tail -n 20
} >> "$LOG"
# 日志只留最近 1000 行
tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit $code
