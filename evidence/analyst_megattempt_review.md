# UNDERKÄND — SNG-mega-"försöket" (traj_53G ep 6) är två kedjade bunnyhops in i en vägg, inte hoppnavigering; klättringsvillkoret luras av luftburna hopp-apexar (repro: evidence/repro/verify_mega_attempt.py)

Granskning: 2026-08-02, DM3-analytikern. Fjärde vetogranskningen av
rl/jump_gates.py-claims (tidigare: evidence/analyst_jumpgate_review.md).

## Claim

Detektorn på `~/dumps/traj_53G.json` (30 episoder, greedy @ 5.3G):
gate **SNG-mega: 1 försök, 0 lyckade → nivå 1** (första nollskilda claimet);
övriga fem gates 0/0.

## Reproduktion

```
cd ~/rex-ml && PYTHONPATH=. sim/.venv-sf/bin/python -m rl.jump_gates ~/dumps/traj_53G.json
# → "SNG-mega": {"försök": 1, "lyckade": 0, "nivå": 1}   REPRODUCERAT
PYTHONPATH=. sim/.venv-sf/bin/python evidence/repro/verify_mega_attempt.py
```

Triggern: **episod 6** (spawn "vid tele", route = 24 ben tele↔RA-toppen,
mega_sng_s 0.7), besöksintervall **sampel 2248–2309** (1,6 s, ÖPPET vid
episodslut — stängs av att episoden tar slut, inte av utgång ur regionen).
Entré-z −16,0 (låg ✓). Samtidighetsvillkoret (z ≥ entré+80 OCH d2<120)
uppfylls i sampel **2282–2286** (z 64,0–67,8; d2 101,8–117,2).

## Fysikalisk dekomposition (Observerat/Härlett)

Gravitationsfit på z-serien (andradifferens ≈ −800·0,026² = −0,541/sampel²
⇒ luftburen) visar att nästan hela intervallet är luftburet:

1. **Hopp 1:** takeoff ~s2253 från golvet z=−16 (vz≈265), apex 27,8 @s2266.
2. **Bhop-mellanlandning:** 1–2 sampel touch på ett ~26-enheterssteg vid
   väggbasen (s2269–2270) — enda "stödet" över golvet i hela intervallet.
3. **Hopp 2:** takeoff ~s2270 (vz≈250) **samtidigt som väggkollision**:
   fart 471→194, y låser sig på exakt 144,0 i 14 sampel (väggslide).
   Apex **z=67,8** @s2282 — där tänder samtidighetsvillkoret.
4. s2286: andra väggen (x låser på exakt −800,0, fart 46), fritt fall till
   golvet z=−16 (s2300), därefter springer botten BORT (d2 97→130 stigande)
   tills episoden tar slut 0,2 s senare.

**Max stödd z i intervallet: −16 (golvet).** Apexen 67,8 är 20 u under
lägsta relevanta trappsteg (origin 88) och 92 u under mega-z 160.

## Mänsklig baslinje (store-dm3, samma extrakt som tidigare mätningar)

400 samplade mega-sng-pickups (item_events, taken @ (−720,80,160)),
352 med trajektoria: **93 % tas uppifrån** (hyllnivån origin 184+);
**24 st (7 %) nerifrån** (z<100 4 s före). Av de 24: **21 klättrar trappan**
(grundade 16-enheterssteg origin 24→104) till **stödd platå origin 120**
(= golv −16 + 136) vid x −896..−960, y 32..96, och hoppar därifrån
(apex ~163) för att nudda megan. Ex: demo 47178 slot 7 t 450773;
demo 28933 slot 2 t 589311.

Botten passerade trappbasens x-läge (x≈−941, y −199→−109, s2240–2248) utan
att engagera trappan, och hoppade i stället i **motsatt (NO-) hörn** mot
väggen y=144, varifrån megan inte kan nås (apex-underskott 92 u; människodata
visar noll tagningar från den punkten).

## Kontroll mot de tre tidigare underkännandegrunderna

- *Ankomst uppifrån/z-dipp vid entrén:* NEJ — entrén är genuint låg (golv).
- *Klättring bort från målet:* NEJ — d2 sjunker under bågen (169→102).
- *Disjunkta villkor:* NEJ — samtidigheten håller. MEN: eventet är fysiskt
  samma klass som review-3:s underkända "avsatsstuds z 67,8 på d2 126" —
  identisk apex-z; det passerar nu enbart för att bågen råkade ligga på
  d2 117 i stället för 126. Detektorn balanserar på tröskeln kring exakt
  samma artefakt.

## Domslut och villkorslucka (ändra EJ detektorn utan ny granskning av fixen)

**UNDERKÄND.** Nivå 1 kräver "uppvisad medvetenhet om hoppet som genväg".
Det observerade är policyns normala bhop-lokomotion (450+ UPS kräver kedjade
hopp) som råkar korsa en hopp-apex inom d2<120 efter studs på ett minimalt
steg — ingen stödd höjdvinst, fel hörn, väggkollision, intervall trunkerat
av episodslut, och botten hade redan vänt bort när episoden slutade.

**Luckan:** CLIMB_GAIN mäts mot intervallentré-z och kan uppfyllas helt av
**luftburna** sampel. Två kedjade bhops (45+45 u apexhöjd) över vilket
~25-enderssteg som helst når entré+80 utan att någon förhöjd yta bestigs.

**Föreslagen täppning:** kräv att höjdvinsten hålls av en STÖDD position:
samtidighetssamplet (z ≥ entré+80 ∧ d2 < 120) ska vara grundat — t.ex.
z-stabilt inom ±2 u över ≥3 konsekutiva sampel (78 ms; en ballistisk apex
@26 ms klarar högst ~5 sampel inom ±2 u, så använd hellre ±0,5 u över 3
sampel, eller gravitationsfit-negation som i reproskriptet). Kalibrering:
människornas nerifrån-väg ger stödda platåer på entré+104..+136 (trappsteg
88/104, platå 120 mot golventré −16) — 21/24 mänskliga låg-entré-tagningar
passerar ett grundat +80-krav; botens event får max stödd z = entré+0 och
faller. Fixen måste återvalideras mot samma 24 mänskliga positiva innan den
tas i bruk (jag har inte ändrat detektorn).

Konfidens: **Hög** (bit-exakt trajektoria + gravitationsfit + 352 mänskliga
pickups i samma koordinatsystem; alla siffror reproducerbara via kommandona
ovan).

## Addendum 2026-08-02: fixen implementerad och återvaliderad

Grundat-kravet (`_grounded`: dz ±0.5 mot båda grannar + |d²z| ≤ 0.2)
återvaliderat mot mänskliga positiva: mega 2/2 (100 %), RA 136/156 (87 %)
behållna; botdumpar 6 gates × 0/0 själv-verifierade.
Domslut GODKÄND FÖR DRIFT — se evidence/analyst_grounded_validation.md
och evidence/repro/validate_grounded_humans.py.
