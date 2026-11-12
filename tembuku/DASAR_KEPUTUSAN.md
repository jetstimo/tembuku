# Tembuku decision basis

This document explains **every rule** Tembuku uses, where each number comes from, and how it was tested on real data.
Values are of three kinds: **standard** (from a current international standard or official source), **calibrated**
(measured on approved real designs) and **policy** (an engineering choice your team should confirm). Every value can be
changed under *Advanced* in the Tembuku window.

## 0b. Version 1.4.4: every engineering rule (PDF 11 Nov 2026) checked against sources and data
A rule is followed as written unless a credible source **and** the 213-design test show a better choice. Rules not
followed literally stay available under *Advanced* (set them to the PDF value to apply them as written).

| PDF rule | 1.4.4 default | Basis |
|---|---|---|
| 3.1/3.2 FDT up to 6 km on the 48F group (T9-T12), beyond on 96F (T1-T8), as a **preference** | Off (`utamakan_aturan_6km` = No) | Loss grows with length (fibre attenuation ITU-T G.652; class B+ budget 28 dB, G.984.2; FOA: GPON 32-split 13-28 dB), not with fibre count, so the group gives no optical gain. Test: F/T match 36 % on vs 54 % off; new cable 563 vs 425 km |
| 48F branch at most 6 km; longer fibre path on 96F | Followed (`batas_48f_km` 6) | Capacity reserve on long routes: fibre is cheap compared with installation (FOA FTTH design) |
| 3.3 Tap at existing slack, no new slack | Followed with a limit: slack first when at most 600 m / 15 % more cable (`toleransi_slack_antar_m`) | Mid-span access is a normal practice with loose-tube cable (FOA mid-span access; STL, Superior Essex TG082 and OFS guides give 1.8-2.4 m sheath openings). Extra cable to reach a slack costs more than a closure beyond a few hundred metres. Test: 300 m 421 km / 99 checks, **600 m 425 km / 92 checks / best F/T**, 1000 m 434 km / 81, always 481 km / 60 |
| Closure 0-5 m strong, 5-10 m check | Followed (`tap_slack_m` 10) | - |
| Closure 6 holes (1 in + 5 out) | Followed | Manufacturer port count; policy |
| 144F from POP at most 750 m, slack window per feeder | Followed | Policy |
| Hanger/slack every 300 m | Followed | Policy; aerial slack storage at intervals is common practice (Preformed Line Products) |
| 9 m poles on both sides of a road crossing | Followed, also on residential/unclassified roads | Road crossings need the road authority's permit (Permen PU 20/PRT/M/2010); a 9 m pole keeps clearance over traffic |
| Avoid footways and motorways | Followed (configurable) | - |
| Template APD folders exact, "Collo" spelling kept, no extra root | Followed; one POP folder as in the compilation, no extra root | Checked after writing (`periksa_template`) |
| Priority: direction, then colo with free tube, then efficient route, then New Infra | Followed | - |

Sources: ITU-T G.652 (08/2024), G.984.2, G.671, G.9940; The Fiber Optic Association, *FTTH design* and *Midspan access*
(thefoa.org); STL *Hardened CONCAT II* (2026); Superior Essex *TG082 FI2 install guide*; OFS *Drop Terminal* practice;
Preformed Line Products *SLACKLOOP*; Peraturan Menteri PU 20/PRT/M/2010.

Known limit: in 34 of 213 designs Tembuku proposes less than half the designer's new cable. In about half of them the
whole proposed route lies on the designer's own route (an earlier tap on the same line); the others use another feeder.
The data cannot show whether the designer had a reason not recorded in the compilation (for example a full cable), so
check such results before budgeting.

## 0a. Version 1.4.3: what the 213 approved designs of four cities showed
Data: compilations of Bengkulu POP 4 (21 designs), Gresik (47), Palembang POP 3 (60) and Serang (85), November 2026.

