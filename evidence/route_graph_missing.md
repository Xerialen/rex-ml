# DM3: saknade rutter i ruttsetet — de-facto-ruttgrafen ur korpusen

Underlag: 3,008,058 direkta transiter (samma liv, dt<=15 s) ur 2,146 demos (mvd/4on4). 738,740 kandidat-transiter (19.7 %) förkastades som död/respawn/diskontinuitets-artefakter (livsgräns enligt route-labs same_life-semantik), plus 632 transiter med fysiskt omöjlig hastighet (>2500 u/s över minsta möjliga förflyttning). Kanter med <20 demos klassas ej.

Kantklasser (n_demos>=20): COVERED 16, PARTIAL 90, MISSING 272 (+0 triviala hopp), TELE 3. Transit-täckning: 2.3 % COVERED, 59.5 % PARTIAL, 23.8 % MISSING (+0.0 % triviala, 14.5 % TELE).

## De 12 viktigaste saknade rutterna (symmetriska par ihopvikta)

**1. mega_hill <-> spawn2** — 38100 transiter totalt
   - mega_hill->spawn2: 38100 transiter, 2128 demos, med 1.28 s (p25 1.07 / p75 1.96, min 0.58)

**2. ratop <-> spawn5** — 34639 transiter totalt
   - ratop->spawn5: 32382 transiter, 2121 demos, med 3.36 s (p25 2.92 / p75 4.71, min 1.76)
   - spawn5->ratop: 2257 transiter, 1319 demos, med 10.32 s (p25 9.14 / p75 12.14, min 2.30)

**3. mega_sng <-> spawn1** — 32561 transiter totalt
   - mega_sng->spawn1: 32561 transiter, 2123 demos, med 1.43 s (p25 1.33 / p75 1.82, min 1.02)

**4. lg_water <-> mega_hill** — 32153 transiter totalt
   - mega_hill->lg_water: 26498 transiter, 2121 demos, med 4.67 s (p25 3.55 / p75 7.04, min 2.25)
   - lg_water->mega_hill: 5655 transiter, 1908 demos, med 6.47 s (p25 5.42 / p75 8.63, min 3.46)

**5. pent <-> spawn6** — 27314 transiter totalt
   - pent->spawn6: 21882 transiter, 2115 demos, med 5.38 s (p25 5.12 / p75 6.23, min 2.34)
   - spawn6->pent: 5432 transiter, 1965 demos, med 3.18 s (p25 2.55 / p75 5.60, min 2.15)

**6. spawn3 <-> tele_sng_out** — 23597 transiter totalt
   - tele_sng_out->spawn3: 23398 transiter, 2104 demos, med 4.56 s (p25 3.74 / p75 6.53, min 2.91)
   - spawn3->tele_sng_out: 199 transiter, 186 demos, med 10.28 s (p25 8.45 / p75 12.31, min 5.47)

**7. mega_pent <-> pent** — 21466 transiter totalt
   - mega_pent->pent: 15278 transiter, 2116 demos, med 1.76 s (p25 1.57 / p75 2.39, min 0.83)
   - pent->mega_pent: 6188 transiter, 2098 demos, med 3.55 s (p25 2.75 / p75 5.63, min 0.69)

**8. mega_hill <-> tele_sng_out** — 20178 transiter totalt
   - tele_sng_out->mega_hill: 20178 transiter, 2121 demos, med 1.94 s (p25 1.50 / p75 3.38, min 0.68)

**9. spawn2 <-> spawn5** — 19925 transiter totalt
   - spawn2->spawn5: 19925 transiter, 2117 demos, med 4.16 s (p25 3.71 / p75 5.04, min 2.99)

**10. ralow_ng <-> spawn5** — 19100 transiter totalt
   - ralow_ng->spawn5: 19100 transiter, 2120 demos, med 2.05 s (p25 1.53 / p75 3.74, min 0.93)

**11. rl <-> spawn3** — 17920 transiter totalt
   - rl->spawn3: 17920 transiter, 2121 demos, med 7.18 s (p25 6.24 / p75 8.88, min 2.77)

