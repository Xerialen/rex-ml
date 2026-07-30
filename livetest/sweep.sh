#!/usr/bin/env bash
# Knob sweep against the recorded human times.
#
# One setting per iteration: apply it (verified by read-back — `rex-drills set` exits non-zero on a
# MISMATCH, and a setting that did not take is skipped rather than measured), run every drill twice,
# write its own raw envelope. Nothing here edits the game module, so every run is the same build and
# the digests in the envelopes keep pointing at the same artifact.
#
# Ordering is by hypothesis strength, not alphabet. The leading suspect is the rocket-jump aim gate:
# `RJ_AIM_TOL` is 0.5 deg (RJ_CERT_AIM_DEG/3) and the stance is abandoned after RJ_STANCE_TIMEOUT
# = 2.5 s. On `rj-pent-to-lifts-to-window-to-quad` the planner returns a *short* 558-unit route and
# the bot does gain 512 units of height, yet takes 19.6 s — about eight stance timeouts' worth — with
# only one steering watchdog firing. That is the signature of an aim gate the bot cannot satisfy in
# time, not of a bot that is stuck.
#
# usage: ./sweep.sh <port> <spec.json> <outdir>
set -uo pipefail

PORT=${1:-27700}
SPEC=${2:-drills_human_x2.json}
OUT=${3:-evidence/sweep}
DRILLS=../rtx/target/release/rex-drills
FLOOR=30

mkdir -p "$OUT"

# Stock values, restored between settings so each is measured against the same background and a
# sweep of N knobs never becomes a sweep of one accumulating pile. The rj_* numbers are the code
# constants in bot/mod.rs (RJ_STANCE 16, RJ_AIM_TOL = RJ_CERT_AIM_DEG/3 = 0.5, RJ_STANCE_TIMEOUT
# 2.5, RJ_LIFTOFF_TIMEOUT 0.3, RJ_BALLISTIC_SLACK 1.0).
DEFAULTS=(
  rtx_bot_glide 1 rtx_bot_nearfield 1 rtx_bot_hopplan 1 rtx_bot_bandplan 1
  rtx_bot_zigzag 1 rtx_bot_lod 1 rtx_bot_walkplan 1 rtx_bot_magnet 1
  rtx_bot_greed 1 rtx_bot_hazard_health 1 rtx_bot_hazard_k 15
  rtx_bot_turnrate 0 rtx_jump_runup 0.5 rtx_bot_skill 3
  rtx_jump_curl_hold 0 rtx_jump_curl_gain 0
)
# NOTE: `rtx_bot_rocketjump` is absent on purpose. It is read only when the navmesh is built, so
# it cannot be restored between settings — the sweep runs entirely in the no-rocket-jump regime
# the owner asked for (verified: rj_links 0). Putting it in DEFAULTS would imply otherwise.

# Ordered by what the baseline actually blames. Decomposing the -99.3 s total gap into "time lost
# running further" vs "time lost running slower" puts 71 % on the detour: where the bot's path
# matches the human's the margin is -1 to -2.6 s, and where it is 2-3.7x longer the margin is
# -9 to -14 s. So routing knobs come first and steering knobs second, which is the reverse of the
# order the rocket-jump finding suggested.
declare -a NAMES=(
  lod_off hazardk_0 bandplan_off magnet_off greed_off hazard_health_off
  lod_off_hazardk_0 lod_off_bandplan_off
  turnrate_2000 skill_4 nearfield_off glide_off hopplan_off walkplan_off zigzag_off
  runup_0 runup_0.85
)
declare -a SETS=(
  "rtx_bot_lod 0" "rtx_bot_hazard_k 0" "rtx_bot_bandplan 0" "rtx_bot_magnet 0"
  "rtx_bot_greed 0" "rtx_bot_hazard_health 0"
  "rtx_bot_lod 0 rtx_bot_hazard_k 0" "rtx_bot_lod 0 rtx_bot_bandplan 0"
  "rtx_bot_turnrate 2000" "rtx_bot_skill 4" "rtx_bot_nearfield 0" "rtx_bot_glide 0"
  "rtx_bot_hopplan 0" "rtx_bot_walkplan 0" "rtx_bot_zigzag 0"
  "rtx_jump_runup 0" "rtx_jump_runup 0.85"
)

for i in "${!NAMES[@]}"; do
  name=${NAMES[$i]}
  set_pairs=${SETS[$i]}
  raw="$OUT/$name.raw.json"
  if [[ -f $raw ]]; then
    echo "== $name  (already done, skipping)"
    continue
  fi
  echo "== $name : $set_pairs"
  if ! $DRILLS "$PORT" set "${DEFAULTS[@]}" >/dev/null; then
    echo "   !! could not restore defaults — stopping"
    exit 1
  fi
  # shellcheck disable=SC2086
  if ! $DRILLS "$PORT" set $set_pairs; then
    echo "   !! setting did not take — skipped, NOT measured"
    continue
  fi
  $DRILLS "$PORT" drills "$SPEC" "$raw" 0 $FLOOR > "$OUT/$name.log" 2>&1
  python3 - "$raw" <<'PY'
import json, sys, statistics as st
from collections import defaultdict
d = json.load(open(sys.argv[1]))["result"]
g, paths = defaultdict(list), defaultdict(list)
for r in d["drills"]:
    if "margin_secs" in r:
        g[r["id"].rsplit("-r", 1)[0]].append(r["margin_secs"])
    if "metrics" in r and r["outcome"].startswith("arrived"):
        paths[r["id"].rsplit("-r", 1)[0]].append(r["metrics"]["path_len"])
tot = sum(st.median(v) for v in g.values())
pl = sum(st.median(v) for v in paths.values())
# Path total is reported next to the margin because the baseline blames the detour, not the speed:
# a knob that cuts seconds without cutting distance is doing something else, and worth noticing.
print(f"   passed {d['passed']}/{d['total']}  arrived {d['arrived']}  "
      f"sum of median margins {tot:+.1f}s over {len(g)} drills  total path {pl:.0f}u")
PY
done

$DRILLS "$PORT" set "${DEFAULTS[@]}" >/dev/null && echo "defaults restored"
