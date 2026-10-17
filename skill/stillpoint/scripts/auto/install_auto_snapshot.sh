#!/bin/bash
# 静观：安装自动快照。只需要运行一次。
#   安装或更新：bash ~/学习/install_auto_snapshot.sh
#   卸载：      bash ~/学习/install_auto_snapshot.sh uninstall
# 装好后，Mac 会在周一到周五 08:40、11:35、15:10、21:00 和周六 08:40 自动拉快照；
# Claude 改动 ~/学习/auto/request.txt 时，也会马上拉一次。
# Mac 睡眠时错过的定时，会在唤醒后补跑一次；关机时不会运行。
set -eu

LABEL="com.b1ack.invest-snapshot"
BASE="$HOME/学习"
AUTO="$BASE/auto"
SNAP="$BASE/snapshots"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "${1:-}" = "uninstall" ]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "已卸载自动快照。已有的快照都还在 $SNAP。"
  exit 0
fi

PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "找不到 python3，先确认终端里 python3 能用。"; exit 1; fi
for f in "$BASE/invest_snapshot.py" "$AUTO/run_snapshot.sh"; do
  if [ ! -f "$f" ]; then echo "找不到 $f"; exit 1; fi
done
mkdir -p "$SNAP" "$HOME/Library/LaunchAgents"
[ -f "$AUTO/request.txt" ] || echo "init" > "$AUTO/request.txt"

# 定时：周一到周五 08:40、11:35、15:10、21:00；周六 08:40（补周五美股收盘）
CAL=""
for wd in 1 2 3 4 5; do
  for hm in "8 40" "11 35" "15 10" "21 0"; do
    h="${hm% *}"; m="${hm#* }"
    CAL="$CAL<dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>$h</integer><key>Minute</key><integer>$m</integer></dict>"
  done
done
CAL="$CAL<dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>40</integer></dict>"

cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$AUTO/run_snapshot.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>INVEST_PY</key><string>$PY</string>
    <key>LANG</key><string>en_US.UTF-8</string>
    <key>PYTHONIOENCODING</key><string>utf-8</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <array>$CAL</array>
  <key>WatchPaths</key>
  <array><string>$AUTO/request.txt</string></array>
  <key>RunAtLoad</key><false/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$SNAP/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$SNAP/launchd.err.log</string>
</dict>
</plist>
PL

plutil -lint "$PLIST" >/dev/null
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "已安装。现在先试跑一次，通常一到三分钟……"
before="$(cat "$SNAP/auto_status.txt" 2>/dev/null || true)"
launchctl kickstart "$DOMAIN/$LABEL"
for i in $(seq 1 120); do
  sleep 3
  now="$(cat "$SNAP/auto_status.txt" 2>/dev/null || true)"
  if [ -n "$now" ] && [ "$now" != "$before" ]; then break; fi
done
if [ -f "$SNAP/auto_status.txt" ]; then
  cat "$SNAP/auto_status.txt"
  if grep -q '^exit_code=0$' "$SNAP/auto_status.txt"; then
    echo "试跑成功。以后不用再手动跑了。"
  else
    echo "试跑没有成功，错误记在 $SNAP/auto.log，告诉 Claude 一声就行。"
  fi
else
  echo "六分钟内没等到结果，可能还在跑。告诉 Claude 一声，它会去看 $SNAP/auto.log。"
fi
echo "macOS 可能会弹出“已添加后台项目”的通知，这是正常的。"