| Finding | Evidence | Rule in 1.4.3 |
|---|---|---|
| Designers take the lowest free tube of the feeder; they do not reserve T9-T12 for FDTs within 6 km | With the reservation on, 76 of 120 tube groups matched the designer; off, 111 of 127 | `utamakan_aturan_6km` = No by default; a 48-fibre path over 6 km is still rejected |
| Taps are at existing points | Of 186 reuse designs: 59 % at an existing slack/closure (<= 10 m), 15 % at a cable end, 25 % mid-cable | A tap at a slack, closure or cable end is preferred when the new cable is at most 300 m / 15 % longer (600 m from 1.4.4) (`toleransi_slack_antar_m`); not for FDTs right next to the feeder (< 150 m, `slack_min_kabel_m`) |
| An unrecorded tube is not proof of a free tube (PDF 3.2) | - | Every proposed tube is marked *please check* |
| Higher colo ratio is better (PDF 4) | - | Among equal candidates, more new cable on existing poles wins |
| Avoid footways and motorways, configurable (PDF 4) | - | `kelas_jalan_hindari` |
| 9 m poles on both sides of a road crossing (PDF 3.4) | - | `kelas_seberang` includes residential and unclassified roads |

Leave-one-out on the 213 designs:

| Measure | 1.4.2 | 1.4.3 |
|---|---|---|
| Same decision (reuse / new feeder) | 174 (82 %) | 174 (82 %) |
| Same feeder | 134 (63 %) | 140 (66 %) |
| Same F/T folder | 79 (37 %) | 112 (53 %) |
| Route match, median | 42 % | 73 % |
| Total proposed new cable | 523 km | 420 km |

## 0. Version 1.4.0: engineering rules of 11 November 2026 (these override older text below where they differ)
| Rule | How Tembuku applies it |
|---|---|
| The compilation is the only capacity source; the cable inventory is a corridor reference | `produk_feeder` is empty by default: inventory cables are existing pole routes only |
| Folder hierarchy gives the feeder identity; no geometric tracing between folders | Tube use is read from the folders `F<n>_T<k>` per POP and feeder (the "tube book"); overlapping pole lines of other feeders are ignored |
| 144F trunk: T1-T8 for the 96F branch, T9-T12 for 48F branches; one FDT = one tube; lowest free number | `tube_kelompok_96`, `tube_kelompok_48`; the proposed tube becomes the T number and the FDT fields F (SP1) / T (SP1) |
| Up to 6 km POP-to-FDT along the real route: 48F; beyond: 96F | `batas_48f_km`, `utamakan_aturan_6km`: candidates of the fitting group come first; a 48F path over 6 km is rejected |
| Feeder direction must fit the cluster | Direction at the tap (`cos_arah_min`); a new 48F branch from the closure 144 must follow the feeder's own corridor (`koridor_min`, 25 %) |
| Use existing slack; new closure exactly at the slack; 0-5 m strong, 5-10 m review | `tap_slack_m`, `tap_slack_toleransi_m`; an existing closure is reused |
| Hanger every 300 m from the start of the pull; OTB Existing per feeder | `hanger_m`; written to New Hanger and Eksisting OTB |
| OpenStreetMap roads for new infrastructure | Helper lines cost 4x when road data exists (`faktor_bebas`) |

Case study Bengkulu POP 4, FDT BGL1-LAT01-H07 (designer: F2_T9, new 48C 3,706 m from the closure 144): version 1.3.2 chose
an inventory cable and F1_T1 with a 347 m straight line (8 % route match); version 1.4.0 gives F2_T9, a new 48C of 3,117 m
from the closure 144 of feeder 2, 80 % of the route within 20 m of the designer's cable. Leave-one-out on the 19 folders of
the same compilation: equal decisions 12 -> 15, equal F/T folders 4 -> 10, median tap offset 1,545 m -> 154 m. Feeder 4
qualifies equally (shared pole line) and is listed as an equal alternative; the lowest feeder number is used.

### Version 1.4.2: wider test on four cities (12 November 2026)
Leave-one-out on the compilations of Bengkulu POP 4, Gresik, Palembang POP 3 and Serang (213 designs, OpenStreetMap
roads on). Four data-reading faults were fixed first: folder names with several tubes (`F8_T1,T2,T3`), an FDT tapping
its own earlier design, an incomplete tube book CSV, and POP folders without a POP point (now located from the start of
their 144-fibre cables).

