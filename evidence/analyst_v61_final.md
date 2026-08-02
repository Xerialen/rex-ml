# GODKÄND FÖR DRIFT (v6.1 "förankrat fall") — kvalitetsvillkoren håller exakt (42/43 förankrade ramla, 0 grazers, alla botregressioner); volymavvikelsen mot min prognos (768 mot 662, 5 insläpp mot ≤1) är utredd och beror på fel i MIN prognosproxy, inte i implementationen

## v6.1-slutvalidering

Analyst, 2026-08-02. Detektor: `rl/jump_gates.py` v6.1 (oförändrad av mig; läst
och verifierad mot min spec i analyst_v6_validation.md — förankrat fall ersätter
in-mask-progressionen för ramla, min_d_all över ALLA transitsampel, exakt som
jag specificerade den). Repro: `evidence/repro/human_ledge_v61_final.py`
(+.json; 227 assert-verifierade segment mot detektorn, dt=0.051).

## Utfall mot driftvillkoret

| Villkor (min prognos) | Uppmätt | Status |
|---|---|---|
| 42 av 43 golvförankrade genuina ramla | **42/43** | håller exakt |
| 0 grazers | **0** | håller |
| Botregressioner | probe 0+2 (ep5+ep8), traj_53G 0+3, traj_0907 0+0 | alla gröna, oberoende omkörda |
| 662 gate-event | **768** | avvikelse — utredd, se nedan |
| ≤1 insläpp | **5** | avvikelse — utredd, se nedan |

## Utredningen av avvikelserna (båda är prognosfel, inte detektorfel)

Min 662-prognos räknades på v6-datats eventlista med två proxyfel:
(1) förankrat fall-kandidater begränsades till **v4-event** (min-d<350 på
luftburna sampel över z −20), och (2) min-d mättes bara på sådana sampel.
Den implementerade regeln — **min_d_all över ALLA transitsampel, som jag själv
specificerade den** — ser även fallets djupa framåtsträckning.

Skillnaden är 104 gate-ramla som inte var v4-event: golvförankrade
bandnärvarande misslyckanden i partialfönstret. Uppmätt jämförelse mot de 42
v4-genuina (samma JSON):

| | 104 nya icke-v4 | 42 v4-genuina |
|---|---|---|
| grundade masksampel p10/p50/p90 | 2/8/31 | 2/8/25 |
| massa p50 (u·s) | 121 | 158 |
| andel förankrade | 1,00 | 1,00 |
| min_d_all p10/p50/p90 | 182/362/439 | 197/288/326 |

Statistiskt oskiljbara i de bärande måtten; 45 av de 104 nådde <350 men enbart
under z −20 (mitt i fallet) — exakt det v4-progressionen var blind för.
SO-dominansen (78/26) är väntad: SO-gapet får SO-misslyckanden att falla
tidigare/djupare. Detta är den avsedda semantiken i drift, inte ett hål —
ep5/ep8/ep14/ep23-klasserna förblir strukturellt uteslutna (kräver grundad
maskkontakt + grundad källplattform, båda omöjliga för luftflygare/gårdsloopar,
bekräftat av botregressionerna).

De 5 "insläppen" (mitt ≤1 byggde på gamla bandproxyn n_inledge<5): samtliga är
golvförankrade (2–10 grundade masksampel), massade (16–52 u·s) med verklig
framåtsträckning (min_d 182–418) — under maskesemantiken är de äkta korta
försök, inte junk. Demo-id:n i valideringsutskriften (28382/7, 31522/9,
46585/8, 46857/5, 53123/9).

## Ny regressionsbaslinje (låses för framtida omvalideringar av denna kohort)

24-demoskohorten (`human_ledge_baseline.json`-nycklarna), dt 0.051, genom
v6.1: **768 gate-event = 584 lyckat + 151 ramla (45 NV / 106 SO) + 33 retreat;
42/43 golvförankrade genuina ramla; 0 grazers; genuina lyckade 562/646**
(förlusterna = källgrundskravets 51 ms-bias, dokumenterad). Botdumpar:
probe_ledge_60G ⇒ sidogates 0 + axial 2; traj_53G ⇒ sidogates 0 + axial 3;
traj_0907 ⇒ 0 + 0.

## Kvarstående övervakningspunkter (oförändrade från analyst_v6_validation.md)

1. Bhop-underdetektion: 1-sampels nedslag fäller grundat-flaggan — övervaka
   axial-ramla med hög luftburen maskkontakt i probekörningar; åtgärd
   (d²z-nedslagsdetektor) först om klassen ackumuleras.
2. Källplattformskravets 11 %-bias på 51 ms-humandata — notera vid framtida
   humanbaslinjer; irrelevant för botdumpar.
3. Plattformscirkeln (r 260) är modell, inte BSP.

## Domslut

**GODKÄND FÖR DRIFT.** Detektorn v6.1 mäter det ägarens gate avser: golvför-
ankrad ledgeanvändning med riktningsverifierad sidoetikett, misslyckanden
observerbara på båda sidor inklusive SO-gapets fall, och alla kända artefakt-
klasser (axialhopp, luftöverflygning, gårdsloop, bandgraze, gropluftrum)
strukturellt uteslutna och regressionstestade. Konfidens: hög.

```
cd ~/rex-ml
.venv/bin/python evidence/repro/human_ledge_v61_final.py       # 768 / 42-43 / 0 / 5
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/probe_ledge_60G.json
PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_53G.json
```
