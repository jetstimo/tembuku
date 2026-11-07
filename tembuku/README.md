# Tembuku™ – Feeder Tap Designer

![Tembuku](icon.png)

A **tembuku** is the water divider of the Balinese *subak* irrigation system: the place where the main channel is shared out
to branch channels toward the rice fields. Tembuku does the same for FTTH networks. It finds an existing **feeder** that
still has free tubes and runs toward the new FDT, chooses the **tap point**, and draws the **branch to the FDT**, or proposes
a new feeder from the POP when no existing feeder is suitable. The logo shows the four-petal *kawung* motif of Indonesian
batik drawn in light: a feeder passes through the divider and one petal, the new branch, lights up toward the FDT.

Copyright © 2026 **Joseph Edward Timothy Siahaan** · GNU GPL v3 or later with section 7 terms · QGIS 3.22 LTR – 4.x
Tembuku™ and its logo are trademarks of Joseph Edward Timothy Siahaan. Official release key fingerprint:
**92C4-D078-D1FC-1C5B** (the same key as Seranta and Seuntai).

## Use it in three steps
1. Click the **Tembuku** icon (or *Vector → Tembuku → Design Feeders...*).
2. **Choose the folder** with your KMZ files. Tembuku recognises each file from its content and checks it:

   | File | Needed? | Used for |
   |---|---|---|
   | Cable inventory KMZ (existing network) | at least one of these two | feeders that may give free tubes, existing pole routes |
   | Feeder design compilation KMZ (`F1_T1`, ...) | ↑ | on-going feeders, tube use, F/T numbering, POP |
   | Distribution / design-lite KMZ | yes (or click FDTs on the map) | target FDTs, splitters, cluster ID and area |
   | POP / OLT list KMZ | when the POP is not in the compilation | POP locations |
3. Press **Run all FDTs**. You get styled layers in QGIS, a results panel and, in the `TEMBUKU_HASIL_<date>` folder:
   one `TEMBUKU_<FDT>_<DECISION>.kmz` per FDT and `TEMBUKU_SEMUA_*.kmz` in the compilation template (ready to paste),
   `TEMBUKU_LAPORAN_*.html` (interactive, offline), `TEMBUKU_RINGKASAN_*.csv` and `TEMBUKU_PEMERIKSAAN_INPUT_*.txt`.
   The results are written in Indonesian, as used by the design teams.

**Click an FDT on the Map:** after the data is prepared once, click a planned FDT location for an answer in about a second.
**Results Panel:** the reason for each decision and the other candidates (double-click one to use it), *Save KMZ*, *Open report*.
**Accuracy test:** each FDT already designed in the compilation is hidden and designed again; the report, a CSV and a
comparison layer show how Tembuku compares with the designer.
**Processing:** *Tembuku → Design feeders from a data folder* for batch runs, the model builder and scripts.
**Basemaps:** *Vector → Tembuku → Basemaps* adds only current maps with a known date: OpenStreetMap (live), the newest
cloud-free Copernicus Sentinel-2 quarterly mosaic (10 m, your own free account, moves forward each quarter) and detailed
Esri World Imagery (0.3-0.5 m, your own API key) with the capture date at the map centre and a warning when it is older
than 12 months. The HTML report always shows OpenStreetMap road lines (offline) and, if you allow it, the same satellite layers.
**Help:** *Vector → Tembuku → Help and Quick Guide* opens an offline guide with a glossary.

## How it decides (details in [DASAR_KEPUTUSAN.md](DASAR_KEPUTUSAN.md))
1. Only fibre-to-the-home feeders of at least 48 fibres may give fibres; other cables are existing pole routes only.
2. Free tubes: inventory spare fibres ÷ 12; for on-going feeders, tubes minus the FDTs they already serve (1 FDT = 1 tube).
   A missing spare count is shown as *not verified* and is never accepted automatically.
3. Toward the FDT: the fibre path through the tap is at most 1.24 × a new feeder from the POP, and the cable at the tap
   points toward the FDT (cos ≥ 0.5).
4. Route: shortest path over existing poles, OpenStreetMap roads and short access links, existing poles preferred.
5. Optical budget with the maximum values of current ITU-T standards (G.652, G.671, G.9940) against GPON class B+ 28 dB
   (G.984.2); POP within 20 km (G.984.1).
6. Calibrated on 17 approved real designs (Bitung and Tomohon, November 2026): same decision 17/17, same F/T folder 16/17.
   Decisions close to the limit are marked **borderline** for review.

## Files with mistakes
- Corrected automatically and listed: folder names (`Kolo Kable`, `Exsisting Closure`, `Fedder 1`), FDT codes
  (`bit1 - stu01 - h2`), attribute names (`Splitter `), swapped latitude/longitude, several versions of a file (the newest is used).
- The run **stops** with a clear message when a required file is missing, damaged, not a KMZ, or possibly unsafe
  (DOCTYPE/ENTITY, zip-slip, zip bomb).

## Company labels
Tembuku contains no company or brand names. To make the KMZ labels match your company's template, put an
`istilah.json` file in `Documents/Tembuku/` (see the Help page). It stays on your computer and is not part of the plugin.

## Security and data
KMZ files are never extracted to disk; decompressed size and ratio are limited; KML with a DTD is rejected; text from
files is never rendered as HTML. The cable index stores only the geometry and the attributes the decision needs, in your
QGIS profile folder. The only internet use is road data from OpenStreetMap (once per area, cached for 90 days), which can
be switched off or replaced by your own road layer or your own Overpass server. Road data © OpenStreetMap contributors, ODbL 1.0.

## Licence
Code: GPL-3.0-or-later with section 7 terms – see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). Leaflet (BSD-2-Clause);
Plus Jakarta Sans by Tokotype, Jakarta, Indonesia, plus Inter and Poppins fonts (SIL OFL 1.1, see `assets/fonts`).