| Compilation | Designs | Same decision | Same F/T folder | Median tap offset | Median route match |
|---|---|---|---|---|---|
| Bengkulu POP 4 | 21 | 19 | 10 | 274 m | 61 % |
| Gresik | 47 | 38 | 23 | 880 m | 55 % |
| Palembang POP 3 | 60 | 48 | 25 | 1,230 m | 51 % |
| Serang | 85 | 69 | 21 | 1,388 m | 23 % |
| **Total** | **213** | **174 (82 %)** | **79 (37 %)** | 1,280 m | 42 % |

Open points for the engineering team: (1) 25 designs were reused by the designer where Tembuku proposes a new feeder -
13 because of the route ratio limit, 9 because the tube group of that feeder is recorded as full; (2) a route ratio
limit of 1.35 instead of 1.24 gives 178 equal decisions and 87 equal folders, but turns three of the designers' new
feeders into reuse; the limit stays 1.24 until confirmed; (3) the proposed tube is always the lowest free number,
which designers do not always follow. Results are a first draft for a designer to review.

## 1. Workflow (feeder design procedure, steps 1-6)
| Step | Question | How Tembuku answers it |
|---|---|---|
| 2 | Which data is available? | Each file's role is recognised from its content: cable inventory, feeder design compilation, target FDTs, POP list. The inventory is indexed once for the work area (SQLite R*Tree). |
| 3 | Reuse an existing feeder or build a new one? | Decision: reuse / reuse - check free tubes / new feeder from POP / needs manual design |
| 4 | Which feeder still has free tubes **and** runs toward the FDT? | Free tubes per cable + fibre-path ratio + cable direction at the tap |
| 5 | Draw the route from the feeder to the FDT | Shortest path (Dijkstra) on a graph of existing poles, OpenStreetMap roads and short access links |
| 6 | From the usable point on the existing cable to the FDT | Tap point + new closure + slack, KMZ in the compilation template |

## 2. What the real data showed
Data: feeder design compilations of Bitung (2 POPs, 13 taps) and Tomohon (1 POP, 4 taps) and the cable inventory of
October 2026, week 4.
1. **Only fibre-to-the-home feeders give fibres.** Every "colo cable" in the compilation lies 100 % on another tap's new
   feeder cable and 0 % on cables of other products (fibre-to-the-tower, leased, fibre upgrade). Those other cables are used
   as **existing pole routes** only: the existing-pole sections of the designs follow them for 85-100 % of their length.
2. **One feeder number = one cable system.** Taps T2..Tn always tap the same feeder (the 96-fibre trunk or the 48-fibre
   branch of an earlier tap); the feeder number reflects the order of construction.
3. **"Toward the FDT" = a sensible fibre path.** Ratio (POP-to-tap via the existing feeder + new cable) / new feeder from the
   POP: reused feeders 0.65-1.23, new feeders 1.25 and above.
4. **One FDT = one tube.** The largest FDT splitter is 12 x 1:4 (12 fibres); no 96-fibre cable serves more than 8 FDTs.
5. **Drawing pattern.** New feeder: OTB 144 -> 144-fibre cable 40-93 m -> closure 144 (slack) -> 96-fibre cable.
   Reuse: new closure within 4.3 m of the end of the reused cable (7 of 10 taps), 48-fibre branch, detour 1.01-1.30.
6. **A data anomaly is detected automatically:** Bitung POP 2, folder F1_T9 holds FDT BIT1-PAN07-H01 (which belongs to F1_T1).

## 3. Leave-one-out test (17 taps, with OpenStreetMap roads)
Each tap is hidden together with every later tap of the same feeder and every higher-numbered feeder of the same POP
(the situation when that tap was designed). Tembuku then designs the FDT and the result is compared with the designer's.

