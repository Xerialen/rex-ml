# Körbok — fas 1 (Gate 1-träning) och bevisprotokollen

## Starta träningen (tmux-fönstret `jobs`, aldrig blockerande)

```bash
cd ~/rex-ml
EXP=gate1_v1
tmux send-keys -t jobs "PYTHONPATH=. sim/.venv-sf/bin/python -m rl.train_gate1 \
  --algo=APPO --env=qw_gate1 --experiment=$EXP --use_rnn=True --device=gpu \
  --num_workers=32 --num_envs_per_worker=8 --batch_size=4096 \
  --train_for_env_steps=2000000000 --train_dir=pipeline/out/rl/train_dir" Enter
# curriculum-daemonen (äger den GLOBALA stegväxlingen) i samma fönster, andra rutan:
tmux send-keys -t jobs ".venv/bin/python -m rl.curriculum_daemon \
  pipeline/out/rl/train_dir/$EXP" Enter
```

- Daemonen skriver växlingar till `train_dir/<EXP>/curriculum_log.jsonl` — de raderna
  citeras i PROGRESS.md-milstolparna (mätningar, aldrig adjektiv).
- Daemonen avslutar sig själv med `GATE1_KANDIDAT` när steg 4 konvergerat
  (rullande medel-peak >= 800 och kollisionsförlust <= 150 över 200 episoder).
- Checkpoints: SF-standard under `train_dir/<EXP>/checkpoint_p0/`.

## Encoderbeslut (startläge)

SF:s default-MLP-encoder på den platta 97-dim-observationen. En 1-D-konv över
azimutstrålarna är den naturliga uppgraderingen OM steg 3-4 stagnerar — beslutet
tas då på inlärningskurvor, inte i förväg. `--use_rnn=True` är obligatoriskt
(half-beat kräver temporal representation; BRIEF §3.3).

## Vaktposter under träning (operatörsisolering — åtgärda själv, logga i PROGRESS)

- **Stagnation i steg 1-2:** höj entropikoefficienten först; sänk sedan
  friktionsstraffet i steg 2 (agenten får inte lära sig stå still för att undvika
  markstraff — kontrollera att medelfarten inte kollapsar mot 0).
- **Policykollaps (peak rasar >30 % mellan fönster):** sänk lr, öka batch;
  förväntat fenomen, inte nödläge.
- **reward-hacking i steg 3:** exp-kurvan är obegränsad — om värdeförlusten
  exploderar, klipp belöningen vid motsvarande ~850 u/s (över taket 821 är allt brus).

## Bevisprotokoll Gate 1 (bevisregeln: INNAN rundan rapporteras klar)

Träningssimmens siffror räcker ALDRIG. Kedjan:
1. Exportera policyn (torchscript/onnx) ur SF-checkpointen.
2. Driv den genom rtx-klientstacken mot riktig mvdsv (`rtx/crates/rtx-client` har
   nätkoden; `rex-env`-mönstret visar hur usercmds konstrueras; movement-only-läge —
   combat är utanför missionen). Detaljdesign görs när kandidaten finns.
3. >= 30 körningar 100m, servern spelar in demos (mvd). Median-peak >= 800 => PASS.
4. Bevissida enligt stående regeln (inspelningar + kurvor), publicera, SEDAN rapport.

## Gate 2 (fas 2) — samma mönster

`--env=qw_gate2` (registrera `make_env_gate2`), zonrastret laddas automatiskt.
Gate-poäng: `rl.zones.GateScore` implementerar exakt formeln ur
`evidence/gate2_zones.md` (T(v), OPEN-medel, 70 %-täckning). Curriculum A-D kräver
egen daemon-kriterielogik — skrivs när fas 2 inleds, mot uppmätta steg A-C-kriterier.
