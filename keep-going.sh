#!/usr/bin/env bash
# Stop hook: keep the rex-ml mission agent working until the terminating goal is met.
# Fails OPEN on any doubt -- a broken hook must never wedge the session.
set -u
M="$HOME/rex-ml"
[ -d "$M" ] || exit 0                    # not the mission project
[ -f "$M/STOP" ] && exit 0               # human escape hatch: touch ~/rex-ml/STOP
[ -f "$M/REPORT.md" ] && exit 0          # goal reached
C="$M/.keepgoing_count"
n=$(cat "$C" 2>/dev/null || echo 0)
case "$n" in ''|*[!0-9]*) n=0 ;; esac
n=$((n + 1)); echo "$n" > "$C"
[ "$n" -gt 40 ] && exit 0                # hard ceiling on runaway re-prompting
cat <<JSON
{"decision":"block","reason":"Standing mandate active. The mission is NOT complete - ~/rex-ml/REPORT.md does not exist. Re-read ~/rex-ml/CLAUDE.md and the last entry of ~/rex-ml/PROGRESS.md, determine the current BRIEF step, and continue working. Do not idle and do not ask what to do next. If you are genuinely blocked on one of the four stop conditions in BRIEF.md, write the specific question into PROGRESS.md and then run: touch ~/rex-ml/STOP"}
JSON