| FDT | Compilation folder | Designer | Tembuku | Tembuku folder | Tap point offset | New cable Tembuku / designer | Route match |
|---|---|---|---|---|---|---|---|
| TMH1-KEN01-H02 | F1_T1_2547840495 | New feeder | New feeder | F1_T1 (same) | - | 2639 / 3369 m | 74% |
| TMH1-KEN01-H01 | F1_T2_2547840494 | Reuse | Reuse | F1_T2 (same) | - | 1 / 3 m | 100% |
| TMH1-KTU03-H01 | F1_T3_2547840412 | Reuse | Reuse | F1_T3 (same) | 0 m | 1347 / 1343 m | 100% |
| TMH1-TNG01-H02 | F2_T1-T2_2547840446 | New feeder | New feeder | F2_T1 (same) | - | 2804 / 2811 m | 100% |
| BIT1-WER01-H01 | F1_T1_2547740341 | New feeder | New feeder | F1_T1 (same) | - | 1368 / 1848 m | 49% |
| BIT1-WER01-H02 | F1_T2_2547740340 | Reuse | Reuse | F1_T2 (same) | 47 m | 716 / 701 m | 60% |
| BIT1-STU01-H03 | F2_T1_2547740313 | New feeder | New feeder | F2_T1 (same) | - | 4711 / 4958 m | 68% |
| BIT1-STU01-H02 | F2_T2_2547740315 | Reuse | Reuse | F2_T2 (same) | 0 m | 148 / 145 m | 100% |
| BIT1-STU01-H01 | F2_T3_2547740314 | Reuse | Reuse | F2_T3 (same) | 17 m | 373 / 296 m | 46% |
| BIT1-SAT01-H01 | F2_T4_2547740316 | Reuse | Reuse | F2_T4 (same) | 0 m | 1468 / 1466 m | 100% |
| BIT1-SAT01-H02 | F2_T5_2547740318 | Reuse | Reuse | F2_T5 (same) | 105 m | 2 / 107 m | 100% |
| BIT1-WAT01-H01 | F3_T1_2547740330 | New feeder | New feeder | F3_T1 (same) | - | 2188 / 2328 m | 63% |
| BIT1-PAN07-H01 | F1_T1_2547740271 | New feeder | New feeder | F1_T1 (same) | - | 1871 / 1919 m | 100% |
| BIT1-PAN07-H01 | F1_T9_2547740289 | Reuse | Reuse | F1_T2 (designer: F1_T9) | 1807 m | 2 / 192 m | 0% |
| BIT1-MET01-H01 | F1_T10_2547740290 | Reuse | Reuse | F1_T10 (same) | 1 m | 681 / 676 m | 100% |
| BIT1-MET01-H02 | F1_T11_2547740292 | Reuse | Reuse | F1_T11 (same) | 0 m | 255 / 265 m | 100% |
| BIT1-WUA01-H01 | F2_T1_2547740235 | New feeder | New feeder | F2_T1 (same) | - | 4453 / 4479 m | 100% |

**Result:** same decision **17/17**; same F/T folder 16/17 (the exception is the F1_T9 data anomaly above); median tap
offset 1 m; median route match 100 %. The route ratio limit 1.24 was calibrated on these same designs (in-sample): two
taps (ratios 1.23 and 1.25) sit on either side of it, so decisions within ±0.05 of the limit are marked **borderline**.
Lower route-match values (46-74 %) are taps where the designer followed a different road or pole line to the same FDT; they are listed so they can be reviewed. Recommended further
validation: 20-50 designs from other cities.

The optical-budget values were updated in version 1.1.0 to the maximum values of current ITU-T standards (section 4).
The 17 decisions are identical before and after the change.

