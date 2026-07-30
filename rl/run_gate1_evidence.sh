#!/bin/bash
# Gate 1-BEVISPROTOKOLLET (tryckknappen när skördaren nått 820):
#   ./rl/run_gate1_evidence.sh [ckpt_dir] [n_runs] [dur_s]
# Kör kandidaten sluten-loop på RIKTIGA mvdsv, N körningar, samlar per-run-peak
# + MVD-demos, skriver evidence/gate1_server_runs.json. Bevisregeln: publicera
# bevissidan och validera INNAN någon rapport. Se evidence/policy_bridge_smoke.json
# för bryggans repro (rtx-commit 180448a).
set -euo pipefail
cd "$(dirname "$0")/.."

CKPT_DIR="${1:-pipeline/out/rl/train_dir/gate1_v1/harvest/eval_dir}"
N="${2:-30}"
DUR="${3:-12}"
ONNX="$PWD/pipeline/out/rl/gate1_candidate.onnx"   # ABSOLUT: servern (cwd playground) öppnar filen
SCRATCH=/tmp/claude-1001/-home-benjamin-adm-rex-ml/003dd697-8855-417d-9d80-53960851ebcf/scratchpad
TICKDIR="$SCRATCH/gate1_server_runs"
mkdir -p "$TICKDIR"

echo "=== 1/4 Exporterar kandidaten ($CKPT_DIR) ==="
SF_STDDEV_MAX=1.0 PYTHONPATH=. sim/.venv-sf/bin/python -m rl.export_onnx "$CKPT_DIR" --out "$ONNX"

echo "=== 2/4 Server + binärer ==="
( cd rtx && cargo build --release -p rex-policy -p rtx-game 2>&1 | tail -2 )
cp rtx/target/release/librtx.so rtx/playground/qw/qwprogs.so
if ! pgrep -f "mvdsv.*server_100m" > /dev/null; then
  tmux send-keys -t jobs:1 "cd ~/rex-ml/rtx/playground && ./mvdsv +exec server_100m.cfg" Enter 2>/dev/null \
    || tmux new-window -t jobs -n gate1srv "cd ~/rex-ml/rtx/playground && ./mvdsv +exec server_100m.cfg"
  sleep 4
fi

echo "=== 3/4 $N körningar à ${DUR}s ==="
for i in $(seq 1 "$N"); do
  rtx/target/release/rex-policy-smoke 27700 "$ONNX" "$TICKDIR/run_$i.jsonl" "$DUR" \
    224 -1408 32 90 "gate1_ev_$i" > "$TICKDIR/summary_$i.json" 2>>"$TICKDIR/errors.log" \
    && echo "  run $i: $(grep -oE '"peak_speed_ups":[0-9.]+' "$TICKDIR/summary_$i.json" | head -1)" \
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
            runs.append({"run": i, "peak": s.get("peak_speed_ups"),
                         "ticks": s.get("ticks"), "hz": s.get("tick_rate_hz"),
                         "msec13": s.get("msec13_fraction")})
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
