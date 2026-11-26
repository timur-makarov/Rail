#!/usr/bin/env bash
# Kill a process and every process below it, even those that started their own session (the bench starts each
# command and each child in a session of its own, so killing a process group misses them). SIGKILL, as a machine
# that stops would.
#   killtree.sh PID
set -u
collect() {
  local p=$1 c
  echo "$p"
  for c in $(pgrep -P "$p" 2>/dev/null); do collect "$c"; done
}
[ $# -eq 1 ] || { echo "usage: killtree.sh PID" >&2; exit 2; }
pids=$(collect "$1")
kill -STOP $pids 2>/dev/null   # freeze first, so nothing starts a new child while the tree is killed
kill -KILL $pids 2>/dev/null
echo "killed: $(echo $pids | wc -w) processes"