## 4. Parameters
| Name | Setting | Default | Kind | Meaning and source |
|---|---|---|---|---|
| `radius_cari_m` | Search radius (m) | 3000 | policy | How far around each FDT to look for an existing feeder. The longest branch in the real designs is 1,466 m. |
| `tube_per_fdt` | Tubes per FDT | 1 | policy, checked on data | Each FDT uses one whole tube (12 fibres). |
| `mode_kapasitas` | Capacity mode | tube | policy | 'tube' = one whole tube per FDT; 'core' = one fibre per 1:4 splitter. |
| `produk_feeder` | Cable products that may be tapped | FTTH | calibrated | Only cables of these product types (comma separated) may give fibres to a new FDT. Other cables are used only as existing pole routes. |
| `core_feeder_min` | Smallest feeder size (fibres) | 48 | policy | Cables with fewer fibres are treated as distribution cables, not feeders. |
| `core_per_tube` | Fibres per tube | 12 | standard | Fibre colour code ANSI/TIA-598-D: 12 fibres per tube. |
| `cadangan_tube` | Reserved tubes | 0 | policy | Tubes to keep free in a feeder after this FDT is added. |
| `pakai_spare_kosong` | Show cables with unknown spare | True | policy | Cables without a spare count are shown as 'not verified' candidates; they are never accepted automatically. |
| `cos_arah_min` | Minimum direction match (cos) | 0.5 | calibrated | How well the feeder must point toward the FDT as seen from the POP: 1 = same direction, 0.5 = within 60 degrees. |
| `jarak_dekat_m` | 'Very close' distance (m) | 300 | calibrated | If the FDT is this close to a cable, direction does not matter. |
| `detour_maks` | Maximum detour | 1.5 | calibrated | New cable length divided by the straight distance from tap to FDT. |
| `cabang_maks_m` | Longest new branch (m) | 2500 | policy | Longest new cable from the tap to the FDT that still makes sense. |
| `rasio_jalur_maks` | Route ratio limit | 1.24 | calibrated | Reuse a feeder only if (POP-to-tap + new cable) is at most this many times a new feeder straight from the POP. Calibrated on 17 real designs. |
| `zona_batas` | Borderline band | 0.05 | policy | Results within this distance of the route ratio limit are marked 'borderline' for a designer to review. |
| `faktor_tiang_eksisting` | Cost factor: existing poles | 0.8 | policy | Relative cost per metre of running along existing poles (lower = preferred). |
| `faktor_akses` | Cost factor: access link | 1.2 | policy | Relative cost of the short straight link from an FDT or POP to the nearest road or cable. |
| `faktor_bebas` | Cost factor: helper line | 1.35 | policy | Relative cost of a straight helper line where no road or cable data exists (must be redrawn by hand). |
| `faktor_garis_bantu` | Helper line length factor | 1.35 | calibrated | Real length of a straight helper line is estimated as this many times the straight distance. |
| `akses_maks_m` | Longest access link (m) | 150 | policy | Maximum distance from an FDT or POP to the nearest road or cable. |
| `sambung_kabel_m` | Cable join distance (m) | 12 | calibrated | Two cables closer than this are treated as the same pole line. Source: GPS.gov, GPS Accuracy (smartphones 4.9 m, open sky). |
| `sambung_jalan_m` | Cable-to-road join (m) | 25 | policy | Poles stand beside the road, within this distance of its centre. |
| `rapat_m` | Tap point spacing (m) | 25 | policy | Distance between candidate tap points along a cable. |
| `faktor_jalur_feeder` | Feeder path factor | 1.5 | calibrated | If the cable path from POP to tap is broken in the data, its length is estimated as this many times the straight distance. |
| `core_cabang` | New branch cable size | 48 | calibrated | Fibre count of the new cable from the tap to the FDT. |
| `core_feeder_baru` | New feeder cable size | 96 | calibrated | Fibre count of a new feeder from the POP. |
| `stub_144_m` | 144-fibre stub length (m) | 75 | calibrated | Length of the 144-fibre cable from the OTB to the first closure. |
| `closure_tap` | Closure at the tap | 96 | calibrated | Closure size placed at the tap point. |
| `slack_m` | Slack per cable end (m) | 10 | standard | Spare cable left at each end for splicing: at least 10 m (ITU-T L.163, 11/2018). |
| `pop_maks_m` | Furthest POP (m) | 20000 | standard | A POP serves an FDT only within this distance. GPON physical reach is 10 or 20 km (ITU-T G.984.1). |
| `fiber_db_km` | Fibre loss (dB/km) | 0.4 | standard | Maximum cabled loss of G.652.D fibre, 0.40 dB/km at 1310-1625 nm (ITU-T G.652, 08/2024). 1310 nm upstream is the worst case. |
| `splitter_fdt_db` | 1:4 splitter loss (dB) | 7.4 | standard | Maximum insertion loss of a 1:4 splitter, 7.4 dB (ITU-T G.9940, 12/2023, Table I.1). |
| `splitter_fat_db` | 1:8 splitter loss (dB) | 10.5 | standard | Maximum insertion loss of a 1:8 splitter, 10.5 dB (ITU-T G.9940, 12/2023, Table I.1). |
| `konektor_n` | Number of connectors | 4 | policy | Connector pairs on the path: OLT, ODF, FDT and FAT. |
| `konektor_db` | Loss per connector (dB) | 0.5 | standard | Maximum loss of a single-fibre connector, 0.5 dB (ITU-T G.671, 11/2025). |
| `splice_db` | Loss per splice (dB) | 0.15 | standard | Typical fusion splice loss, 0.15 dB (ITU-T G.671, note 9). |
| `margin_db` | System margin (dB) | 3.0 | policy | Reserve for repairs, extra splices, ageing and temperature. The standards ask for 'a suitable margin' without a fixed number; 3 dB is a design policy. Source: ITU-T G.652 App. I; G-Sup.39 (no fixed value). |
| `kelas_olt_db` | Optical budget limit (dB) | 28.0 | standard | GPON class B+ allows 13 to 28 dB of loss (ITU-T G.984.2, 08/2019). Use 32 for class C+ optics. |
| `distribusi_km` | Distribution length (km) | 1.0 | policy | Distance from the FDT to the furthest customer, used in the optical budget. |

