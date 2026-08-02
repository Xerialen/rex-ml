# GODKÄND FÖR DRIFT — grundat-kravet behåller 100 % (2/2) av mega- och 87 % (136/156) av RA-gatens mänskliga lyckade låg-entré-försök; alla stickprovade förluster är korrekt klassade luftgrepp (repro: evidence/repro/validate_grounded_humans.py)

Återvalidering: 2026-08-02, DM3-analytikern. Uppföljning av villkoret i
evidence/analyst_megattempt_review.md (review 4): fixen (`_grounded` +
grundat-krav i `_item_events`) skulle återvalideras mot mänskliga positiva
före driftsättning.

## Vad som validerats

Patchade rl/jump_gates.py (GROUND_DZ 0.5, GROUND_RUN 3 via båda grannsampel,
GROUND_D2Z 0.2) körd mot mänskliga pickup-fönster ur store-dm3
(4on4/dm3/mvd; samma hash-ordnade 400-pickups-sampel per item som review 4;
fönster [t−25 s, t+2 s] per (demo_key, slot), gap-split >150 ms).
Gammal logik = identisk körning med `_grounded` forcerad till True.

```
~/rex-ml/.venv/bin/python ~/rex-ml/evidence/repro/validate_grounded_humans.py
```

## Siffror

| Gate | Fönster | Gamla försök/lyckade | Nya försök/lyckade | Retention lyckade |
|---|---|---|---|---|
| SNG-mega | 352 | 2 / 2 | 2 / 2 | **100 %** |
| RA-tagningen | 392 | 217 / 156 | 176 / 136 | **87 %** |

Botdumpar (egen omkörning, ej koordinatorns claim): traj_53G.json och
traj_0907.json ger **alla sex gates 0/0** — det underkända ep6-eventet
(luftburen apex z 67,8) fälls nu korrekt av kurvaturkravet.

## Prognosnotering (viktig kalibrering av min egen 21/24-siffra)

Review 4-prognosen "21/24" avsåg min ad hoc-klassning (z<100 fyra sekunder
före pickup) — INTE detektorns egen lins. Genom detektorns fulla villkor
(intervallentré i d<300 med z<100 + samtidigt klättringssample) räknades
bara **2 av 352** mänskliga megatagningar som låg-entré-försök redan FÖRE
fixen: de flesta av "mina 24" har intervallentré uppifrån (aldrig ute ur
d<300-regionen sedan hyllnivån) och föll redan på low-villkoret. Fixen
tappade inget av de 2. Retention 100 % ≥ prognosens 87,5 %.

## RA-förlustdiagnos (20 tappade lyckanden)

Fem av fem stickprovade (demo/slot/t: 5225/6/31175, 37017/5/454664,
34458/4/1201494, 52534/4/852962, 34603/1/941499) är **rena luftgrepp**:
spelaren nuddar RA (304) mitt i hoppbågen (z 330→371 medan d2 krymper
<60, d²z ≈ −0,6..−3 = gravitationen vid deras 34–51 ms dt) och har INGET
grundat sample ≥ entré+80 inom d2<120 i hela intervallet — varken före
(uppfartsapexar ~307 på d2 ~95–118 är också luftburna) eller efter
(faller av utan ledge-landning). `_grounded` felklassar alltså inga stödda
sampel; förlusten är semantisk (grip-utan-landning), korrekt begränsad
(13 %) och över koordinatorns väsentlighetströskel 79 %.

## dt-förbehåll (dokumenteras, kräver ingen åtgärd)

Mänsklig MVD-data är 34–51 ms/sampel; botdumpar 26 ms. Gravitationens
|d²z| är 0,54 u/sampel² @26 ms mot tröskeln 0,2 (marginal 2,7×) och
0,9–2,1 på människodata (ännu större marginal). Separationen verifierad
i båda regimerna (ep6-apexen fälld; mänskliga plateåer origin 120/184
respektive RA-ledgen behållna).

## Känd kvarvarande begränsning (ingen justering krävs nu)

En bot som lär sig människostilens rena luftgrepp (touch utan landning på
ledge/hylla) undermäts: både försöket och lyckandet uteblir (climbed_near
krävs för att intervallet ska räknas alls). Omfattning hos människor:
13 % av RA-lyckanden, 0 av 2 mega. OM detta blir relevant (bot som bevisat
plockar item utan att gaten registrerar det): föreslagen minimal justering
är att låta lyckad pickup i ett låg-entré-intervall räknas som
försök+lyckat även utan climbed_near (`if low and (climbed_near or suc)`),
vilket per konstruktion inte kan återinföra ep6-klassens falska positiva
(de har suc=False). INTE implementerat — kräver egen granskningsrunda.

## Domslut

**GODKÄND FÖR DRIFT.** Mega-retention 100 % (2/2), RA-retention 87 %
(136/156) ≥ tröskeln 79 %; alla stickprovade förluster korrekt klassade
luftgrepp; regressionerna på botdumparna själv-verifierade (6× 0/0).
Trösklarna GROUND_DZ/GROUND_D2Z/GROUND_RUN behöver inte justeras.

Konfidens: **Hög** (352+392 pickup-fönster, deterministisk hash-sampling,
fysikaliskt verifierad luftburenhet i alla stickprov; allt reproducerbart
via kommandot ovan).