**12. ring <-> spawn6** — 16212 transiter totalt
   - spawn6->ring: 15868 transiter, 2101 demos, med 3.15 s (p25 2.74 / p75 4.39, min 1.78)
   - ring->spawn6: 344 transiter, 305 demos, med 8.02 s (p25 3.75 / p75 11.07, min 2.31)

## Alla saknade kanter (rangordnade)

| rutt | transiter | demos | median-s | kommentar |
|---|---|---|---|---|
| mega_hill->spawn2 | 38100 | 2128 | 1.28 | avstånd 405 u |
| mega_sng->spawn1 | 32561 | 2123 | 1.43 | avstånd 392 u; motsatt riktning täckt av ruttsetet |
| ratop->spawn5 | 32382 | 2121 | 3.36 | avstånd 944 u |
| mega_hill->lg_water | 26498 | 2121 | 4.67 | avstånd 1016 u |
| tele_sng_out->spawn3 | 23398 | 2104 | 4.56 | avstånd 1390 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| pent->spawn6 | 21882 | 2115 | 5.38 | avstånd 714 u |
| tele_sng_out->mega_hill | 20178 | 2121 | 1.94 | avstånd 497 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn2->spawn5 | 19925 | 2117 | 4.16 | avstånd 963 u |
| ralow_ng->spawn5 | 19100 | 2120 | 2.05 | avstånd 569 u |
| rl->spawn3 | 17920 | 2121 | 7.18 | avstånd 1428 u |
| spawn6->ring | 15868 | 2101 | 3.15 | avstånd 860 u |
| mega_pent->pent | 15278 | 2116 | 1.76 | avstånd 855 u |
| spawn4->spawn3 | 11131 | 2098 | 7.29 | avstånd 1362 u |
| tele_ya_out->pent | 11074 | 2124 | 2.78 | avstånd 532 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| sng->spawn1 | 10629 | 2080 | 4.70 | avstånd 781 u |
| tele_ya_out->lg_water | 10624 | 2083 | 6.16 | avstånd 894 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_hill->gl_water | 10559 | 2073 | 5.22 | avstånd 747 u |
| spawn4->lg_water | 10436 | 2086 | 5.39 | avstånd 705 u |
| ratop->ralow_ng | 10280 | 2091 | 3.86 | avstånd 470 u; motsatt riktning täckt av ruttsetet |
| rl->lg_water | 9615 | 2069 | 5.06 | avstånd 753 u |
| ratop->ring | 8905 | 2066 | 4.10 | avstånd 716 u; motsatt riktning täckt av ruttsetet |
| spawn6->mega_hill | 8616 | 2058 | 3.75 | avstånd 914 u |
| lg_water->spawn3 | 8502 | 2052 | 9.12 | avstånd 837 u |
| tele_ya_out->spawn3 | 8061 | 2040 | 7.13 | avstånd 1481 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| tele_ya_out->mega_pent | 8009 | 2054 | 5.64 | avstånd 574 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| lg_water->spawn2 | 7625 | 1987 | 7.59 | avstånd 1373 u |
| tele_sng_out->ralow_ng | 7056 | 2005 | 5.33 | avstånd 488 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| quad->mega_hill | 7054 | 2042 | 3.23 | avstånd 575 u |
| rl->ssg_ya | 7052 | 2034 | 7.85 | avstånd 1182 u |
| quad->spawn3 | 6829 | 2017 | 7.04 | avstånd 1332 u |
| gl_water->lg_water | 6754 | 1967 | 3.88 | avstånd 542 u |
| ratop->quad | 6252 | 2000 | 6.01 | avstånd 1243 u; motsatt riktning täckt av ruttsetet |
| pent->mega_pent | 6188 | 2098 | 3.55 | avstånd 855 u |
| tele_sng_out->lg_water | 5922 | 1947 | 7.38 | avstånd 1405 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| tele_ya_out->mega_hill | 5795 | 1959 | 5.56 | avstånd 995 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| lg_water->mega_hill | 5655 | 1908 | 6.47 | avstånd 1016 u |
| lg_water->rl | 5637 | 1940 | 7.42 | avstånd 753 u |
| spawn3->lg_water | 5463 | 1909 | 6.18 | avstånd 837 u |
| spawn6->pent | 5432 | 1965 | 3.18 | avstånd 714 u |
| spawn6->spawn3 | 5333 | 1861 | 7.57 | avstånd 1964 u |
| tele_sng_out->spawn5 | 5202 | 1899 | 7.33 | avstånd 931 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_hill->spawn3 | 5053 | 1902 | 9.49 | avstånd 1276 u |
| lg_water->mega_pent | 5004 | 1859 | 9.27 | avstånd 894 u |
| ratop->mega_hill | 4890 | 1904 | 5.01 | avstånd 878 u |
| ring->spawn3 | 4212 | 1812 | 6.80 | avstånd 1526 u |
| mega_pent->spawn6 | 4129 | 1768 | 7.44 | avstånd 1400 u |
| tele_ya_out->ssg_ya | 4074 | 1761 | 8.33 | avstånd 1284 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_pent->gl_water | 3975 | 1773 | 5.75 | avstånd 763 u |
| spawn4->ssg_ya | 3829 | 1753 | 7.97 | avstånd 1118 u |
| spawn6->mega_pent | 3647 | 1630 | 6.37 | avstånd 1400 u |
| tele_ya_out->sng | 3530 | 1663 | 9.58 | avstånd 1843 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn6->spawn1 | 3470 | 1642 | 8.93 | avstånd 1730 u |
| tele_sng_out->spawn2 | 3386 | 1639 | 4.89 | avstånd 252 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn6->lg_water | 3285 | 1615 | 9.30 | avstånd 1545 u |
| mega_pent->lg_water | 3209 | 1621 | 6.70 | avstånd 894 u |
| ring->ralow_ng | 3157 | 1603 | 5.70 | avstånd 744 u |
| quad->ssg_ya | 3150 | 1632 | 6.93 | avstånd 1263 u |
| mega_hill->spawn4 | 3057 | 1571 | 7.62 | avstånd 1075 u |
| spawn4->gl_water | 2989 | 1544 | 6.74 | avstånd 487 u |
| gl_water->mega_hill | 2918 | 1485 | 4.52 | avstånd 747 u |
| tele_ya_out->gl_water | 2883 | 1538 | 7.52 | avstånd 563 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| gl_water->spawn3 | 2812 | 1580 | 8.67 | avstånd 1258 u |
| rl->gl_water | 2811 | 1499 | 6.38 | avstånd 500 u |
| gl_water->rl | 2777 | 1525 | 7.86 | avstånd 500 u |
| quad->spawn2 | 2729 | 1524 | 4.96 | avstånd 941 u |
| ring->spawn5 | 2708 | 1523 | 7.48 | avstånd 1089 u |
| spawn2->lg_water | 2671 | 1437 | 6.63 | avstånd 1373 u |
| tele_ya_out->spawn2 | 2564 | 1416 | 6.58 | avstånd 1380 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn6->ratop | 2453 | 1401 | 10.37 | avstånd 1497 u |
| spawn5->ratop | 2257 | 1319 | 10.32 | avstånd 944 u |
| ring->spawn2 | 2196 | 1328 | 5.60 | avstånd 295 u |
| lg_water->ssg_ya | 2182 | 1323 | 9.71 | avstånd 636 u |
| spawn6->ssg_ya | 2126 | 1298 | 7.83 | avstånd 1922 u |
| rl->spawn2 | 2125 | 1291 | 8.65 | avstånd 1504 u |
| gl_water->spawn2 | 2103 | 1294 | 5.79 | avstånd 1143 u |
| spawn6->tele_ya_out | 2056 | 1221 | 4.63 | avstånd 864 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| tele_sng_out->gl_water | 2027 | 1254 | 7.56 | avstånd 1230 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| lg_water->spawn4 | 1868 | 1187 | 7.36 | avstånd 705 u |
| ralow_ng->spawn3 | 1862 | 1177 | 8.55 | avstånd 1552 u |
| pent->quad | 1846 | 1310 | 6.44 | avstånd 617 u |
| ring->ssg_ya | 1838 | 1200 | 7.38 | avstånd 1661 u |
| spawn6->gl_water | 1832 | 1159 | 9.39 | avstånd 1083 u |
| tele_ya_out->spawn6 | 1751 | 1145 | 8.40 | avstånd 864 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_hill->ssg_ya | 1710 | 1175 | 9.98 | avstånd 1364 u |
| ring->spawn1 | 1708 | 1137 | 9.97 | avstånd 1140 u |
| rl->mega_pent | 1705 | 1167 | 10.60 | avstånd 357 u |
| ring->pent | 1658 | 1113 | 6.69 | avstånd 1186 u |
| ssg_ya->lg_water | 1650 | 1108 | 7.06 | avstånd 636 u |
| ssg_ya->mega_hill | 1644 | 1126 | 8.20 | avstånd 1364 u |
| ssg_ya->quad | 1634 | 1141 | 9.21 | avstånd 1263 u |
| spawn6->spawn2 | 1626 | 1092 | 5.43 | avstånd 1099 u |
| ratop->spawn2 | 1518 | 1086 | 6.82 | avstånd 693 u; motsatt riktning täckt av ruttsetet |
| gl_water->mega_pent | 1496 | 1069 | 8.55 | avstånd 763 u |
| pent->gl_water | 1495 | 1067 | 6.20 | avstånd 609 u |
| mega_sng->tele_sng_in | 1475 | 874 | 3.01 | avstånd 585 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| rl->pent | 1471 | 1044 | 8.69 | avstånd 623 u |
| sng->mega_hill | 1470 | 1024 | 5.84 | avstånd 1219 u |
| spawn3->mega_hill | 1447 | 1029 | 8.67 | avstånd 1276 u |
| tele_sng_out->pent | 1388 | 990 | 7.33 | avstånd 1410 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn4->spawn2 | 1360 | 985 | 8.94 | avstånd 1477 u |
| spawn2->gl_water | 1320 | 906 | 6.76 | avstånd 1143 u |
| ring->lg_water | 1294 | 901 | 8.39 | avstånd 1396 u |
| ssg_ya->ring | 1256 | 939 | 8.66 | avstånd 1661 u |
| tele_sng_out->sng | 1242 | 912 | 8.34 | avstånd 1065 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn6->ralow_ng | 1234 | 885 | 7.64 | avstånd 1601 u |
| pent->lg_water | 1219 | 934 | 7.57 | avstånd 1134 u; motsatt riktning täckt av ruttsetet |
| spawn3->quad | 1219 | 906 | 9.23 | avstånd 1332 u |
| spawn6->tele_sng_out | 1216 | 891 | 4.21 | avstånd 1138 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn4->mega_pent | 1160 | 861 | 10.64 | avstånd 391 u |
| spawn3->gl_water | 1088 | 848 | 7.94 | avstånd 1258 u |
| mega_hill->pent | 1084 | 849 | 9.56 | avstånd 963 u |
| spawn4->pent | 1080 | 849 | 9.07 | avstånd 664 u |
| spawn6->rl | 1075 | 790 | 10.15 | avstånd 1094 u |
| mega_sng->spawn5 | 1002 | 718 | 3.61 | avstånd 785 u; motsatt riktning täckt av ruttsetet |
| tele_sng_out->tele_ya_out | 960 | 765 | 5.44 | avstånd 1402 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn2->spawn3 | 944 | 745 | 10.65 | avstånd 1476 u |
| gl_water->spawn4 | 942 | 777 | 8.26 | avstånd 487 u |
| mega_hill->ring | 922 | 732 | 3.29 | avstånd 408 u |
| ratop->lg_water | 918 | 723 | 9.46 | avstånd 1562 u |
| spawn3->ring | 869 | 695 | 9.41 | avstånd 1526 u |
| spawn6->spawn4 | 817 | 651 | 8.37 | avstånd 1105 u |
| tele_ya_out->spawn1 | 806 | 649 | 11.72 | avstånd 2341 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| ralow_ng->ssg_ya | 802 | 653 | 8.87 | avstånd 1841 u |
| quad->spawn1 | 782 | 643 | 10.19 | avstånd 1908 u; motsatt riktning täckt av ruttsetet |
| quad->spawn5 | 773 | 622 | 9.42 | avstånd 1862 u; motsatt riktning täckt av ruttsetet |
| gl_water->ssg_ya | 764 | 623 | 10.04 | avstånd 1119 u |
| ratop->rl | 761 | 629 | 10.55 | avstånd 1792 u; motsatt riktning täckt av ruttsetet |
| sng->spawn3 | 755 | 610 | 9.65 | avstånd 2417 u |
| spawn6->spawn5 | 724 | 591 | 9.45 | avstånd 1860 u |
| ratop->pent | 721 | 622 | 9.20 | avstånd 1785 u |
| spawn3->spawn2 | 720 | 579 | 8.78 | avstånd 1476 u |
| spawn2->rl | 694 | 560 | 9.14 | avstånd 1504 u |
| quad->ralow_ng | 690 | 596 | 8.00 | avstånd 1429 u |
| quad->lg_water | 644 | 552 | 9.68 | avstånd 901 u |
| quad->pent | 643 | 545 | 6.58 | avstånd 617 u |
| tele_sng_out->mega_pent | 632 | 540 | 9.62 | avstånd 1888 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| quad->mega_pent | 615 | 537 | 8.19 | avstånd 982 u |
| ring->gl_water | 591 | 483 | 8.20 | avstånd 1118 u |
| mega_pent->spawn3 | 589 | 529 | 12.50 | avstånd 1605 u |
| ssg_ya->spawn2 | 574 | 504 | 9.17 | avstånd 1651 u |
| ring->mega_pent | 565 | 489 | 8.69 | avstånd 1749 u |
| mega_hill->mega_pent | 531 | 460 | 11.98 | avstånd 1442 u |
| tele_sng_in->spawn1 | 518 | 454 | 1.38 | avstånd 432 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_pent->rl | 505 | 446 | 11.34 | avstånd 357 u |
| lg_water->quad | 500 | 437 | 11.48 | avstånd 901 u |
| lg_water->tele_ya_out | 436 | 379 | 9.87 | avstånd 894 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn3->tele_ya_out | 432 | 371 | 6.37 | avstånd 1481 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| pent->spawn3 | 425 | 392 | 11.35 | avstånd 1810 u |
| sng->lg_water | 408 | 362 | 10.18 | avstånd 2213 u |
| lg_water->spawn6 | 395 | 349 | 13.20 | avstånd 1545 u |
| tele_ya_out->ralow_ng | 389 | 352 | 9.55 | avstånd 1871 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| pent->mega_hill | 389 | 367 | 9.31 | avstånd 963 u |
| ratop->spawn4 | 388 | 352 | 9.89 | avstånd 1744 u |
| spawn3->pent | 386 | 363 | 10.01 | avstånd 1810 u |
| sng->ratop | 384 | 344 | 11.41 | avstånd 1400 u |
| sng->tele_ya_out | 377 | 332 | 6.77 | avstånd 1843 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_sng->mega_hill | 376 | 339 | 7.91 | avstånd 1338 u |
| tele_ya_out->spawn5 | 358 | 327 | 11.35 | avstånd 2312 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn2->ssg_ya | 354 | 321 | 10.92 | avstånd 1651 u |
| ring->spawn6 | 344 | 305 | 8.02 | avstånd 860 u |
| ratop->tele_ya_out | 322 | 291 | 8.22 | avstånd 1666 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| ssg_ya->gl_water | 319 | 295 | 8.96 | avstånd 1119 u |
| sng->tele_sng_out | 301 | 281 | 5.76 | avstånd 1065 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| sng->spawn5 | 292 | 264 | 8.02 | avstånd 1140 u |
| tele_sng_out->spawn1 | 292 | 261 | 10.79 | avstånd 1109 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| sng->ssg_ya | 291 | 263 | 9.37 | avstånd 2544 u |
| ratop->sng | 290 | 263 | 10.16 | avstånd 1400 u |
| pent->ring | 288 | 269 | 7.82 | avstånd 1186 u |
| sng->tele_sng_in | 280 | 249 | 6.36 | avstånd 899 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn2->spawn4 | 274 | 254 | 9.71 | avstånd 1477 u |
| spawn3->mega_pent | 270 | 251 | 11.16 | avstånd 1605 u |
| ssg_ya->pent | 247 | 230 | 10.74 | avstånd 1665 u |
| sng->spawn2 | 234 | 226 | 8.85 | avstånd 1000 u |
| ratop->gl_water | 230 | 218 | 9.42 | avstånd 1527 u |
| ralow_ng->lg_water | 221 | 212 | 10.86 | avstånd 1729 u |
| sng->rl | 221 | 207 | 11.12 | avstånd 2043 u |
| pent->rl | 210 | 199 | 11.37 | avstånd 623 u |
| ssg_ya->tele_ya_out | 209 | 198 | 8.08 | avstånd 1284 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_pent->spawn4 | 209 | 195 | 11.74 | avstånd 391 u |
| mega_hill->tele_ya_out | 199 | 193 | 9.55 | avstånd 995 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn3->tele_sng_out | 199 | 186 | 10.28 | avstånd 1390 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| ralow_ng->sng | 192 | 181 | 11.10 | avstånd 1244 u |
| tele_sng_out->spawn6 | 181 | 174 | 9.88 | avstånd 1138 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| sng->pent | 179 | 172 | 9.88 | avstånd 1609 u |
| ssg_ya->ralow_ng | 176 | 170 | 10.89 | avstånd 1841 u |
| mega_pent->mega_hill | 167 | 157 | 10.69 | avstånd 1442 u |
| mega_pent->spawn2 | 167 | 157 | 11.43 | avstånd 1846 u |
| sng->gl_water | 164 | 150 | 10.30 | avstånd 1814 u |
| pent->spawn2 | 164 | 159 | 11.35 | avstånd 1302 u |
| ssg_ya->spawn5 | 161 | 158 | 12.20 | avstånd 2408 u |
| mega_hill->sng | 158 | 149 | 7.95 | avstånd 1219 u |
| mega_sng->spawn3 | 156 | 151 | 11.18 | avstånd 2420 u |
| rl->spawn6 | 143 | 136 | 13.03 | avstånd 1094 u |
| ssg_ya->mega_pent | 141 | 136 | 11.65 | avstånd 1291 u |
| sng->spawn4 | 141 | 135 | 10.01 | avstånd 2040 u |
| gl_water->spawn6 | 134 | 131 | 12.88 | avstånd 1083 u |
| spawn2->pent | 134 | 131 | 11.33 | avstånd 1302 u |
| ssg_ya->sng | 131 | 125 | 12.55 | avstånd 2544 u |
| quad->gl_water | 131 | 123 | 9.37 | avstånd 544 u |
| mega_hill->ralow_ng | 130 | 122 | 6.37 | avstånd 921 u |
| sng->ralow_ng | 125 | 123 | 9.90 | avstånd 1244 u |
| sng->mega_pent | 125 | 118 | 10.94 | avstånd 2378 u |
| pent->tele_ya_out | 122 | 121 | 4.26 | avstånd 532 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| lg_water->ring | 119 | 115 | 12.27 | avstånd 1396 u |
| ralow_ng->pent | 115 | 109 | 11.11 | avstånd 1865 u |
| pent->spawn4 | 113 | 109 | 11.74 | avstånd 664 u |
| ralow_ng->rl | 113 | 110 | 11.74 | avstånd 1988 u |
| spawn5->spawn3 | 111 | 109 | 10.75 | avstånd 2119 u |
| spawn3->sng | 109 | 108 | 12.44 | avstånd 2417 u |
| mega_hill->spawn5 | 108 | 104 | 8.29 | avstånd 1364 u |
| gl_water->quad | 103 | 103 | 10.95 | avstånd 544 u |
| ratop->spawn1 | 101 | 100 | 12.36 | avstånd 1271 u |
| mega_sng->tele_ya_out | 97 | 93 | 8.41 | avstånd 2103 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn1->spawn3 | 96 | 96 | 12.84 | avstånd 2453 u |
| ralow_ng->tele_ya_out | 95 | 94 | 9.85 | avstånd 1871 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn4->spawn6 | 92 | 90 | 13.62 | avstånd 1105 u |
| mega_sng->lg_water | 90 | 88 | 11.58 | avstånd 2352 u |
| spawn1->tele_ya_out | 86 | 84 | 10.52 | avstånd 2341 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| ratop->spawn6 | 85 | 80 | 9.68 | avstånd 1497 u |
| ratop->mega_pent | 84 | 84 | 11.80 | avstånd 2128 u |
| mega_sng->spawn6 | 81 | 79 | 6.31 | avstånd 1412 u; motsatt riktning täckt av ruttsetet |
| ring->mega_sng | 80 | 77 | 10.46 | avstånd 972 u |
| gl_water->tele_ya_out | 79 | 72 | 8.92 | avstånd 563 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| pent->ssg_ya | 74 | 74 | 12.12 | avstånd 1665 u |
| spawn3->spawn5 | 73 | 72 | 11.49 | avstånd 2119 u |
| mega_pent->quad | 71 | 70 | 7.26 | avstånd 982 u |
| pent->ratop | 70 | 70 | 12.52 | avstånd 1785 u |
| spawn1->spawn6 | 69 | 67 | 11.38 | avstånd 1730 u |
| spawn3->ralow_ng | 68 | 67 | 11.84 | avstånd 1552 u |
| spawn6->tele_sng_in | 67 | 66 | 11.04 | avstånd 1599 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_sng->tele_sng_out | 66 | 64 | 8.14 | avstånd 1031 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_pent->ssg_ya | 66 | 64 | 13.14 | avstånd 1291 u |
| mega_sng->ratop | 65 | 64 | 12.71 | avstånd 1260 u |
| ralow_ng->gl_water | 64 | 64 | 9.95 | avstånd 1634 u |
| ralow_ng->spawn1 | 62 | 61 | 12.68 | avstånd 943 u |
| spawn1->lg_water | 62 | 62 | 12.87 | avstånd 2457 u |
| ralow_ng->spawn4 | 60 | 58 | 11.05 | avstånd 1950 u |
| rl->sng | 59 | 59 | 13.74 | avstånd 2043 u |
| mega_sng->spawn2 | 58 | 58 | 9.88 | avstånd 1014 u |
| mega_sng->pent | 56 | 55 | 11.43 | avstånd 1927 u |
| spawn2->mega_pent | 54 | 51 | 12.41 | avstånd 1846 u |
| mega_hill->spawn6 | 50 | 48 | 10.16 | avstånd 914 u |
| pent->tele_sng_out | 50 | 50 | 10.14 | avstånd 1410 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn5->ssg_ya | 48 | 47 | 10.86 | avstånd 2408 u |
| mega_sng->rl | 47 | 47 | 12.12 | avstånd 2294 u |
| ralow_ng->mega_pent | 45 | 44 | 12.67 | avstånd 2327 u |
| spawn1->pent | 44 | 42 | 13.71 | avstånd 2170 u |
| spawn3->spawn6 | 44 | 43 | 12.13 | avstånd 1964 u |
| spawn2->sng | 43 | 42 | 12.12 | avstånd 1000 u |
| mega_sng->ssg_ya | 40 | 40 | 11.14 | avstånd 2611 u |
| tele_ya_out->mega_sng | 40 | 40 | 11.56 | avstånd 2103 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| gl_water->ring | 39 | 37 | 11.84 | avstånd 1118 u |
| mega_sng->spawn4 | 36 | 36 | 11.86 | avstånd 2281 u |
| ring->tele_sng_in | 34 | 32 | 11.40 | avstånd 856 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_hill->spawn1 | 34 | 34 | 9.82 | avstånd 1466 u |
| spawn4->sng | 32 | 32 | 13.54 | avstånd 2040 u |
| spawn2->tele_ya_out | 32 | 32 | 10.30 | avstånd 1380 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_sng->gl_water | 30 | 29 | 11.08 | avstånd 2026 u |
| pent->ralow_ng | 29 | 29 | 10.92 | avstånd 1865 u |
| mega_pent->ring | 28 | 28 | 7.93 | avstånd 1749 u |
| quad->mega_sng | 26 | 26 | 9.05 | avstånd 1689 u |
| tele_sng_out->tele_ya_in | 25 | 24 | 4.24 | avstånd 1121 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_sng->ralow_ng | 25 | 24 | 11.45 | avstånd 1042 u |
| spawn1->ssg_ya | 25 | 25 | 12.72 | avstånd 2690 u |
| tele_ya_out->tele_sng_in | 25 | 25 | 13.07 | avstånd 2087 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| mega_pent->tele_ya_out | 24 | 24 | 11.88 | avstånd 574 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| spawn1->gl_water | 23 | 22 | 11.83 | avstånd 2185 u |
| quad->tele_sng_in | 23 | 23 | 11.48 | avstånd 1639 u; tele-relaterad (approach/utgång till telepad — rörelsedelen) |
| pent->spawn5 | 23 | 23 | 13.34 | avstånd 2227 u |
| lg_water->sng | 21 | 21 | 13.94 | avstånd 2213 u |
| spawn1->ratop | 21 | 21 | 13.98 | avstånd 1271 u |
| ssg_ya->spawn6 | 20 | 20 | 12.48 | avstånd 1922 u |