### Optical budget (worst case, ITU-T G-Sup.39 method)
Total loss = fibre length x 0.40 dB/km (POP to FDT plus 1 km distribution) + 7.4 dB (1:4) + 10.5 dB (1:8) + 4 x 0.5 dB
(connectors) + splices x 0.15 dB + 3 dB margin, compared with 28 dB (GPON class B+). The formula follows ITU-T L.250
(01/2024): "the insertion loss of the optical line is the sum of fibre, splice, branching unit and connector losses".
Maximum (not typical) component values are used because a PON path has few components, where ITU-T G.652 and G-Sup.39
recommend worst-case design. With these values a path of about 9-10 km from the POP to the FDT still fits class B+ (1:4 x 1:8 split); longer paths are
flagged, and class C+ optics (32 dB) can be selected by changing the limit.

## 5. Input check (tolerant of typing mistakes, stops when something required is missing)
| Level | Real examples tested | Behaviour |
|---|---|---|
| Auto-corrected | `Exsisting  Closure`, `colo cable`, `Kolo Kable`, `New Kabel 48Core`, `New Cable 96 c`, `Feder 2`/`Fedder 1`, `F2-T3_..._APD Fedeer KMZ`, code `bit1 stu01 h2`, `12 X 1 : 4`, attribute `Splitter `, swapped latitude/longitude, two versions of the same city's compilation (the newest is used) | read with the correct meaning and listed in the window, the report and `TEMBUKU_PEMERIKSAAN_INPUT_*.txt` |
| Please check | `New Cable 441C` (probably 144C, digits swapped), FDT differs between the FDT folder and the sub-folder, tap without FDT or cable, unknown cable size, FDT in two places, inventory of the wrong island, POP over 20 km away, unclear file role | the run continues; the affected decision is marked |
| Cannot run | file does not exist (similar names are suggested), empty, damaged, no objects, DOCTYPE/ENTITY (XXE), zip-slip, zip bomb, no feeder source, no target FDT | the Run buttons stay locked / Processing stops before the analysis |

Tests: 11 typing mistakes planted in a copy of the Bitung compilation were all corrected and the decisions stayed
identical to the clean data; 7 damaged or unsafe files all stopped with a message; the original data produced no false
corrections and one real anomaly. Basis: data-quality elements of ISO 19157-1:2023 (completeness, logical consistency,
positional and thematic accuracy); bounded tolerance that is always reported (IETF RFC 9413, 2023); fail-fast on wrong
required input; text similarity (Ratcliff/Obershelp, threshold 0.80, unique best match) only against the template
vocabulary, never for numbers.

