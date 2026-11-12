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
2. **Choose the folder** with your data. Tembuku looks inside every file and recognises what it is from its content
   (object shapes, data columns, folder layout), not from its name or extension, and says why in the *Why* column.
   Formats: KMZ/KML (even with the wrong extension), ZIP bundles, GeoJSON, CSV/TXT/Excel with coordinates, and through
   QGIS also Shapefile, GeoPackage, GML, TAB, FlatGeobuf and GPX. Indonesian and English column names are understood.

   | File | Needed? | Used for |
   |---|---|---|
   | Cable inventory KMZ (existing network) | at least one of these two | feeders that may give free tubes, existing pole routes |
   | Feeder design compilation KMZ (`F1_T1`, ...) | ↑ | on-going feeders, tube use, F/T numbering, POP |
   | KMZ with the FDT points to design (distribution or design KMZ) | yes (or click FDTs on the map) | target FDTs, splitters, cluster ID and area |
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

## New in 1.4.4 (engineering rules checked against sources and data)
Every rule of the 11 Nov 2026 engineering document was checked against credible technical sources (ITU-T, the Fiber
Optic Association, cable and closure manufacturers' installation guides, Indonesian road-space regulation) and against
213 approved designs in four cities. See *DASAR_KEPUTUSAN.md*, section 0b, for the full table.
- **Tube group by distance (6 km) is not applied literally by default.** Applied literally: 36 % of F/T folders match
  and 563 km of new cable; off: 54 % and 425 km (the designers drew 495 km). Optical loss depends on route length, not
  fibre count. A 48-fibre branch over 6 km is still rejected.
- **Taps at existing slack come first when the new cable is at most 600 m (or 15 %) longer**, not at any cost. Mid-span
  closures can be built and are marked *please check*.
- **KMZ closer to the APD template**: tap at the exact slack coordinate, Colo Pole colour by cable size, template icons
  (Closure 96 for 96-144, hanger, OLT), 9 m crossing poles, no extra New Infra folder, a plain-language summary on each
  new cable, POP folder without ".kmz", and a team icon folder next to the data is found automatically.
- **Fix for feeder tube record tables**: the tube of an FDT that is designed again is freed in the record as well (Palembang
  POP 3 with its record: same F/T folder 2 -> 31 of 60). Faster nearest-point and corridor checks, same results.

## New in 1.4.3 (checked on 213 approved designs in four cities)
- **Lowest free tube of the feeder**, as the designers do. Reserving T9-T12 for FDTs within 6 km is now off by default
  (switch it on under *Advanced*); the 6 km limit for 48-fibre cables still applies.
- **Taps at an existing slack, closure or cable end come first** when the new cable is at most 300 m (or 15 %) longer.
  Any other tap, and any tube number not yet recorded in the compilation, is marked *please check*.
- **More cable on existing poles** wins among equal candidates; a closure proposed for one FDT can be shared by the next.
- **Plain-language results**: each FDT starts with one sentence saying what to build, the F/T folder, the new cable
  and what a new feeder would need instead.
- Against 1.4.2 on the 213 designs: same decision 82 % (unchanged), same F/T folder 37 % -> 53 %, route match median
  42 % -> 73 %, total proposed new cable 523 km -> 420 km.

## New in 1.4.2 (data-reading fixes of 12 Nov 2026)
Found by running four city compilations (213 designs). The design rules and the route limit of 1.24 are unchanged.
- **Folder names with several tubes are read.** `F8_T1,T2,T3_…`, `F3_T3_T4_T5_…`, `F1_T10,11_…` and folders without a
  cluster ID (`F1_T1_APD Feeder_…`) now count in the tube book; before, 62 of 342 folders were skipped.
- **An FDT that is already in the compilation is designed again fairly.** Its earlier design is hidden while it is
  analysed, so it no longer taps its own cable with 0 m of new cable.
- **The tube book CSV lists every POP and feeder,** also when the POP folder and the POP point have different names.
- **A POP folder without a POP/OLT point** gets its location from the start of its 144-fibre feeder cables and is listed
  under "please check"; add the point to the OLT folder to remove the note.
- Accuracy test on the four compilations: same decision 76 % → 82 %, same F/T folder 25 % → 37 %.

## New in 1.4.0 (engineering rules of 11 Nov 2026)
- **Tube book per feeder, from the compilation folders.** One feeder = one 144-fibre trunk = 12 tubes. The T number of a
  folder `F<n>_T<k>` is the tube used. T1-T8 go through the 96-fibre cable, T9-T12 through 48-fibre branches from the
  closure 144 at the POP. Tembuku proposes the lowest free tube of the group that fits the 6 km rule.
- **The cable inventory is a pole-route reference only**; it no longer gives tubes (changeable under *Advanced*).
- **New 48-fibre branch from the closure 144** of an existing feeder is a candidate when its route follows that feeder's
  own corridor; a new feeder is proposed only when no existing feeder qualifies.
- **Tap at an existing slack or closure** of the feeder where possible; hanger/slack points every 300 m; routes follow roads.
- The steps below still apply; where they differ, this section wins.

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
KMZ files are never extracted to disk (ZIP bundles only into Tembuku's cache, with limits); decompressed size and ratio are limited; KML with a DTD is rejected; text from
files is never rendered as HTML. The cable index stores only the geometry and the attributes the decision needs, in your
QGIS profile folder. The only internet use is road data from OpenStreetMap (once per area, cached for 90 days), which can
be switched off or replaced by your own road layer or your own Overpass server. Road data © OpenStreetMap contributors, ODbL 1.0.

## Licence
Code: GPL-3.0-or-later with section 7 terms – see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). Leaflet (BSD-2-Clause);
Plus Jakarta Sans by Tokotype, Jakarta, Indonesia, plus Inter and Poppins fonts (SIL OFL 1.1, see `assets/fonts`).