## Triviala hopp (median < 1.5 s och avstånd < 300 u) — redovisas separat, inget döljs

| rutt | transiter | demos | median-s | avstånd u |
|---|---|---|---|---|

## Observation: fyra identifierade rutter finns inte som direkta kanter

- **rl->ratop** (rl_to_ratop): endast 11 direkta transiter i korpusen — människor passerar alltid en annan nod på vägen (t.ex. spawn3/spawn4/telepaderna), så rutten sönderfaller i segment som återfinns som andra kanter (klassade PARTIAL).
- **ya->ratop** (ya_to_ratop): endast 0 direkta transiter i korpusen — människor passerar alltid en annan nod på vägen (t.ex. spawn3/spawn4/telepaderna), så rutten sönderfaller i segment som återfinns som andra kanter (klassade PARTIAL).
- **ya->rl** (ya_to_rl): endast 1 direkta transiter i korpusen — människor passerar alltid en annan nod på vägen (t.ex. spawn3/spawn4/telepaderna), så rutten sönderfaller i segment som återfinns som andra kanter (klassade PARTIAL).
- **ya->ssg_ya** (ya_to_ssg_ya): endast 0 direkta transiter i korpusen — människor passerar alltid en annan nod på vägen (t.ex. spawn3/spawn4/telepaderna), så rutten sönderfaller i segment som återfinns som andra kanter (klassade PARTIAL).