## 6. References
- ITU-T G.652 (08/2024) Characteristics of a single-mode optical fibre and cable: G.652.D cable attenuation max 0.40 dB/km
  (1310-1625 nm); Appendix I link attenuation formula and margin.
- ITU-T G.984.1 GPON general characteristics: physical reach 10 or 20 km, logical reach 60 km, differential reach 20 km.
- ITU-T G.984.2 (08/2019) GPON PMD layer: class B+ 13-28 dB (Annex A, Table A.2), C+ 17-32 dB.
- ITU-T G.671 (11/2025) Transmission characteristics of optical components: connector max 0.5 dB; typical fusion splice
  0.08-0.15 dB.
- ITU-T G.9940 (12/2023), Table I.1: splitter insertion loss 1:4 typical 6.8 / max 7.4 dB, 1:8 typical 10.2 / max 10.5 dB;
  IEC 61753-031-2.
- ITU-T L.250 (01/2024) Topologies for optical access network: loss = fibre + splice + branching + connector losses.
- ITU-T G-series Supplement 39 (2016) Optical system design and engineering considerations: worst-case and statistical design.
- ITU-T L.163 (11/2018): at least 10 m of extra cable at each end.
- ANSI/TIA-598-D (2014) with Addendum 1 (2018): optical fibre colour code, 12 per tube.
- GPS.gov, *GPS Accuracy*: smartphones typically within a 4.9 m radius under open sky.
- E. W. Dijkstra (1959), *A note on two problems in connexion with graphs*, Numerische Mathematik 1.
- M. Grötschel, C. Raack, A. Werner (2014), *Towards optimizing the deployment of optical access networks*, EURO Journal
  on Computational Optimization 2, 17-53.
- M. Żotkiewicz et al. (2016), *Profitable areas in large-scale FTTH network optimization*, Telecommunication Systems
  (Springer): shortest-path engineering rules for cable routes give results close to full optimisation.
- ISO 19157-1:2023 Geographic information - Data quality; IETF RFC 9413 (2023) Maintaining robust protocols.
- OWASP XML External Entity Prevention and File Upload cheat sheets; OGC KML 2.2.
- OpenStreetMap Foundation, Attribution Guidelines and Licence FAQ (ODbL 1.0); Overpass API usage policy (identify the
  application, cache, pause at least 30 s after HTTP 429/406, heavy commercial use on own or paid servers).
- Copernicus Data Space Ecosystem: Sentinel-2 Level 3 quarterly cloudless mosaics, released within a month after each
  quarter (CDSE news, 16 Mar 2026); the mosaic date is the start of the quarter (CDSE forum); Copernicus data licence
  (free, including commercial use).
- Esri World Imagery metadata service (World_Imagery_Metadata_<year>_r<nn>, newest release = current World Imagery):
  capture dates checked 7 Nov 2026 - Bitung 28 Apr 2025, Jakarta 21 Jul 2025, Makassar 12 Oct 2025, Jayapura 20 May 2025,
  Kupang 12 Aug 2024, Banda Aceh 2 Apr 2024, Pontianak 2 Feb 2024 (Vantor, 0.31-0.5 m).
- OSMF Tile Usage Policy (no offline use or bulk download; identify the application); Esri ArcGIS Location Platform pricing
  (2,000,000 basemap tiles free per month) and Terms of Use; EOX Sentinel-2 cloudless licence (2018+ CC BY-NC-SA);
  Planet NICFI tropical mosaics ended in January 2025 (Planet community, Apr 2025). Imagery older than the design date
  (e.g. the 2016 cloudless mosaic) is deliberately not offered.
- Government Regulation 46/2021 and Minister of Communication and Informatics Regulation 5/2021: shared use of passive
  infrastructure (poles, ducts).
- Law 27/2022 on Personal Data Protection, data minimisation: the cable index stores only the attributes needed for the
  decision.
