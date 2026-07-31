#!/bin/bash
# Gate 1-BEVISPROTOKOLLET (tryckknappen när skördaren nått 820):
#   ./rl/run_gate1_evidence.sh [ckpt_dir] [n_runs] [dur_s]
# Kör kandidaten sluten-loop på RIKTIGA mvdsv, N körningar, samlar per-run-peak
# + MVD-demos, skriver evidence/gate1_server_runs.json. Bevisregeln: publicera
# bevissidan och validera INNAN någon rapport. Se evidence/policy_bridge_smoke.json
# för bryggans repro (rtx-commit 180448a).
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${1:-pipeline/out/rl/train_dir/gate1_v1/harvest/best.pth}"
N="${2:-30}"
DUR="${3:-12}"
ONNX="$PWD/pipeline/out/rl/gate1_candidate.onnx"   # ABSOLUT: servern (cwd playground) öppnar filen

# FRYS SNAPSHOT (bryggdiagnosens lärdom: harvest/eval_dir är ett RÖRLIGT mål —
# checkpointen byttes mitt under diagnos ⇒ ONNX och sim-eval var olika policies).
# best.pth är ratchetens stabila artefakt; kopiera till frusen katalog före export.
CKPT_DIR="pipeline/out/rl/gate1_candidate_snapshot"
mkdir -p "$CKPT_DIR/checkpoint_p0"
cp "$SRC" "$CKPT_DIR/checkpoint_p0/checkpoint_999999999_snapshot.pth"  # fast namn, cp skriver över
cp pipeline/out/rl/train_dir/gate1_v1/config.json "$CKPT_DIR/config.json"
echo "snapshot: $SRC -> $CKPT_DIR ($(sha256sum "$SRC" | cut -c1-12))"
SCRATCH=/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad
TICKDIR="$SCRATCH/gate1_server_runs"
mkdir -p "$TICKDIR"

echo "=== 1/4 Exporterar kandidaten ($CKPT_DIR) ==="
SF_STDDEV_MAX=1.0 PYTHONPATH=. sim/.venv-sf/bin/python -m rl.export_onnx "$CKPT_DIR" --out "$ONNX"

echo "=== 2/4 Binärer ==="
( cd rtx && cargo build --release -p rex-policy -p rtx-game 2>&1 | tail -2 )
cp rtx/target/release/librtx.so rtx/playground/qw/qwprogs.so

echo "=== 3/4 $N körningar à ${DUR}s (FÄRSK SERVER PER KÖRNING — upprepade"
echo "    PolicyDrive-sessioner mot samma server ger 0-fart; oberoende körningar) ==="
SRVLOG="$SCRATCH/gate1srv.log"
for i in $(seq 1 "$N"); do
  tmux kill-window -t rexml:gate1srv 2>/dev/null || true
  pkill -x mvdsv 2>/dev/null || true; sleep 1   # fönsterdöd dödar inte processen — porten måste släppas
  : > "$SRVLOG"
  tmux new-window -d -t rexml -n gate1srv \
    "cd ~/rex-ml/rtx/playground && ./mvdsv +exec server_100m.cfg 2>&1 | tee -a $SRVLOG"
  T0=$(date +%s)
  until grep -q "Server spawned" "$SRVLOG" 2>/dev/null; do
    sleep 1
    if grep -q "Address already in use" "$SRVLOG" 2>/dev/null; then pkill -x mvdsv || true; sleep 2; : > "$SRVLOG"; tmux kill-window -t rexml:gate1srv 2>/dev/null || true; tmux new-window -d -t rexml -n gate1srv "cd ~/rex-ml/rtx/playground && ./mvdsv +exec server_100m.cfg 2>&1 | tee -a $SRVLOG"; fi
    if [ $(( $(date +%s) - T0 )) -gt 60 ]; then echo "  server-timeout run $i" >> "$TICKDIR/errors.log"; break; fi
  done
  sleep 2
  rtx/target/release/rex-policy-smoke 27700 "$ONNX" "$TICKDIR/run_$i.jsonl" "$DUR" \
    224 -1408 32 90 "gate1_ev_$i" > "$TICKDIR/summary_$i.json" 2>>"$TICKDIR/errors.log" \
    && echo "  run $i: $(grep -oE '"peak_speed(_ups)?": ?[0-9.]+' "$TICKDIR/summary_$i.json" | head -1)" \
    || echo "  run $i: FEL (se errors.log)"
done

echo "=== 4/4 Aggregerar ==="
.venv/bin/python - "$TICKDIR" "$N" << 'EOF'
import json, sys, glob
from pathlib import Path
import numpy as np
tickdir, n = Path(sys.argv[1]), int(sys.argv[2])
runs = []
for i in range(1, n + 1):
    p = tickdir / f"summary_{i}.json"
    if p.exists():
        try:
            s = json.load(open(p))
            runs.append({"run": i,
                         "peak": s.get("peak_speed", s.get("peak_speed_ups")),
                         "ticks": s.get("ticks"), "hz": s.get("tick_rate_hz"),
                         "msec13": s.get("msec13_frac", s.get("msec13_fraction"))})
        except Exception as e:
            runs.append({"run": i, "error": str(e)[:100]})
peaks = np.array([r["peak"] for r in runs if r.get("peak") is not None])
out = {
    "protocol": "Gate 1 serverbevis: sluten loop på riktiga mvdsv, greedy, 77 Hz",
    "n_ok": int(len(peaks)), "n_requested": n,
    "peak_best": float(peaks.max()) if len(peaks) else None,
    "peak_median": float(np.median(peaks)) if len(peaks) else None,
    "peak_p10": float(np.percentile(peaks, 10)) if len(peaks) else None,
    "gate_820_passed": bool(len(peaks) and peaks.max() >= 820.0),
    "subgoal_850_reached": bool(len(peaks) and peaks.max() >= 850.0),
    "runs": runs,
    "mvd_demos": "rtx/playground/qw/demos/gate1_ev_*.mvd",
}
json.dump(out, open("evidence/gate1_server_runs.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "runs"}, indent=1))
EOF
echo "KLART — bevisregeln: uppdatera bevissidan + validera INNAN rapport."
