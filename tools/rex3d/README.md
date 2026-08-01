# rex3d — 3D-artefaktens byggkedja

Kanoniska källor för dm3-3D-artefakten (https://claude.ai/code/artifact/c32e9f16-…):

- `rex3d_template.html` — sidan (WebGL-vy, gate-metrics-panel med trendpilar,
  gate-hoppens mognadsstege, hopp/rutt-paneler). Panelerna läser `DATA.metrics`
  (evidence/gate_metrics_history.json) och `DATA.jumpgates`
  (evidence/jump_gates_latest.json, `review_godkand` styr PRELIMINÄR-bannern).
- `rex3d_build.py` — injicerar BSP-geometri (atlas_geo.b64), mänsklig trafik
  (atlas_heat.b64), trajektorier (rex_trajectories.json från rl/dump_trajectories)
  och evidence-JSON till en självbärande HTML.
- `atlas_geo.b64` / `atlas_heat.b64` — förbyggd dm3-geometri + korpusheat
  (908 M sampel), base64-packade binärbuffertar.

Körning (byggscriptet läser/skriver i sin arbetskatalog, SCRATCH i scriptet):
kopiera dessa filer + färsk rex_trajectories.json till arbetskatalogen och kör
`python rex3d_build.py` ⇒ `rex-dm3-3d.html`, publicera via Artifact-verktyget
på samma fil-path (behåller URL:en).
