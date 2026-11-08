# -*- coding: utf-8 -*-
# Tembuku - parameter keputusan. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Setiap angka membawa dasar & sumbernya. 'KEBIJAKAN' = kebijakan internal yang dapat diubah di bagian Advanced;
'DATA' = dikalibrasi dari desain feeder riil yang disetujui (Bitung & Tomohon, 4-5 Nov 2026); 'STANDAR' = rujukan."""
import copy

BAWAAN = {
    "radius_cari_m": (3000, "KEBIJAKAN", "Radius pencarian feeder di sekitar FDT; cabang terpanjang di data riil 1.466 m"),
    "tube_per_fdt": (1, "KEBIJAKAN+DATA", "1 FDT = 1 tube (12 core). Splitter FDT terbesar di data 12x1x4 = 12 core; "
                     "semua feeder di data <= 8 FDT per kabel 96C (8 tube)"),
    "mode_kapasitas": ("tube", "KEBIJAKAN", "'tube' = tube utuh per FDT; 'core' = 1 core per splitter 1:4 (praktik sebagian operator)"),
    "produk_feeder": ("FTTH", "DATA", "Jenis produk kabel inventaris yang boleh dipakai core-nya (dipisah koma). Data riil: kabel yang ditumpangi 100 % "
                      "berimpit kabel feeder FTTH compile, 0 % kabel produk lain (FTTT, sewa, fiberisasi); kabel lain = jalur tiang"),
    "core_feeder_min": (48, "KEBIJAKAN", "Kabel inventaris < 48 core dianggap kabel distribusi, bukan feeder"),
    "core_per_tube": (12, "STANDAR", "ANSI/TIA-598-D (2014) + Addendum 1 (2018): 12 warna serat per tube; notasi 24/2, "
                      "48/4, 96/8"),
    "cadangan_tube": (0, "KEBIJAKAN", "Tube yang disisakan di feeder setelah alokasi"),
    "pakai_spare_kosong": (True, "KEBIJAKAN", "Kabel inventaris tanpa data core cadangan (spare) tetap ditampilkan sebagai kandidat yang sisa tube-nya belum pasti (peringkat diturunkan), tidak pernah langsung dipakai"),
    "cos_arah_min": (0.5, "DATA", "Feeder dianggap searah bila melenceng paling banyak 60° dari arah POP ke FDT (nilai 0,5 = 60°). Desain nyata: 7 dari 10 melenceng kurang dari 23°"),
    "jarak_dekat_m": (300, "DATA", "Bila FDT sudah sangat dekat dengan kabel (<= 300 m), arah kabel tidak menentukan. Desain nyata: kabel yang melenceng 141° pun dipakai pada jarak 144 m"),
    "detour_maks": (1.5, "DATA", "Panjang kabel baru / jarak lurus tap-FDT; data riil 1,01-1,30"),
    "cabang_maks_m": (2500, "KEBIJAKAN", "Kabel baru titik sambung->FDT terpanjang yang masih masuk akal saat menumpang feeder yang ada"),
    "rasio_jalur_maks": (1.24, "DATA", "Searah ke FDT: panjang serat bila menumpang feeder yang ada (POP->titik sambung->FDT) <= 1,24 x feeder baru "
                         "langsung dari POP. Dikalibrasi pada 17 traksi riil Bitung & Tomohon (menumpang <= 1,23; feeder baru "
                         ">= 1,25); keputusan dalam +-0,05 dari ambang ditandai BATAS untuk ditinjau"),
    "zona_batas": (0.05, "KEBIJAKAN", "Hasil yang selisihnya kurang dari 0,05 dari batas panjang jalur ditandai 'perlu ditinjau'"),
    "faktor_tiang_eksisting": (0.8, "KEBIJAKAN", "Biaya relatif per meter menumpang tiang yang sudah ada"),
    "faktor_akses": (1.2, "KEBIJAKAN", "Sambungan lurus FDT/POP ke jaringan terdekat (<= 150 m)"),
    "faktor_bebas": (1.35, "KEBIJAKAN", "Garis bantu lurus bila tidak ada data jalan (WAJIB digambar ulang)"),
    "faktor_garis_bantu": (1.35, "DATA", "Panjang nyata jalur yang masih berupa garis bantu lurus = 1,35 x lurus "
                           "(7 feeder baru riil: jalur/lurus 1,06-1,65, rata-rata 1,35)"),
    "akses_maks_m": (150, "KEBIJAKAN", "Jarak maksimum FDT/POP ke jalan/kabel terdekat"),
    "sambung_kabel_m": (12, "DATA", "Dua kabel <= 12 m dianggap satu tiang/satu koridor. Dasar: GPS ponsel tipikal "
                        "akurat dalam radius 4,9 m di langit terbuka (GPS.gov, GPS Accuracy); dua titik survei -> ~10 m"),
    "sambung_jalan_m": (25, "KEBIJAKAN", "Kabel ke jalan: tiang di bahu jalan (<= 25 m dari as jalan)"),
    "rapat_m": (25, "KEBIJAKAN", "Kerapatan titik calon tap di sepanjang kabel"),
    "faktor_jalur_feeder": (1.5, "DATA", "Bila jalur kabel POP->tap tidak tersambung di data: panjang = 1,5 x lurus "
                            "(data riil: jalur sebenarnya 1,27-1,65 x garis lurus)"),
    "core_cabang": (48, "DATA", "Kabel cabang titik sambung->FDT: 48C (pola semua desain menumpang di data riil)"),
    "core_feeder_baru": (96, "DATA", "Feeder baru: OTB 144 + 144C ke Closure 144 (slack) lalu 96C (pola T1 di data riil)"),
    "stub_144_m": (75, "DATA", "Panjang 144C dari OTB ke Closure 144: data riil 40-93 m"),
    "closure_tap": ("96", "DATA", "Closure baru di titik sambung: 'New Closure 96' pada 7 dari 10 desain menumpang di data riil"),
    "slack_m": (10, "STANDAR", "ITU-T L.163 (11/2018): sisakan panjang kabel >= 10 m per ujung untuk penyambungan "
                "(L.163 juga menyarankan ~10 % lebih untuk kabel permukaan; panjang rute Tembuku sudah dikalibrasi)"),
    "pop_maks_m": (20000, "STANDAR", "POP dianggap melayani FDT hanya dalam 20 km: jangkauan fisik GPON 10 atau 20 km, "
                   "jangkauan logis 60 km (ITU-T G.984.1)"),
    "fiber_db_km": (0.40, "STANDAR", "Redaman kabel maksimum G.652.D 0,40 dB/km pada 1310-1625 nm (ITU-T G.652 08/2024, "
                    "tabel atribut kabel). 1310 nm = arah upstream GPON, kasus terburuk"),
    "splitter_fdt_db": (7.4, "STANDAR", "Splitter 1:4, insertion loss MAKSIMUM 7,4 dB (tipikal 6,8) termasuk sambungan "
                        "(ITU-T G.9940 12/2023 Tabel I.1; IEC 61753-031-2)"),
    "splitter_fat_db": (10.5, "STANDAR", "Splitter 1:8, insertion loss MAKSIMUM 10,5 dB (tipikal 10,2) termasuk sambungan "
                        "(ITU-T G.9940 12/2023 Tabel I.1; IEC 61753-031-2)"),
    "konektor_n": (4, "KEBIJAKAN", "Jumlah pasangan konektor di jalur: OLT, ODF, FDT, FAT"),
    "konektor_db": (0.5, "STANDAR", "Insertion loss MAKSIMUM konektor serat tunggal 0,5 dB (ITU-T G.671 11/2025 kl. 6.7)"),
    "splice_db": (0.15, "STANDAR", "Sambungan fusi 0,15 dB (nilai tipikal fusi passive-alignment, ITU-T G.671 catatan 9; "
                  "fusi active-alignment tipikal 0,08 dB)"),
    "margin_db": (3.0, "KEBIJAKAN", "Margin untuk perubahan kabel, sambungan tambahan, penuaan dan suhu. ITU-T G.652 "
                  "Lampiran I dan G-Sup.39 mewajibkan margin 'yang sesuai' tanpa angka tetap; 3 dB = kebijakan desain"),
    "kelas_olt_db": (28.0, "STANDAR", "GPON kelas B+: redaman ODN 13-28 dB (ITU-T G.984.2 08/2019, Annex A Tabel A.2). "
                     "Kelas C+ = 17-32 dB"),
    "distribusi_km": (1.0, "KEBIJAKAN", "Panjang distribusi FDT->pelanggan terjauh untuk link budget"),
}


# Kosakata keluaran (KMZ/laporan). Bawaan GENERIK - plugin tidak memuat nama merek/perusahaan. Organisasi dapat
# menimpanya dengan berkas JSON di luar plugin (lihat istilah()), mis. agar label sama persis dengan template internal.
ISTILAH_BAWAAN = {
    "label_tiang_nasional": "Colo Pole (jaringan eksisting)",
    "label_tiang_compile": "Colo Pole FTTH",
    "label_colo_compile": "Colo FTTH (on going)",
    "label_colo_ftth": "Colo FTTH",
    "label_colo_lain": "Colo Cable",
    # aturan label colo kabel nasional: [kolom, teks yang dicari (huruf besar), label] - dicek berurutan
    "aturan_label_colo": [],
    # petunjuk tambahan nama berkas inventaris kabel nasional (peran tetap dikenali dari atribut)
    "petunjuk_berkas_nasional": ["ALL CABLE", "CABLE INVENTORY", "INVENTARIS KABEL"],
    # nama atribut yang menandai titik POP/OLT di KMZ POP organisasi
    "atribut_pop": [],
}


def istilah(paths=()):
    """Gabungkan ISTILAH_BAWAAN dengan JSON organisasi (berkas pertama yang ada menang, kunci tak dikenal diabaikan)."""
    import json
    import os
    out = dict(ISTILAH_BAWAAN)
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, ValueError) as e:
                d = None
                out["_galat"] = "%s: %s" % (p, e)
            if not isinstance(d, dict):
                out.setdefault("_galat", "%s: isi harus berupa objek JSON {...}" % p)
                continue
            for k, v in d.items():
                if k in out and isinstance(v, type(out[k])):
                    out[k] = v
            out["_sumber"] = p
            break
    return out


def baru(ubah=None):
    p = {k: v[0] for k, v in BAWAAN.items()}
    for k, v in (ubah or {}).items():
        if k in p:
            p[k] = type(p[k])(v) if not isinstance(p[k], bool) else bool(v)
    return p


def dasar():
    return copy.deepcopy(BAWAAN)


# Plain-English name and explanation of every parameter, for the user interface (the report keeps the Indonesian basis).
# Label parameter dalam bahasa Indonesia untuk laporan (pengganti nama kunci internal)
LABEL_ID = {
    "radius_cari_m": "Radius pencarian feeder (m)", "tube_per_fdt": "Tube per FDT",
    "mode_kapasitas": "Cara hitung kapasitas", "produk_feeder": "Jenis produk kabel yang boleh dipakai",
    "core_feeder_min": "Ukuran feeder terkecil (core)", "core_per_tube": "Core per tube",
    "cadangan_tube": "Tube cadangan yang disisakan", "pakai_spare_kosong": "Tampilkan kabel tanpa data cadangan",
    "cos_arah_min": "Arah feeder minimum (0,5 = boleh melenceng 60°)", "jarak_dekat_m": "Jarak 'sangat dekat' ke kabel (m)",
    "detour_maks": "Batas memutar kabel baru (x jarak lurus)", "cabang_maks_m": "Kabel baru terpanjang (m)",
    "rasio_jalur_maks": "Batas panjang jalur lewat feeder (x feeder baru)", "zona_batas": "Lebar zona 'perlu ditinjau'",
    "faktor_tiang_eksisting": "Bobot biaya: menumpang tiang yang ada", "faktor_akses": "Bobot biaya: sambungan ke jaringan",
    "faktor_bebas": "Bobot biaya: garis bantu", "faktor_garis_bantu": "Perkiraan panjang nyata garis bantu (x)",
    "akses_maks_m": "Jarak terjauh ke jalan atau kabel (m)", "sambung_kabel_m": "Dua kabel dianggap satu tiang dalam (m)",
    "sambung_jalan_m": "Jarak tiang ke jalan (m)", "rapat_m": "Jarak antar calon titik sambung (m)",
    "faktor_jalur_feeder": "Perkiraan panjang feeder bila jalurnya tidak tersambung di data (x)",
    "core_cabang": "Ukuran kabel cabang ke FDT (core)", "core_feeder_baru": "Ukuran feeder baru (core)",
    "stub_144_m": "Panjang kabel 144C dari OTB (m)", "closure_tap": "Ukuran closure di titik sambung (core)",
    "slack_m": "Slack per ujung kabel (m)", "pop_maks_m": "Jarak POP terjauh (m)",
    "fiber_db_km": "Redaman kabel (dB/km)", "splitter_fdt_db": "Redaman splitter 1:4 (dB)",
    "splitter_fat_db": "Redaman splitter 1:8 (dB)", "konektor_n": "Jumlah konektor", "konektor_db": "Redaman per konektor (dB)",
    "splice_db": "Redaman per sambungan fusi (dB)", "margin_db": "Margin cadangan (dB)",
    "kelas_olt_db": "Batas redaman perangkat GPON (dB)", "distribusi_km": "Panjang distribusi ke pelanggan (km)",
}
JENIS_ID = {"STANDAR": "Standar", "DATA": "Dari desain nyata", "KEBIJAKAN": "Kebijakan", "KEBIJAKAN+DATA": "Kebijakan dan desain nyata"}

PENJELASAN_EN = {
    "radius_cari_m": ("Search radius (m)", "How far around each FDT to look for an existing feeder. The longest branch "
                      "in the real designs is 1,466 m."),
    "tube_per_fdt": ("Tubes per FDT", "Each FDT uses one whole tube (12 fibres)."),
    "mode_kapasitas": ("Capacity mode", "'tube' = one whole tube per FDT; 'core' = one fibre per 1:4 splitter."),
    "produk_feeder": ("Cable products that may be tapped", "Only cables of these product types (comma separated) may "
                      "give fibres to a new FDT. Other cables are used only as existing pole routes."),
    "core_feeder_min": ("Smallest feeder size (fibres)", "Cables with fewer fibres are treated as distribution cables, "
                        "not feeders."),
    "core_per_tube": ("Fibres per tube", "Fibre colour code ANSI/TIA-598-D: 12 fibres per tube."),
    "cadangan_tube": ("Reserved tubes", "Tubes to keep free in a feeder after this FDT is added."),
    "pakai_spare_kosong": ("Show cables with unknown spare", "Cables without a spare count are shown as 'not verified' "
                           "candidates; they are never accepted automatically."),
    "cos_arah_min": ("Direction limit (cosine of the angle)", "How closely the feeder must point toward the FDT, seen "
                     "from the POP: 1 = exactly toward it, 0.5 = up to 60 degrees off (default)."),
    "jarak_dekat_m": ("'Very close' distance (m)", "If the FDT is this close to a cable, direction does not matter."),
    "detour_maks": ("Maximum detour", "New cable length divided by the straight distance from tap to FDT."),
    "cabang_maks_m": ("Longest new branch (m)", "Longest new cable from the tap to the FDT that still makes sense."),
    "rasio_jalur_maks": ("Longest route through a feeder (x a new feeder)", "Reuse a feeder only if (POP-to-tap + new cable) is at most this many times "
                         "a new feeder straight from the POP. Calibrated on 17 real designs."),
    "zona_batas": ("'Please review' band", "Results this close to the route limit above are marked 'please review' so "
                   "a designer checks both options."),
    "faktor_tiang_eksisting": ("Cost factor: existing poles", "Relative cost per metre of running along existing "
                               "poles (lower = preferred)."),
    "faktor_akses": ("Cost factor: access link", "Relative cost of the short straight link from an FDT or POP to the "
                     "nearest road or cable."),
    "faktor_bebas": ("Cost factor: helper line", "Relative cost of a straight helper line where no road or cable data "
                     "exists (must be redrawn by hand)."),
    "faktor_garis_bantu": ("Helper line length factor", "Real length of a straight helper line is estimated as this "
                           "many times the straight distance."),
    "akses_maks_m": ("Longest access link (m)", "Maximum distance from an FDT or POP to the nearest road or cable."),
    "sambung_kabel_m": ("Cable join distance (m)", "Two cables closer than this are treated as the same pole line."),
    "sambung_jalan_m": ("Cable-to-road join (m)", "Poles stand beside the road, within this distance of its centre."),
    "rapat_m": ("Tap point spacing (m)", "Distance between candidate tap points along a cable."),
    "faktor_jalur_feeder": ("Feeder path factor", "If the cable path from POP to tap is broken in the data, its length "
                            "is estimated as this many times the straight distance."),
    "core_cabang": ("New branch cable size", "Fibre count of the new cable from the tap to the FDT."),
    "core_feeder_baru": ("New feeder cable size", "Fibre count of a new feeder from the POP."),
    "stub_144_m": ("144-fibre stub length (m)", "Length of the 144-fibre cable from the OTB to the first closure."),
    "closure_tap": ("Closure at the tap", "Closure size placed at the tap point."),
    "slack_m": ("Slack per cable end (m)", "Spare cable left at each end for splicing: at least 10 m (ITU-T L.163, 11/2018)."),
    "pop_maks_m": ("Furthest POP (m)", "A POP serves an FDT only within this distance. GPON physical reach is 10 or "
                   "20 km (ITU-T G.984.1)."),
    "fiber_db_km": ("Fibre loss (dB/km)", "Maximum cabled loss of G.652.D fibre, 0.40 dB/km at 1310-1625 nm "
                    "(ITU-T G.652, 08/2024). 1310 nm upstream is the worst case."),
    "splitter_fdt_db": ("1:4 splitter loss (dB)", "Maximum insertion loss of a 1:4 splitter, 7.4 dB (ITU-T G.9940, "
                        "12/2023, Table I.1)."),
    "splitter_fat_db": ("1:8 splitter loss (dB)", "Maximum insertion loss of a 1:8 splitter, 10.5 dB (ITU-T G.9940, "
                        "12/2023, Table I.1)."),
    "konektor_n": ("Number of connectors", "Connector pairs on the path: OLT, ODF, FDT and FAT."),
    "konektor_db": ("Loss per connector (dB)", "Maximum loss of a single-fibre connector, 0.5 dB (ITU-T G.671, 11/2025)."),
    "splice_db": ("Loss per splice (dB)", "Typical fusion splice loss, 0.15 dB (ITU-T G.671, note 9)."),
    "margin_db": ("System margin (dB)", "Reserve for repairs, extra splices, ageing and temperature. The standards ask "
                  "for 'a suitable margin' without a fixed number; 3 dB is a design policy."),
    "kelas_olt_db": ("Optical budget limit (dB)", "GPON class B+ allows 13 to 28 dB of loss (ITU-T G.984.2, 08/2019). "
                     "Use 32 for class C+ optics."),
    "distribusi_km": ("Distribution length (km)", "Distance from the FDT to the furthest customer, used in the optical "
                      "budget."),
}