## Sanity: topp-10 kanter totalt (alla klasser)

| # | rutt | transiter | demos | median-s | klass |
|---|---|---|---|---|---|
| 1 | tele_sng_in->tele_sng_out | 277642 | 2144 | 0.03 | TELE |
| 2 | spawn3->ya | 246740 | 2144 | 0.38 | PARTIAL |
| 3 | spawn4->rl | 223056 | 2146 | 0.04 | PARTIAL |
| 4 | rl->spawn4 | 163234 | 2135 | 0.04 | PARTIAL |
| 5 | spawn5->tele_sng_in | 144191 | 2144 | 0.56 | PARTIAL |
| 6 | ya->tele_ya_out | 141493 | 2142 | 0.03 | TELE |
| 7 | spawn1->tele_sng_in | 133465 | 2141 | 0.93 | PARTIAL |
| 8 | spawn2->mega_hill | 85701 | 2140 | 1.07 | PARTIAL |
| 9 | ya->spawn3 | 78711 | 2129 | 0.38 | PARTIAL |
| 10 | ssg_ya->spawn3 | 75590 | 2131 | 1.58 | PARTIAL |

Metod och full kanttabell: `evidence/route_graph.json`. Livssegmentering enligt route-labs same_life-semantik (spawns-händelser) plus frags-dödsfall och icke-teleport-diskontinuiteter; teleport in->ut räknas som egen kantklass TELE eftersom förflyttningen där är spelmekanik, inte rörelse.