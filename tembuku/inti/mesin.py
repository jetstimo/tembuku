# -*- coding: utf-8 -*-
# Tembuku - mesin keputusan feeder (slide 1-6 "Feeder Design APD Ruas Jalan" + aturan engineering 11-11-2026).
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Untuk setiap FDT target:

 1. Kumpulkan kabel di sekitar FDT: kabel baru di Compile APD Feeder (sumber kapasitas tube) + koridor tiang: garis
    Colo Pole / New Infra compile dan kabel inventaris nasional (hanya jalur tiang, bukan sumber tube - aturan 11-11-2026).
 2. Kapasitas (buku tube per feeder, dari HIERARKI FOLDER compile, bukan dari penelusuran geometri):
      satu feeder = satu kabel induk 144F = 12 tube; nomor T pada folder F<n>_T<k> = nomor tube yang dipakai FDT itu;
      T1-T8 dicabangkan lewat kabel 96F, T9-T12 lewat kabel 48F dari closure 144 di POP; satu FDT = satu tube;
      tube yang diusulkan = nomor terkecil yang masih kosong di kelompoknya. Kapasitas fisik kabel yang disambung
      (96C = 8 tube, 48C = 4 tube) tetap dihormati.
 3. Graf gabungan: kabel & koridor eksisting (tiang eksisting, faktor 0,8) + jalan OSM (faktor 1,0-1,5) + sambungan
    antar-kabel (<= 12 m) & kabel-jalan (<= 25 m) + akses FDT (<= 150 m). Dijkstra SEKALI dari FDT memberi biaya kabel
    baru ke SETIAP calon titik sambung (Dijkstra 1959).
 4. Dijkstra kedua dari POP hanya di atas kabel: membuktikan kabel yang dipetik memang tersambung ke POP, memberi
    panjang colo (link budget) dan ARAH kabel di titik sambung (slide 4 "searah untuk FDT").
 5. Titik sambung per kabel = titik dengan kabel baru termurah yang searah; bila ada slack/closure existing feeder itu
    dalam 10 m (atau tak jauh lebih mahal), titik sambung dipindah ke sana (closure baru tepat di koordinat slack).
 6. Keputusan (prioritas 11-11-2026): kesesuaian arah feeder -> colo feeder yang ada dengan tube kosong terbukti ->
    jalur aktual paling efisien -> feeder baru dari POP bila tidak ada feeder yang memenuhi syarat.
 7. Jalur digambar dari titik sambung ke FDT, dipecah per jenis infrastruktur: tiang eksisting (inventaris), tiang
    FTTH on-going (compile), New Infra (jalan / tiang baru)."""
import math
import re

from . import geo, osm, profil
from .teks import T, gabung, m, km, kali, db
from .graf import Graf, INF


# ----------------------------------------------------------------------------- data
class Data(object):
    """Semua sumber yang sudah dibaca. indeks: daftar IndeksKabel; compiles: hasil sumber.baca_compile."""

    def __init__(self, indeks=(), compiles=(), pops=(), jalan=None):
        self.indeks = list(indeks)
        self.compiles = list(compiles)
        self.pops = list(pops)
        for c in self.compiles:
            for p in c["pops"]:
                if not any(_sama_pop(p, q) for q in self.pops):
                    self.pops.append(p)
        self.jalan = jalan            # callable(bbox) -> [ {kelas, ll} ] atau None
        self.kecuali = set()          # kunci traksi yang diabaikan (uji / desain ulang)
        self.audit = []               # [(nama POP, feeder, {T terpakai})] dari tabel catatan tube (opsional)
        self._ledger = {}
        self._pop_folder = {}         # (berkas compile, folder POP) -> nama titik POP
        self.pop_dugaan = []          # [(nama, jumlah kabel 144C)] POP yang lokasinya diambil dari pangkal kabel 144C
        self._kenali_pop_folder()

    # ------------------------------------------------------------------ identitas POP & traksi
    def _kenali_pop_folder(self):
        """Pasangkan tiap folder POP compile dengan titik POP-nya lewat LOKASI: semua feeder sebuah POP berpangkal di
        OTB yang sama, jadi median titik awal kabel 144C folder itu = lokasi POP. Titik POP yang ada dalam 150 m dipakai
        (walau namanya lain, mis. folder 'Serang POP 1' = titik 'POP SERANG KALIGANDU'); bila tidak ada titik POP di
        sana, POP dibuat di lokasi itu dengan nama foldernya, supaya FDT-nya tidak dihitung dari POP kota sebelah."""
        from . import sumber
        for c in self.compiles:
            awal = {}
            for k in c.get("kabel", ()):
                if k.get("jenis") == "NEW_CABLE" and k.get("core") == 144 and k.get("pop_folder") and len(k["ll"]) > 1:
                    awal.setdefault(k["pop_folder"], []).append(k["ll"][0])
            for popf, ts in awal.items():
                xs, ys = sorted(p[0] for p in ts), sorted(p[1] for p in ts)
                o = (xs[len(xs) // 2], ys[len(ys) // 2])
                if sum(1 for p in ts if geo.haversine(p, o) <= JARAK_POP_M) * 2 < len(ts):
                    continue                    # pangkal kabel 144C berpencar: lokasi POP tidak bisa disimpulkan
                kp = sumber.kunci_pop(popf)
                dekat = sorted((p for p in self.pops if geo.haversine(p["ll"], o) <= JARAK_POP_M),
                               key=lambda p: (not (kp and (kp == sumber.kunci_pop(p["nama"]) or
                                                           kp in sumber.kunci_pop(p["nama"]))),
                                              geo.haversine(p["ll"], o)))
                if dekat:
                    self._pop_folder[(c.get("berkas"), popf)] = dekat[0]["nama"]
                    continue
                nama = sumber.RX_EKST_PETA.sub("", str(popf)).strip()
                self.pops.append({"nama": nama, "ll": o, "attrs": {}, "dari_feeder": True})
                self._pop_folder[(c.get("berkas"), popf)] = nama
                self.pop_dugaan.append((nama, len(ts)))

    def nama_pop(self, popf, c=None):
        """Nama POP sebuah folder POP compile ('BENGKULU POP 4' -> titik OLT 'Bengkulu POP 4'); compile tanpa folder
        POP (Tomohon) -> satu-satunya POP/OLT di compile itu."""
        from . import sumber
        if self._pop_folder:
            if c is not None and (c.get("berkas"), popf) in self._pop_folder:
                return self._pop_folder[(c.get("berkas"), popf)]
            if c is None or c.get("berkas") == "_TEMBUKU_BATCH":
                for (_b, pf), nm in self._pop_folder.items():
                    if pf == popf:
                        return nm
        kp = sumber.kunci_pop(popf)
        if kp:
            for p in self.pops:
                kn = sumber.kunci_pop(p["nama"])
                if kp == kn or kn.endswith(kp) or kp in kn:
                    return p["nama"]
            # folder POP bernama lain dari titik POP-nya ('Palembang POP 3' vs titik 'POP PALEMBANG KEBUN BUNGA'):
            # compile dengan SATU folder POP dan SATU titik POP -> itu POP yang sama (buku tube tidak terpecah)
            # (usulan proses ini disimpan di compile bayangan _TEMBUKU_BATCH: cari compile asli pemilik folder POP itu)
            for x in ([c] if c is not None and c.get("berkas") != "_TEMBUKU_BATCH" else self.compiles):
                if x.get("berkas") == "_TEMBUKU_BATCH":
                    continue
                fp = x.get("_folder_pop")
                if fp is None:
                    fp = {k[1] for k in x.get("traksi", {}) if k[1]}
                    x["_folder_pop"] = fp
                if len(fp) == 1 and popf in fp and len(x.get("pops") or []) == 1:
                    return x["pops"][0]["nama"]
            return sumber.RX_EKST_PETA.sub("", str(popf)).strip()
        if c is not None and len(c.get("pops") or []) == 1:
            return c["pops"][0]["nama"]
        if len(self.pops) == 1:
            return self.pops[0]["nama"]
        return "?" + (c.get("berkas", "") if c is not None else "")

    def _traksi(self, c, kode):
        peta = c.get("_peta_traksi")
        if peta is None:
            peta = {t["kode"]: t for t in c["traksi"].values()}
            c["_peta_traksi"] = peta
        return peta.get(kode)

    def kabel_compile(self, bb):
        out = []
        for c in self.compiles:
            for k in c["kabel"]:
                if k["jenis"] != "NEW_CABLE" or k["traksi"] in self.kecuali:
                    continue
                if not _bb_kena(k["ll"], bb):
                    continue
                d = dict(k)
                t = self._traksi(c, k["traksi"]) or {}
                inf = t.get("info") or {}
                d["grup"] = (c["berkas"], k["pop_folder"], k["feeder"])
                fdt = set(f["kode"].upper() for f in t.get("fdt", ()))
                fdt |= set(t.get("_tambahan") or ())
                d["fdt_di_feeder"] = sorted(fdt)
                d["tube_traksi"] = set(inf.get("tube") or ())
                d["area"] = str(inf.get("area") or "").strip()      # nama cluster traksi (keterangan COLO CABLE)
                # mis. "Feeder 6" dipakai juga untuk keterangan saran dan penjelasan
                d["pop_nama"] = self.nama_pop(k["pop_folder"], c)
                out.append(d)
        return out

    def koridor_compile(self, bb):
        """Garis Colo Pole / New Infra / Colo Cable compile: jalur tiang yang sudah ada (bukan sumber tube)."""
        out = []
        for c in self.compiles:
            for k in c["kabel"]:
                if k["jenis"] == "NEW_CABLE" or k["traksi"] in self.kecuali or not _bb_kena(k["ll"], bb):
                    continue
                d = dict(k)
                d["id"] = "K" + k["id"]
                d["jenis_asli"] = k["jenis"]
                d["koridor"] = True
                d["pop_nama"] = self.nama_pop(k["pop_folder"], c)
                out.append(d)
        return out

    def ledger(self, pop_nama):
        """Buku tube per feeder di satu POP: {nomor feeder: {tube: {T terpakai}, fdt: {kode}, traksi: {kode}}}.
        Sumber: hierarki folder compile (nomor T), tabel catatan tube (opsional) dan hasil batch sebelumnya."""
        from . import sumber
        kp = sumber.kunci_pop(pop_nama)
        key = (kp, frozenset(self.kecuali))
        if key in self._ledger:
            return self._ledger[key]
        out = {}
        lepas = {}      # tube milik desain yang sedang disembunyikan (uji akurasi / dirancang ulang): {feeder: {T}}
        for c in self.compiles:
            for (_b, popf, _f, kode), t in c["traksi"].items():
                inf = t.get("info") or {}
                fe = _angka_feeder(inf.get("feeder") or t.get("feeder"))
                if fe is None or sumber.kunci_pop(self.nama_pop(popf, c)) != kp:
                    continue
                if kode in self.kecuali:
                    lepas.setdefault(fe, set()).update(inf.get("tube") or ())
                    continue
                e = out.setdefault(fe, {"tube": set(), "fdt": set(), "traksi": set()})
                e["tube"] |= set(inf.get("tube") or ())
                e["fdt"] |= set(f["kode"].upper() for f in t["fdt"])
                e["fdt"] |= set(t.get("_tambahan") or ())
                e["traksi"].add(kode)
        pop_unik = set(sumber.kunci_pop(p["nama"]) for p in self.pops)
        for apop, afdr, at in self.audit:
            ap = sumber.kunci_pop(apop)
            if not ap or ap == kp or ap in kp or kp in ap or len(pop_unik) <= 1:
                # tabel catatan tube juga mencatat tube desain yang sedang disembunyikan: tube itu dilepas juga,
                # kecuali masih dipakai traksi lain yang tidak disembunyikan (sudah masuk lewat compile di atas)
                e = out.setdefault(int(afdr), {"tube": set(), "fdt": set(), "traksi": set()})
                e["tube"] |= set(at) - (lepas.get(int(afdr), set()) - e["tube"])
        self._ledger[key] = out
        return out

    def titik_feeder(self, pop_nama, feeder, bb=None):
        """Closure & slack existing milik feeder ini (semua traksi di feeder yang sama, hierarki folder)."""
        from . import sumber
        kp = sumber.kunci_pop(pop_nama)
        fe = _angka_feeder(feeder)
        out = []
        for c in self.compiles:
            for (_b, popf, _f, kode), t in c["traksi"].items():
                if kode in self.kecuali:
                    continue
                inf = t.get("info") or {}
                if _angka_feeder(inf.get("feeder") or t.get("feeder")) != fe:
                    continue
                if sumber.kunci_pop(self.nama_pop(popf, c)) != kp:
                    continue
                for cl in t.get("closure", ()):
                    if bb is None or _bb_kena([cl["ll"]], bb):
                        out.append({"ll": cl["ll"], "nama": cl["nama"], "jenis": "closure",
                                    "eksisting": cl.get("eksisting", False), "core": cl.get("core"), "traksi": kode})
                for sl in t.get("slack", ()):
                    if bb is None or _bb_kena([sl["ll"]], bb):
                        out.append({"ll": sl["ll"], "nama": sl["nama"], "jenis": "slack",
                                    "eksisting": sl.get("eksisting", False), "core": None, "traksi": kode})
        return out

    def kabel_nasional(self, bb):
        out = []
        for ix in self.indeks:
            out.extend(ix.di_bbox(bb))
        return out


def _angka_feeder(x):
    m_ = re.search(r"\d+", str(x or ""))
    return int(m_.group(0)) if m_ else None


def _sama_pop(a, b):
    return geo.haversine(a["ll"], b["ll"]) < 30


def _bb_kena(ll, bb):
    xs = [c[0] for c in ll]
    ys = [c[1] for c in ll]
    return max(xs) >= bb[0] and min(xs) <= bb[2] and max(ys) >= bb[1] and min(ys) <= bb[3]


def _teks_tube(ts):
    ts = sorted(set(int(x) for x in ts))
    if not ts:
        return "-"
    # rentang berurutan ditulis ringkas: T9-T12
    out, i = [], 0
    while i < len(ts):
        j = i
        while j + 1 < len(ts) and ts[j + 1] == ts[j] + 1:
            j += 1
        out.append("T%d" % ts[i] if i == j else "T%d-T%d" % (ts[i], ts[j]))
        i = j + 1
    return ", ".join(out)


# ----------------------------------------------------------------------------- kapasitas
def kelompok_tube(prm):
    g96 = profil.rentang_tube(prm["tube_kelompok_96"], range(1, 9))
    g48 = profil.rentang_tube(prm["tube_kelompok_48"], range(9, 13))
    return g96, g48


def _kelompok_kabel(k, prm):
    """Kelompok tube kabel induk yang dilewati bila FDT disambung ke kabel compile ini.
    144C (closure 144 di POP) -> cabang 48F baru (T9-T12); 96C -> T1-T8; 48C -> kelompok traksi pemiliknya."""
    g96, g48 = kelompok_tube(prm)
    core = k.get("core") or 0
    tubes = set(k.get("tube_traksi") or ())
    if core >= 144:
        return "48F", g48
    if core == 96:
        return "96F", g96
    if tubes and tubes <= g48:
        return "48F", g48
    if tubes and tubes <= g96:
        return "96F", g96
    return ("48F", g48) if core <= 48 and tubes and min(tubes) in g48 else ("96F", g96)


def kapasitas(k, prm, butuh_core, data=None):
    """-> (status, tube_bebas, teks, info). status: LOLOS / PENUH / BELUM_TERVERIFIKASI / BUKAN_FEEDER.
    info: kelompok, bebas (daftar nomor tube kosong), tube (usulan), terpakai, feeder, sisa_kabel, bebas_lain."""
    cpt = prm["core_per_tube"]
    # tube yang dibutuhkan: 1 FDT = tube_per_fdt; FDT pertama dari proyek berisi n FDT butuh tempat untuk n FDT
    butuh = max(int(prm["tube_per_fdt"]), int(prm.get("_butuh_tube") or 0))
    info = {"kelompok": None, "bebas": [], "tube": None, "terpakai": [], "feeder": _angka_feeder(k.get("feeder")),
            "sisa_kabel": None, "bebas_lain": [], "kelompok_lain": None, "butuh": butuh}
    if k["sumber"] == "NASIONAL":
        boleh = [x.strip().upper() for x in str(prm["produk_feeder"]).split(",") if x.strip()]
        if not boleh or (k.get("product") or "").upper() not in boleh:
            return "BUKAN_FEEDER", None, T("%s %s: hanya jalur tiang (colo pole), bukan sumber tube (kapasitas hanya "
                                           "dari compile desain feeder)",
                                           "%s %s: pole route only (colo pole), not a tube source (capacity comes from "
                                           "the feeder design compilation only)") % (
                k.get("product") or "-", k.get("owner") or ""), info
        if k.get("core") and k["core"] < prm["core_feeder_min"]:
            return "BUKAN_FEEDER", None, T("%d core: terlalu kecil untuk feeder (minimal %d core), dianggap kabel "
                                           "distribusi", "%d fibres: too small for a feeder (at least %d), treated as a "
                                           "distribution cable") % (k["core"], prm["core_feeder_min"]), info
        if k.get("spare") is None:
            return "BELUM_TERVERIFIKASI", None, T("jumlah core cadangan (spare) tidak tercatat di inventaris kabel",
                                                  "spare fibre count not recorded in the cable inventory"), info
        c = k.get("cpt") or cpt
        if prm["mode_kapasitas"] == "core":
            ok = k["spare"] >= butuh_core
            return ("LOLOS" if ok else "PENUH"), int(k["spare"] // c), T("cadangan %d core (butuh %d core)",
                                                                       "%d spare fibres (%d needed)") % (
                k["spare"], butuh_core), info
        bebas = int(k["spare"] // c) - prm["cadangan_tube"]
        return ("LOLOS" if bebas >= butuh else "PENUH"), bebas, T(
            "cadangan %d core = %d tube kosong", "%d spare fibres = %d free tubes") % (k["spare"], max(bebas, 0)), info
    core = k.get("core")
    if not core:
        return "BELUM_TERVERIFIKASI", None, T("ukuran kabel tidak terbaca", "cable size could not be read"), info
    tube = core // cpt
    terpakai = len(k.get("fdt_di_feeder") or ())
    if prm["mode_kapasitas"] == "core":
        sisa = core - terpakai * max(butuh_core, 1)
        return ("LOLOS" if sisa >= butuh_core else "PENUH"), sisa // cpt, T("%d core, sudah %d FDT di feeder ini",
                                                                    "%d fibres, already used by %d FDT(s)") % (core, terpakai), info
    led = data.ledger(k.get("pop_nama") or "") if data is not None else {}
    fe = info["feeder"]
    pakai = set(led.get(fe, {}).get("tube", ())) if fe is not None else set()
    if fe is None or (not pakai and not k.get("tube_traksi")):
        # compile tanpa nomor tube (susunan lain): hitung seperti dulu, nomor T diberi berurutan
        bebas = tube - terpakai * prm["tube_per_fdt"] - prm["cadangan_tube"]
        info["sisa_kabel"] = bebas
        return ("LOLOS" if bebas >= butuh else "PENUH"), bebas, T(
            "%d core = %d tube, sudah melayani %d FDT", "%d fibres = %d tubes, already used by %d FDT(s)") % (
            core, tube, terpakai), info
    kel, grup = _kelompok_kabel(k, prm)
    g96, g48 = kelompok_tube(prm)
    bebas = sorted(grup - pakai)
    lain = sorted((g96 if kel == "48F" else g48) - pakai)
    if core >= 144:
        sisa_kabel = tube - len(pakai)
    else:
        sisa_kabel = tube - terpakai * prm["tube_per_fdt"]
    info.update({"kelompok": kel, "bebas": bebas, "tube": bebas[0] if bebas else None, "terpakai": sorted(pakai),
                 "sisa_kabel": sisa_kabel, "bebas_lain": lain, "kelompok_lain": "96F" if kel == "48F" else "48F"})
    ok = bool(bebas) and len(bebas) >= prm["cadangan_tube"] + butuh and sisa_kabel >= butuh
    nama_grup = T("tube %s di jalur %s", "tubes %s on the %s path") % (_teks_tube(grup), kel)
    if ok:
        teks = T("Feeder %d sudah memakai %s; yang masih kosong di %s: %s. Diusulkan %s",
                 "Feeder %d already uses %s; still free in %s: %s. Proposed: %s") % (
            fe, _teks_tube(pakai), nama_grup, _teks_tube(bebas), "T%d" % bebas[0])
    elif not bebas:
        teks = T("Feeder %d sudah memakai semua %s", "Feeder %d already uses all %s") % (fe, nama_grup)
    elif butuh > 1 and len(bebas) < prm["cadangan_tube"] + butuh:
        teks = T("Feeder %d hanya punya %d tube kosong di %s (%s), padahal proyek ini butuh %d tube untuk %d FDT",
                 "Feeder %d has only %d free tube(s) in %s (%s), while this project needs %d tubes for %d FDTs") % (
            fe, len(bebas), nama_grup, _teks_tube(bebas), butuh, butuh)
    else:
        teks = T("kabel %d core ini sudah penuh: sudah melayani %d FDT dari kapasitas %d",
                 "this %d-fibre cable is full: it already serves %d FDT(s) of %d") % (core, terpakai, tube)
    return ("LOLOS" if ok else "PENUH"), len(bebas), teks, info


_ISTILAH = dict(profil.ISTILAH_BAWAAN)


def pakai_istilah(d):
    """Pasang kosakata keluaran (profil.istilah()) untuk label jenis infrastruktur & colo."""
    _ISTILAH.clear()
    _ISTILAH.update(d or profil.ISTILAH_BAWAAN)


# Nama keputusan untuk semua keluaran (satu sumber, dua bahasa)
NAMA_KEPUTUSAN = {
    "COLO": T("Pakai feeder yang ada", "Use an existing feeder"),
    "COLO_CEK": T("Pakai feeder yang ada - cek sisa tube", "Use an existing feeder - check free tubes"),
    "COLO_MANUAL": T("Pilihan desainer", "Designer's choice"),
    "FEEDER_BARU": T("Feeder baru dari POP", "New feeder from the POP"),
    "PERLU_MANUAL": T("Perlu dirancang manual", "Needs manual design"),
}


def nama_keputusan(kode):
    return NAMA_KEPUTUSAN.get(kode, kode)


TIANG_NASIONAL, TIANG_COMPILE, NEW_INFRA, GARIS_BANTU = "TIANG_NASIONAL", "TIANG_COMPILE", "NEW_INFRA", "GARIS_BANTU"


def kelas_infra(k):
    """Kunci jenis infrastruktur (tetap); label tampilannya dari label_kelas()."""
    if k is None:
        return NEW_INFRA
    return TIANG_COMPILE if k["sumber"] == "COMPILE" else TIANG_NASIONAL


def label_kelas(kunci):
    return {TIANG_NASIONAL: _ISTILAH["label_tiang_nasional"], TIANG_COMPILE: _ISTILAH["label_tiang_compile"],
            NEW_INFRA: "New Infra", GARIS_BANTU: "Garis Bantu"}.get(kunci, kunci)


def label_kelas_en(kunci):
    """Label jenis infrastruktur untuk antarmuka QGIS (bahasa Inggris). Label kustom perusahaan dipakai apa adanya."""
    return {TIANG_NASIONAL: _ISTILAH["label_tiang_nasional"], TIANG_COMPILE: _ISTILAH["label_tiang_compile"],
            NEW_INFRA: "New poles / route (New Infra)", GARIS_BANTU: "Helper line - redraw"}.get(kunci, kunci)


def label_colo(k):
    """Kosakata 'Format dalam menggambar Feeder': colo di kabel compile, aturan organisasi, FTTH, lainnya."""
    if k["sumber"] == "COMPILE":
        return _ISTILAH["label_colo_compile"]
    for aturan in _ISTILAH.get("aturan_label_colo") or []:
        if not isinstance(aturan, (list, tuple)) or len(aturan) != 3:
            continue
        kolom, cari, label = aturan
        kol = {"OWNER": "owner", "MODEL": "model", "PRODUCT": "product", "NAME": "nama", "NAMA": "nama",
               "STATUS": "status"}.get(str(kolom).strip().upper(), str(kolom).strip().lower())
        nilai, cari = str(k.get(kol) or "").upper(), str(cari).upper()
        if (nilai.startswith(cari[1:]) if cari.startswith("^") else cari in nilai):     # "^X" = diawali X
            return str(label)
    if (k.get("product") or "").upper() == "FTTH":
        return _ISTILAH["label_colo_ftth"]
    return _ISTILAH["label_colo_lain"]


# ----------------------------------------------------------------------------- analisis
def pilih_pop(fdt_ll, data, nama_pop=None, maks_m=None):
    if not data.pops:
        return None
    if maks_m:
        p = min(data.pops, key=lambda p: geo.haversine(p["ll"], fdt_ll))
        if geo.haversine(p["ll"], fdt_ll) > maks_m:
            return None
    if nama_pop:
        np_ = nama_pop.upper()
        cocok = [p for p in data.pops if np_ and (np_ in p["nama"].upper() or p["nama"].upper().endswith(np_))]
        if cocok:
            return min(cocok, key=lambda p: geo.haversine(p["ll"], fdt_ll))
    return min(data.pops, key=lambda p: geo.haversine(p["ll"], fdt_ll))


JARAK_POP_M = 150.0         # titik sambung sejauh ini dari POP = di closure 144 / OTB: arah kabel 144 tidak bermakna
COS_CLOSURE_MIN = -0.5
DETOUR_LEBIH_MIN_M = 50.0      # closure existing: arah lokal kabel boleh sampai 120 derajat (belokan), feeder harus searah
TOLERANSI_SETARA = 0.05     # kandidat yang kabel barunya beda < 5 % (dan < 100 m) dianggap setara


def core_feeder_baru(h, prm):
    """Ukuran kabel distribusi feeder baru (setelah closure 144). Arahan atasan 18-11-2026: 48 core bila jalur POP->FDT
    sampai batas_48f_km, 96 core bila lebih; 'Tidak' pada feeder_baru_ikut_jarak = selalu core_feeder_baru."""
    fb = h.get("feeder_baru") or {}
    if not prm.get("feeder_baru_ikut_jarak", True) or not fb:
        return int(prm["core_feeder_baru"])
    pjg = float(fb.get("panjang_est_m") or fb.get("panjang_m") or 0.0)
    return 96 if pjg > float(prm["batas_48f_km"]) * 1000.0 else 48


def analisis(fdt, data, prm=None, log=None):
    prm = prm or profil.baru()
    sisa_proyek = int(fdt.get("_proyek_sisa") or 0)
    if sisa_proyek > 1:     # FDT ini dan FDT proyek berikutnya harus muat di feeder yang sama
        prm = dict(prm, _butuh_tube=sisa_proyek)
    F = fdt["ll"]
    L = geo.Lokal(F[0], F[1])
    fx = (0.0, 0.0)
    pop = pilih_pop(F, data, maks_m=prm["pop_maks_m"])
    d_pop = geo.haversine(F, pop["ll"]) if pop else 0.0
    rad = min(15000.0, max(prm["radius_cari_m"], d_pop + 1500.0))
    bb = L.bbox_deg(rad)
    hasil = {"fdt": fdt, "pop": pop, "jarak_pop_m": round(d_pop), "peringatan": [], "kandidat": [],
             "keputusan": "PERLU_MANUAL", "alasan": [], "terpilih": None, "feeder_baru": None}
    butuh_core = (fdt.get("splitter") or 0) if prm["mode_kapasitas"] == "core" else prm["core_per_tube"]
    if pop is None:
        terdekat = min((geo.haversine(F, p["ll"]) for p in data.pops), default=None)
        hasil["peringatan"].append(T(
            "Tidak ada POP/OLT dalam %s dari FDT%s. Arah feeder dan feeder baru tidak bisa dihitung. Tambahkan KMZ "
            "daftar POP atau compile kota ini, atau periksa koordinat FDT.",
            "No POP/OLT within %s of the FDT%s. The feeder direction and a new feeder cannot be worked out. Add the POP "
            "list KMZ or the compilation for this city, or check the FDT coordinates.") % (
                km(prm["pop_maks_m"]), (T(" (terdekat %s)", " (nearest %s)") % km(terdekat)) if terdekat else ""))
    if not butuh_core:
        butuh_core = prm["core_per_tube"]
        hasil["peringatan"].append(T("Jumlah splitter di FDT tidak terbaca: dianggap butuh 1 tube (12 core).",
                                     "The FDT splitter count could not be read: one tube (12 fibres) is assumed."))

    kb = data.kabel_nasional(bb)
    if data.indeks and not kb:
        hasil["peringatan"].append(T("Tidak ada kabel dari inventaris kabel dalam %s dari FDT. Pastikan KMZ inventaris "
                                     "untuk wilayah ini sudah dipilih dan koordinat FDT benar.",
                                     "No cable from the cable inventory within %s of the FDT. Make sure the inventory "
                                     "KMZ for this region is selected and the FDT coordinates are right.") % m(rad))
    kc = data.kabel_compile(bb)
    kor = data.koridor_compile(bb)
    kab = kb + kc + kor
    byid = {k["id"]: k for k in kab}
    G = Graf()
    for k in kab:
        k["xy"] = [L.ke(p) for p in k["ll"]]
        G.garis(k["xy"], "KABEL", k["id"], prm["faktor_tiang_eksisting"], prm["rapat_m"])
    jalan = []
    if data.jalan is not None:
        try:
            jalan = data.jalan(bbox_jalan(F, pop, prm)) or []
        except Exception as e:      # jalan opsional: analisis tetap jalan dengan garis bantu
            hasil["peringatan"].append(T("Data jalan tidak tersedia (%s): bagian tanpa kabel yang ada digambar sebagai "
                                         "garis bantu lurus dan harus digambar ulang.",
                                         "Road data not available (%s): parts without existing cable are drawn as "
                                         "straight helper lines that must be redrawn.") % str(e)[:80])
    # kelas jalan yang dihindari untuk jalur kabel baru (PDF: footway & motorway, dapat diatur)
    hindari = _daftar_kelas(prm.get("kelas_jalan_hindari"))
    if hindari:
        jalan = [j for j in jalan if (j.get("kelas") or "").lower() not in hindari]
    for j in jalan:
        G.garis([L.ke(p) for p in j["ll"]], "JALAN", None, osm.faktor(j.get("kelas")))
    n_kabel_simpul = len(G.xy)
    # sambungan antar kabel (satu tiang/koridor) dan kabel-jalan
    for i in range(n_kabel_simpul):
        if not G.refs[i]:
            continue
        for d, j in G.dekat(G.xy[i], prm["sambung_kabel_m"], lambda j, i=i: j != i and G.refs[j] and not (
                G.refs[j] & G.refs[i]))[:2]:
            G.tepi(i, j, "SAMBUNG", None, 1.0)
        if jalan:
            for d, j in G.dekat(G.xy[i], prm["sambung_jalan_m"], lambda j: not G.refs[j])[:1]:
                G.tepi(i, j, "SAMBUNG", None, 1.0)
    nf = G.simpul(fx)
    # sambungan lurus FDT -> jaringan hanya ke simpul yang hampir sedekat simpul terdekat (+30 m / 1,5x): sambungan
    # panjang memotong rumah ke jalan lain tidak dipakai bila ada jalan/tiang tepat di samping FDT (Tomohon KGA01)
    akses = G.dekat(fx, prm["akses_maks_m"], lambda j: j != nf)
    if akses:
        batas_akses = max(akses[0][0] * 1.5, akses[0][0] + 30.0)
        akses = [(d, j) for d, j in akses if d <= batas_akses]
    for d, j in akses[:8]:
        G.tepi(nf, j, "AKSES", None, prm["faktor_akses"])
    np_ = None
    # garis bantu: saat ada data jalan hanya dipakai bila jalur jalan/tiang jauh lebih panjang (faktor_bebas, 4x)
    fb = prm["faktor_bebas"] if jalan else prm["faktor_garis_bantu"]
    if pop:
        P = L.ke(pop["ll"])
        np_ = G.simpul(P)
        for d, j in G.dekat(P, 300.0, lambda j: j != np_)[:8]:
            G.tepi(np_, j, "AKSES", None, prm["faktor_akses"])
        # garis bantu POP->FDT (dipakai hanya bila tidak ada jalur jalan/kabel yang lebih murah)
        G.tepi(np_, nf, "BEBAS", None, fb)

    # kapasitas & kandidat (hanya kabel compile dan - bila diizinkan - kabel inventaris berproduk feeder)
    kand = {}
    for k in kab:
        if k.get("koridor"):
            k["kap"] = ("BUKAN_FEEDER", None, "", {})
            continue
        st, bebas, teks, info = kapasitas(k, prm, butuh_core, data)
        k["kap"] = (st, bebas, teks, info)
        if st in ("LOLOS", "PENUH") or (st == "BELUM_TERVERIFIKASI" and prm["pakai_spare_kosong"]):
            kand[k["id"]] = k        # PENUH tetap dinilai agar alasannya tampil di tabel kandidat
    # titik slack/closure existing feeder di kabel kandidat: simpul graf bertanda (calon titik sambung utama)
    tanda = {}
    titik_feeder = {}
    if pop:
        for kid, k in kand.items():
            if k["sumber"] != "COMPILE":
                continue
            fe = _angka_feeder(k.get("feeder"))
            kunci = (k.get("pop_nama"), fe)
            if kunci not in titik_feeder:
                titik_feeder[kunci] = data.titik_feeder(k.get("pop_nama") or "", fe, bb)
            for tf in titik_feeder[kunci]:
                q = L.ke(tf["ll"])
                nb = geo.terdekat_di_garis(q, k["xy"])
                if not nb or nb[0] > prm["tap_slack_m"]:
                    continue
                j = G.simpul(nb[3], kid)
                a = G.simpul(k["xy"][nb[1]], kid)
                b = G.simpul(k["xy"][nb[1] + 1], kid)
                G.tepi(j, a, "KABEL", kid, prm["faktor_tiang_eksisting"])
                G.tepi(j, b, "KABEL", kid, prm["faktor_tiang_eksisting"])
                lama = tanda.get(j)
                if lama is None or nb[0] < lama["jarak_m"] or (tf["jenis"] == "closure" and lama["jenis"] != "closure"):
                    tanda[j] = dict(tf, jarak_m=round(nb[0], 1), kabel=kid)
            # ujung kabel compile (E2E): titik sambung sah tanpa memotong kabel di tengah bentang (desain riil 15 %)
            for p in (k["xy"][0], k["xy"][-1]):
                j = G.simpul(p, kid)
                if j not in tanda:
                    tanda[j] = {"ll": L.balik(p), "nama": "ujung kabel %dC %s" % (
                        k.get("core") or 0, str(k.get("traksi") or "")[:14].rstrip("_")), "jenis": "ujung",
                        "eksisting": True, "core": k.get("core"), "traksi": k.get("traksi"), "jarak_m": 0.0, "kabel": kid}
    # garis bantu lurus ke titik terdekat setiap kandidat (dipakai hanya bila lebih murah dari jalur jalan/kabel)
    for kid, k in kand.items():
        nb = geo.terdekat_di_garis(fx, k["xy"])
        if nb and nb[0] <= prm["cabang_maks_m"]:
            j = G.simpul(nb[3], kid)
            # sambungkan titik proyeksi ke garis kabelnya
            a = G.simpul(k["xy"][nb[1]], kid)
            b = G.simpul(k["xy"][nb[1] + 1], kid)
            G.tepi(j, a, "KABEL", kid, prm["faktor_tiang_eksisting"])
            G.tepi(j, b, "KABEL", kid, prm["faktor_tiang_eksisting"])
            G.tepi(nf, j, "BEBAS", None, fb)

    distA, prevA = G.dijkstra(nf, maks=rad * 3)
    distB = prevB = None
    if np_ is not None:
        distB, prevB = G.dijkstra(np_, jenis_boleh=("KABEL", "SAMBUNG", "AKSES"), maks=rad * 4)
    u = geo.satuan(L.ke(pop["ll"]), fx) if pop else None
    P = L.ke(pop["ll"]) if pop else None

    # koridor milik tiap feeder (kabel + garis tiang compile) untuk mengukur kesesuaian arah cabang baru
    koridor_feeder = {}
    for k in kc + kor:
        fe = _angka_feeder(k.get("feeder"))
        if fe is not None:
            koridor_feeder.setdefault((k.get("pop_nama"), fe), []).append(k["xy"])
            if not k.get("koridor"):
                koridor_feeder.setdefault(("KABEL", k.get("pop_nama"), fe), []).append(k["xy"])

    # node per kandidat
    per_ref = {}
    for i, rs in enumerate(G.refs):
        for r in rs:
            if r in kand:
                per_ref.setdefault(r, []).append(i)
    daftar = []
    for kid, nodes in per_ref.items():
        k = kand[kid]
        best = best_any = best_slack = best_closure = None
        for v in nodes:
            c = distA[v]
            if c == INF:
                continue
            lurus = math.hypot(G.xy[v][0], G.xy[v][1])
            di_pop = P is not None and math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) <= JARAK_POP_M
            if di_pop:      # arah potongan kabel di POP tidak bermakna; kesesuaian arah diuji lewat koridor feeder
                cosv, sumber_arah = None, "di closure 144 / OTB di POP"
            else:
                cosv, sumber_arah = _arah(G, v, kid, prevB, u, L, pop)
            searah = lurus <= prm["jarak_dekat_m"] or cosv is None or cosv >= prm["cos_arah_min"]
            rec = (c, v, cosv, searah, lurus, sumber_arah)
            if best_any is None or c < best_any[0]:
                best_any = rec
            if searah and (best is None or c < best[0]):
                best = rec
            if searah and v in tanda and (best_slack is None or c < best_slack[0]):
                best_slack = rec
            # closure existing di kabel ini: arah dinilai longgar (belokan lokal di ujung kabel, mis. 120 m terakhir
            # kabel 96C Banda Aceh F5 berbelok 106 derajat, bukan alasan membuang closure di feeder yang searah)
            if v in tanda and tanda[v].get("jenis") == "closure" and \
                    (searah or (cosv is not None and cosv >= COS_CLOSURE_MIN)) and \
                    (best_closure is None or c < best_closure[0]):
                best_closure = rec
        if best_any is None:
            continue
        pilihan = best if best is not None and best[0] <= best_any[0] * 1.5 else best_any
        # 1.6.1: kabel BARU usulan FDT lain di proses ini (proyek yang sama) belum dibangun - closure-nya dipasang di
        # titik terbaik (dekat FDT ini), bukan dipaksa ke slack/closure di pangkalnya. Dua FDT satu proyek = satu kabel
        kv = byid.get(kid) or {}
        if kv.get("berkas") == "_TEMBUKU_BATCH" and pilihan[3] and kv.get("proyek_id") and \
                kv.get("proyek_id") == fdt.get("_proyek_id"):
            if pilihan[1] not in tanda:     # closure usulan di titik ini (dinilai sebagai titik sambung yang sah)
                tanda[pilihan[1]] = {"ll": L.balik(G.xy[pilihan[1]]), "nama": "Closure usulan", "jenis": "usulan",
                                     "eksisting": False, "core": k.get("core"), "traksi": k.get("traksi"),
                                     "jarak_m": 0.0, "kabel": kid}
            daftar.append(_nilai_kandidat(G, k, pilihan, prevA, distB, prevB, prm, P, byid, tanda, koridor_feeder,
                                          data, L))
            continue
        # titik sambung dipindah ke slack/closure existing bila tidak jauh lebih mahal (closure baru tepat di slack)
        if best_slack is not None and best_slack is not pilihan and \
                best_slack[0] <= pilihan[0] + prm["tap_slack_toleransi_m"]:
            pilihan = best_slack
        # arahan revisi 23-11-2026: menyambung boleh di slack, tetapi CLOSURE diutamakan. Closure existing di kabel
        # yang sama dipakai bila kabel barunya paling banyak closure_utama_m lebih panjang daripada titik terpilih,
        # dan hanya bila kabel ini memang searah (ada titik searah) - closure di feeder yang menjauh tetap tidak dipakai
        # Perbandingan dalam METER kabel baru (bukan biaya graf: kabel di tiang existing berbobot 0,2/m, sehingga 600
        # satuan biaya bisa berarti 3 km kabel - regresi 1.6.1 awal: Tomohon KEN01 1 m -> 2.326 m, Minahasa WAN01 0 -> 5.606 m)
        if best_closure is not None and best is not None and best_closure is not pilihan:
            pj_c = _rakit_rute(G, prevA, best_closure[1], byid, prm["faktor_garis_bantu"])["panjang_m"]
            pj_p = _rakit_rute(G, prevA, pilihan[1], byid, prm["faktor_garis_bantu"])["panjang_m"]
            # closure searah: boleh sampai closure_utama_m lebih panjang. Closure yang arah lokalnya menyimpang (belokan)
            # hanya bila MEMPERPENDEK kabel baru - closure itu ada lebih jauh di feeder ke arah FDT (Banda Aceh 1.804 ->
            # 1.512 m); tanpa syarat ini kabel 144C Tomohon KEN01 ikut mendapat closure dan menggeser kandidat 1 m
            # Arahan 'slack boleh, closure diutamakan' = memilih ANTARA slack dan closure: kelonggaran closure_utama_m
            # hanya bila titik terpilih sudah di slack/ujung kabel existing; titik di tengah kabel hanya diganti closure
            # yang memperpendek kabel baru (agar kandidat tengah-kabel tidak 'naik kelas' lewat aturan slack-dahulu)
            longgar = best_closure[3] and pilihan[1] in tanda
            batas_c = pj_p + float(prm.get("closure_utama_m", 100.0)) if longgar else pj_p
            if pj_c <= batas_c:
                if not best_closure[3]:
                    best_closure = (best_closure[0], best_closure[1], best[2], True, best_closure[4],
                                    "closure di feeder yang searah (belokan di ujung kabel diabaikan)")
                pilihan = best_slack = best_closure
        daftar.append(_nilai_kandidat(G, k, pilihan, prevA, distB, prevB, prm, P, byid, tanda, koridor_feeder,
                                      data, L))
        # PDF 3.3: slack harus dari compile, slack baru tidak dibuat. Bila titik sambung terbaik kabel ini bukan slack,
        # titik di slack/closure/ujung kabel yang sama tetap dinilai sebagai kandidat tersendiri dan didahulukan
        # bila lolos semua syarat (lihat _urut_setara)
        if best_slack is not None and best_slack is not pilihan:
            d2 = _nilai_kandidat(G, k, best_slack, prevA, distB, prevB, prm, P, byid, tanda, koridor_feeder, data, L)
            d2["fisik"] = str(d2["fisik"]) + "|slack"
            daftar.append(d2)
    daftar = _gabung_fisik(daftar)
    daftar.sort(key=lambda d: d["skor"])
    hasil["kandidat"] = daftar[:12]
    hasil["n_kabel_diperiksa"] = len(kab)
    hasil["n_kandidat_kapasitas"] = len([k for k in kand.values() if k["kap"][0] == "LOLOS"])
    hasil["ada_jalan"] = bool(jalan)

    # feeder baru dari POP
    if np_ is not None and distA[np_] < INF:
        hasil["feeder_baru"] = _rakit_rute(G, prevA, np_, byid, prm["faktor_garis_bantu"])
        hasil["feeder_baru"]["biaya"] = distA[np_]
        hasil["feeder_baru"]["core"] = core_feeder_baru(hasil, prm)
    _putuskan(hasil, prm)
    # Saran Tembuku: semua kandidat (bukan hanya 12 teratas) dinilai ulang; yang disarankan masuk daftar kandidat
    # agar bisa dipilih di panel/pop-up dengan mekanisme yang sama (pilih_manual)
    from . import saran as _saran
    alt = _saran.nilai(hasil, daftar, prm)
    if alt is not None and not any(k is alt for k in hasil["kandidat"]):
        hasil["kandidat"].append(alt)
    isi_route_existing(hasil, G, byid, L, prm)
    from . import cek_gambar as _cg
    _dj = _cg.JalanDekat(jalan)
    rapikan_gambar_data(hasil, G, prm, getattr(data, "gambar_rusak", None),   # sesudah label route/colo
                        (lambda p: _dj(*L.balik(p))) if _dj else None, L)
    hasil["penomoran"] = penomoran(hasil, data)
    hasil["lokal"] = (F[0], F[1])
    hasil["alasan"].insert(0, ringkasan_awam(hasil, prm))
    # penyeberangan jalan di ruas New Infra jalur terpilih (tiang 9 m di kedua sisi)
    seberang = _daftar_kelas(prm.get("kelas_seberang")) or KELAS_SEBERANG
    besar = [[L.ke(p) for p in j["ll"]] for j in jalan if (j.get("kelas") or "").lower() in seberang]
    for r in ([hasil["terpilih"]["rute"]] if hasil.get("terpilih") else []) + ([hasil["feeder_baru"]] if hasil.get("feeder_baru") else []):
        r["seberang"] = _penyeberangan(r, besar)
    from . import penjelasan as _pj
    hasil["penjelasan"] = _pj.susun(hasil, prm)
    return hasil


KELAS_SEBERANG = {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary",
                  "tertiary_link"}


def _daftar_kelas(teks):
    """'footway, pedestrian' -> {'footway', 'pedestrian'} (huruf kecil, tanpa spasi)."""
    return {x.strip().lower() for x in str(teks or "").replace(";", ",").split(",") if x.strip()}


def label_tap(ts):
    """Uraian titik sambung existing dalam dua bahasa, atau None."""
    if not ts:
        return None
    nama = str(ts.get("nama") or "").strip()
    if ts.get("jenis") == "ujung":
        return T("ujung kabel yang sudah ada (%s)", "the end of an existing cable (%s)") % nama
    if ts.get("jenis") == "usulan":
        return T("kabel baru FDT lain di proyek yang sama (closure baru di titik ini)",
                 "the new cable of another FDT in the same project (a new closure at this point)")
    umum = nama.upper() in ("", "SLACK", "CLOSURE", "HANGER", "SPARE") or len(nama) <= 3
    if ts.get("jenis") == "closure":
        return (T("closure yang sudah ada", "an existing closure") if umum else
                T("closure yang sudah ada (%s)", "the existing closure (%s)") % nama)
    return (T("slack yang sudah ada", "an existing slack") if umum else
            T("slack yang sudah ada (%s)", "the existing slack (%s)") % nama)


def _penyeberangan(rute, besar, sisi=8.0):
    """Titik jalur memotong jalan utama (sudut >= 30 derajat) di ruas New Infra -> [(xy sebelum, xy sesudah)]:
    lokasi tiang 9 m di kedua sisi. Jalur yang berjalan SEPANJANG jalan itu bukan penyeberangan."""
    titik = rute["titik"]
    if not besar or len(titik) < 2:
        return []
    kotak = []
    for xy in besar:
        xs = [q[0] for q in xy]
        ys = [q[1] for q in xy]
        kotak.append((min(xs), min(ys), max(xs), max(ys)))
    ch_seg, acc = [], 0.0
    for a, b in zip(titik, titik[1:]):
        ch_seg.append(acc)
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
    baru = set()
    for kelas, _ref, xy in rute["segmen"]:
        if kelas in (NEW_INFRA, GARIS_BANTU):
            for a, b in zip(xy, xy[1:]):
                baru.add((a, b))
    ketemu = []

    def arah_jalan(p):
        """Arah jalan utama yang MENEMBUS simpul ini (persimpangan bisa lebih dari satu). Jalan yang berakhir di simpul
        (mulut gang di pertigaan) bukan penyeberangan; jalan yang di OSM terpotong dua di simpul tetap dihitung tembus."""
        lengan = []                      # arah keluar dari simpul untuk tiap ruas jalan
        for xy, kb in zip(besar, kotak):
            if not (kb[0] - 3 <= p[0] <= kb[2] + 3 and kb[1] - 3 <= p[1] <= kb[3] + 3):
                continue
            nb = geo.terdekat_di_garis(p, xy)
            if not nb or nb[0] > 2.0:
                continue
            i, q = nb[1], nb[3]
            maju = next((xy[j] for j in range(i + 1, len(xy)) if math.hypot(xy[j][0] - q[0], xy[j][1] - q[1]) > 2.0), None)
            mundur = next((xy[j] for j in range(i, -1, -1) if math.hypot(xy[j][0] - q[0], xy[j][1] - q[1]) > 2.0), None)
            lengan += [geo.satuan(q, x) for x in (maju, mundur) if x is not None]
        out = []
        for k, u in enumerate(lengan):
            for v in lengan[k + 1:]:
                if u[0] * v[0] + u[1] * v[1] < -0.8:          # dua lengan berlawanan = jalan tembus
                    out.append(u)
        return out

    def silang(u, v):
        return u[0] * v[1] - u[1] * v[0]
    for i, (a, b) in enumerate(zip(titik, titik[1:])):
        if (a, b) not in baru or a == b:
            continue
        # (1) memotong di tengah bentang
        for xy, kb in zip(besar, kotak):
            if max(a[0], b[0]) < kb[0] or min(a[0], b[0]) > kb[2] or max(a[1], b[1]) < kb[1] or min(a[1], b[1]) > kb[3]:
                continue
            for c, d in zip(xy, xy[1:]):
                hit = geo.potong_segmen(a, b, c, d)
                if hit and 0.02 < hit[0] < 0.98 and hit[1] >= 0.5:
                    ketemu.append(ch_seg[i] + hit[0] * math.hypot(b[0] - a[0], b[1] - a[1]))
        # (2) memotong tepat di simpul jalan: arah masuk dan keluar sama-sama melintang terhadap salah satu jalan utama
        # yang lewat di simpul itu, dan pindah dari satu sisi jalan ke sisi lainnya (bukan masuk lalu balik ke sisi asal)
        if i + 2 < len(titik) and (b, titik[i + 2]) in baru and b != titik[i + 2]:
            u_in, u_out = geo.satuan(a, b), geo.satuan(b, titik[i + 2])
            for rj in arah_jalan(b):
                s1, s2 = silang(u_in, rj), silang(u_out, rj)
                if abs(s1) >= 0.5 and abs(s2) >= 0.5 and s1 * s2 > 0:
                    ketemu.append(ch_seg[i + 1])
                    break
    out, akhir = [], None
    for ch in sorted(ketemu):
        if akhir is not None and ch - akhir < 25.0:
            continue
        akhir = ch
        out.append((geo.titik_di(titik, max(0.0, ch - sisi)), geo.titik_di(titik, min(acc, ch + sisi))))
    return out


def ringkasan_awam(h, prm):
    """Satu kalimat keputusan untuk pembaca awam: apa yang dibangun, di folder mana, berapa kabel barunya, dan
    pembandingnya. Selalu menjadi kalimat pertama alasan (panel, laporan, CSV, KMZ)."""
    n = h.get("penomoran") or {}
    k = h.get("terpilih")
    fb = h.get("feeder_baru")
    kep = h["keputusan"]
    folder = "F%s_T%s" % (n.get("feeder"), n.get("t"))
    if kep in ("COLO", "COLO_CEK", "COLO_MANUAL") and k:
        siapa = (T("Feeder %d", "Feeder %d") % k["feeder_int"]) if k.get("feeder_int") else (k["nama"] or k["id"])
        s = T("Pakai %s yang sudah ada, tube T%s (folder %s). Kabel baru dari titik sambung ke FDT %s",
              "Use the existing %s, tube T%s (folder %s). The new cable from the tap point to the FDT is %s") % (
            siapa, n.get("t"), folder, m(k["kabel_baru_m"]))
        if k.get("colo_rasio") is not None and k["kabel_baru_m"] >= 50:
            s += T(", %d%% di tiang yang sudah ada", ", %d%% of it on existing poles") % round(100 * k["colo_rasio"])
        s += T(".", ".")
        if fb:
            s += T(" Sebagai pembanding, feeder baru dari POP butuh %s kabel baru, belum termasuk OTB dan kabel 144 core.",
                   " For comparison, a new feeder from the POP needs %s of new cable, not counting the OTB and the "
                   "144-fibre cable.") % m(fb["panjang_m"])
        if kep == "COLO_CEK":
            s += T(" Tube-nya belum tercatat di data, jadi pastikan dulu masih kosong.",
                   " The tube is not recorded in the data, so first make sure it is still free.")
        return s
    if kep == "FEEDER_BARU" and fb:
        return T("Buat feeder baru dari %s sepanjang %s (folder %s), karena belum ada feeder yang cocok.",
                 "Build a new feeder from %s, %s long (folder %s), because no existing feeder fits.") % (
            h["pop"]["nama"] if h.get("pop") else "POP", m(fb["panjang_m"]), folder)
    return T("FDT ini perlu dirancang manual. Alasannya ada di bawah.",
             "This FDT needs to be designed by hand. The reason is below.")


def panjang_144(prm, feeder):
    """Panjang kabel 144F feeder baru: titik tengah jendela slack ujung feeder ke-n (F01 100-250 m, +50 m per
    feeder), paling panjang maks_144_m; atau stub_144_m bila pola dimatikan."""
    if not prm.get("pola_slack_144", True):
        return min(float(prm["stub_144_m"]), float(prm.get("maks_144_m", 750)))
    n = max(1, int(feeder or 1))
    return min(175.0 + 50.0 * (n - 1), float(prm.get("maks_144_m", 750)))


def _gabung_fisik(daftar):
    """Satu kabel fisik = satu kandidat: potongan inventaris yang sama (id 'B12_345') digabung, dipilih yang terbaik."""
    out = {}
    for d in daftar:
        kunci = d.get("fisik") or d["id"]
        if kunci not in out or d["skor"] < out[kunci]["skor"]:
            out[kunci] = d
    return list(out.values())


def komit(h, data, prm):
    """Masukkan hasil desain (kabel baru + FDT) ke data sebagai traksi virtual, agar FDT berikutnya dalam satu batch
    melihat buku tube terbaru dan dapat memetik kabel yang baru didesain (pola riil: F1_T10 memetik 48C milik F1_T9)."""
    if h["keputusan"] not in ("COLO", "COLO_CEK", "COLO_MANUAL", "FEEDER_BARU"):
        return
    rute = h["terpilih"]["rute"] if h.get("terpilih") else h.get("feeder_baru")
    if not rute or len(rute["titik"]) < 2:
        return
    L = geo.Lokal(*h["lokal"])
    n = h["penomoran"]
    kode = "F%d_T%d_TEMBUKU_%s" % (n["feeder"], n["t"], h["fdt"]["kode"])
    sel = h.get("terpilih")
    core = int(core_feeder_baru(h, prm) if h["keputusan"] == "FEEDER_BARU" else (sel or {}).get("core_cabang") or prm["core_cabang"])
    if not data.compiles or data.compiles[-1].get("berkas") != "_TEMBUKU_BATCH":
        data.compiles.append({"pops": [], "traksi": {}, "kabel": [], "fdt": [], "berkas": "_TEMBUKU_BATCH"})
    c = data.compiles[-1]
    popf = n["pop_folder"]
    ll = [L.balik(p) for p in rute["titik"]]
    fdt = dict(h["fdt"], traksi=kode, feeder=str(n["feeder"]), pop_folder=popf, colo_saudara=False)
    kab = {"id": "V%d" % (len(c["kabel"]) + 1), "ll": ll, "core": core, "jenis": "NEW_CABLE", "nama": "%dC" % core,
           "traksi": kode, "feeder": str(n["feeder"]), "pop_folder": popf, "berkas": "_TEMBUKU_BATCH",
           "sumber": "COMPILE", "warna": None, "folder": "New Cable %dC" % core,
           "proyek_id": h["fdt"].get("_proyek_id"), "fdt_proyek": h["fdt"]["kode"]}
    colo = []
    if sel and sel.get("colo_xy"):
        colo.append({"ll": [L.balik(p) for p in sel["colo_xy"]]})
        # FDT baru juga terhitung di kabel yang dipetik (kabel compile asli)
        for cc in data.compiles:
            for t in cc["traksi"].values():
                if t["kode"] == sel.get("traksi"):
                    t.setdefault("_tambahan", []).append(h["fdt"]["kode"].upper())
    tube = {int(n["t"])} if n.get("t") else set()
    # closure di titik sambung yang diusulkan ikut dicatat: FDT berikutnya di feeder yang sama boleh berbagi closure ini
    # (batas lubang closure tetap diperiksa), sehingga tidak dibuat closure baru berdempetan
    closure = []
    if sel and rute["titik"]:
        tsl = sel.get("tap_slack") or {}
        if tsl.get("jenis") != "closure":
            closure.append({"nama": "Closure usulan Tembuku (%s)" % h["fdt"]["kode"], "ll": L.balik(rute["titik"][0]),
                            "eksisting": False, "core": sel.get("core")})
    c["traksi"][("_TEMBUKU_BATCH", popf, str(n["feeder"]), kode)] = {
        "kode": kode, "pop_folder": popf, "feeder": str(n["feeder"]), "berkas": "_TEMBUKU_BATCH", "fdt": [fdt],
        "kabel": [kab], "colo": colo, "closure": closure, "slack": [], "lain": [],
        "info": {"feeder": n["feeder"], "t": str(n["t"]), "tube": tube, "cluster": h["fdt"].get("cluster"),
                 "area": h["fdt"].get("area") or h["fdt"].get("kode")}}
    c["kabel"].append(kab)
    c["fdt"].append(fdt)
    c.pop("_peta_traksi", None)
    data._ledger.clear()


TUBE_PER_FEEDER = 12
MARGIN_TIPIS_DB = 1.0        # sisa redaman di bawah ini ditandai untuk dicek (bukan mengubah keputusan)


def _feeder_kabel_inventaris(h, sel, data):
    """Kabel inventaris yang dipakai sering kali feeder yang SUDAH ADA di compile (sudah dibangun). Feeder-nya dikenali
    dari (1) ID cluster traksi yang tertulis di nama kabel, atau (2) titik sambung yang berada <= 30 m dari kabel/colo
    sebuah traksi di compile. -> (nomor feeder, folder POP, compile) atau None (belum ada di compile)."""
    nama = str(sel.get("nama") or "") + " " + str(sel.get("id") or "")
    tap = None
    try:
        tap = geo.Lokal(*h["lokal"]).balik(sel["rute"]["titik"][0])
    except (KeyError, IndexError, TypeError):
        tap = None
    terbaik = None
    for c in data.compiles:
        if c.get("berkas") == "_TEMBUKU_BATCH":
            continue
        for (b, popf, fdr, kode), t in c["traksi"].items():
            inf = t.get("info") or {}
            if kode in data.kecuali or not inf.get("feeder"):
                continue
            if inf.get("cluster") and str(inf["cluster"]) in nama:
                return int(inf["feeder"]), popf, c
            if tap is None:
                continue
            L = geo.Lokal(*tap)
            for k in list(t.get("kabel") or []) + list(t.get("colo") or []):
                if k.get("jenis", "NEW_CABLE") not in ("NEW_CABLE", "COLO_CABLE"):
                    continue
                xy = [L.ke(q) for q in k["ll"]]
                if len(xy) < 2 or min(abs(p[0]) + abs(p[1]) for p in xy) > 5000:
                    continue
                d = geo.terdekat_di_garis((0.0, 0.0), xy)[0]
                if d <= 30.0 and (terbaik is None or d < terbaik[0]):
                    terbaik = (d, int(inf["feeder"]), popf, c)
    return terbaik[1:] if terbaik else None


def penomoran(h, data):
    """Feeder & nomor T untuk folder KMZ. Colo di kabel compile -> feeder kabel itu, T = nomor tube terkecil yang masih
    kosong di kelompoknya (buku tube per feeder dari hierarki folder); feeder baru -> nomor feeder berikutnya di POP,
    T1. Kabel inventaris yang ternyata feeder compile -> feeder itu, tube kosong terkecil (perlu dicek)."""
    sel = h.get("terpilih")
    pop = h.get("pop") or {}
    pnama = pop.get("nama", "POP")
    asal = None
    if sel and sel["sumber"] == "COMPILE" and sel.get("feeder"):
        c0 = next((c for c in data.compiles if c["berkas"] == (sel.get("grup") or ("",))[0]), {})
        asal = (int(_angka_feeder(sel["feeder"])), sel.get("pop_folder") or "", c0)
    elif sel and h["keputusan"] != "FEEDER_BARU":
        asal = _feeder_kabel_inventaris(h, sel, data)
    if asal:
        n, popf_sel, c0 = asal
        pn = data.nama_pop(popf_sel, c0) if popf_sel else pnama
        led = data.ledger(pn)
        pakai = set(led.get(n, {}).get("tube", ()))
        tube = (sel.get("kap_info") or {}).get("tube")
        if tube and tube not in pakai:
            t = int(tube)
        else:
            kosong = [i for i in range(1, TUBE_PER_FEEDER + 1) if i not in pakai]
            if pakai or sel["sumber"] == "COMPILE":
                if kosong:
                    t = kosong[0]
                    if sel["sumber"] != "COMPILE":
                        pesan = T("Feeder %d: kabel inventaris ini dikenali sebagai feeder compile; tube yang diusulkan "
                                  "T%d (nomor kosong terkecil) perlu dipastikan di lapangan.",
                                  "Feeder %d: this inventory cable is recognised as a compilation feeder; the proposed "
                                  "tube T%d (lowest free number) must be confirmed on site.") % (n, t)
                        if str(pesan) not in [str(x) for x in h.setdefault("peringatan", [])]:
                            h["peringatan"].append(pesan)
                else:
                    t = TUBE_PER_FEEDER
                    pesan = T("Feeder %d: semua %d nomor T sudah tercatat terpakai. Periksa apakah masih ada tube kosong, "
                              "atau pilih feeder lain / feeder baru.",
                              "Feeder %d: all %d T numbers are already recorded as used. Check whether a tube is still "
                              "free, or choose another feeder / a new feeder.") % (n, TUBE_PER_FEEDER)
                    if str(pesan) not in [str(x) for x in h.setdefault("peringatan", [])]:
                        h["peringatan"].append(pesan)
            else:
                t = 1
        return {"pop_folder": popf_sel or pnama, "feeder": n, "t": t, "baru": False, "t_tercatat": sorted(pakai),
                "kelompok": (sel.get("kap_info") or {}).get("kelompok")}
    led = data.ledger(pnama)
    folder = ""
    for c in data.compiles:
        for (_b, popf, _f, kode), t in c["traksi"].items():
            if kode in data.kecuali or not popf:
                continue
            from . import sumber
            if sumber.kunci_pop(data.nama_pop(popf, c)) == sumber.kunci_pop(pnama):
                folder = popf
                break
        if folder:
            break
    n = max(list(led.keys()) or [0]) + 1
    return {"pop_folder": folder or pnama, "feeder": n, "t": 1, "baru": h["keputusan"] == "FEEDER_BARU",
            "kelompok": "96F"}


def sudut_arah(cosv):
    """Selisih arah feeder terhadap arah POP->FDT dalam derajat (0 = searah), atau None bila tidak diketahui."""
    if cosv is None:
        return None
    return int(round(math.degrees(math.acos(max(-1.0, min(1.0, cosv))))))


def vonis_kandidat(k):
    """Kesimpulan singkat satu kandidat feeder, dua bahasa."""
    if k["gagal"]:
        return T("Tidak dipakai: ", "Not used: ") + gabung("; ", k["gagal"])
    if k["catatan"]:
        return T("Bisa dipakai, dengan catatan: ", "Usable, with a note: ") + gabung("; ", k["catatan"])
    return T("Memenuhi semua syarat", "Meets every condition")


def teks_tube(k):
    """'T9 (kelompok 48F, T9-T12)' untuk kandidat compile; '-' bila tidak ada nomor tube."""
    inf = k.get("kap_info") or {}
    if inf.get("tube"):
        return T("T%d (kelompok %s)", "T%d (group %s)") % (inf["tube"], inf.get("kelompok") or "-")
    return T("-", "-")


def uraian_kandidat(k):
    """Uraian lengkap satu kandidat feeder dalam bahasa awam (untuk KMZ dan tooltip)."""
    sd = sudut_arah(k.get("cos"))
    arah = (T("arah tidak diketahui", "direction unknown") if sd is None else
            T("searah dengan FDT (melenceng %d°)", "runs toward the FDT (%d° off)") % sd if k.get("searah", True) else
            T("menjauhi FDT (melenceng %d°)", "runs away from the FDT (%d° off)") % sd)
    bag = [vonis_kandidat(k) + ".",
           T("Sisa tube: %s.", "Free tubes: %s.") % k["ket_kapasitas"],
           T("Kabel baru dari titik sambung ke FDT: %s.", "New cable from the tap point to the FDT: %s.") %
           m(k["kabel_baru_m"]),
           T("Arah feeder: %s.", "Feeder direction: %s.") % arah]
    ts = k.get("tap_slack")
    if ts:
        bag.append(T("Titik sambung di %s (%s m).", "Tap at %s (%s m).") % (label_tap(ts), ts["jarak_m"]))
    if k.get("colo_rasio") is not None:
        bag.append(T("%d%% kabel baru menumpang tiang existing.", "%d%% of the new cable runs on existing poles.") %
                   round(100 * k["colo_rasio"]))
    if k.get("koridor_sendiri") is not None and (k.get("core") or 0) >= 144:
        bag.append(T("%d%% jalur kabel baru mengikuti koridor feeder ini.",
                     "%d%% of the new cable follows this feeder's own corridor.") % round(100 * k["koridor_sendiri"]))
    if k.get("rasio_jalur") is not None:
        bag.append(T("Jalur lewat feeder ini %s panjang feeder baru.", "The route through this feeder is %s a new "
                     "feeder.") % kali(k["rasio_jalur"]))
    bud = k.get("budget") or {}
    if bud:
        bag.append(T("Redaman sinyal %s (sisa %s).", "Signal loss %s (%s to spare).") % (
            db(bud["total_db"]), db(bud["margin_db"])))
    return gabung(" ", bag)


def hasil_gagal(fdt, data, prm, galat):
    """Hasil pengganti bila analisis satu FDT gagal: FDT tetap muncul di panel, laporan, KMZ dan CSV sebagai
    'Perlu dirancang manual' - tidak boleh hilang diam-diam dari daftar."""
    F = fdt["ll"]
    pop = pilih_pop(F, data, maks_m=prm["pop_maks_m"]) if data is not None else None
    h = {"fdt": fdt, "pop": pop, "jarak_pop_m": round(geo.haversine(F, pop["ll"])) if pop else 0, "peringatan": [],
         "kandidat": [], "keputusan": "PERLU_MANUAL", "terpilih": None, "feeder_baru": None, "n_kabel_diperiksa": 0,
         "n_kandidat_kapasitas": 0, "ada_jalan": False, "lokal": (F[0], F[1]),
         "alasan": [T("Tembuku belum bisa menganalisis FDT ini (%s), jadi perlu dirancang manual.",
                      "Tembuku could not analyse this FDT (%s). Design this FDT by hand.") % galat]}
    try:
        h["penomoran"] = penomoran(h, data)
    except Exception:       # penomoran juga gagal: tetap tampilkan FDT dengan nomor kosong
        h["penomoran"] = {"pop_folder": pop["nama"] if pop else "POP", "feeder": 0, "t": 0, "baru": False}
    return h


def bbox_jalan(F, pop, prm, margin=1500.0):
    """Area data jalan untuk satu FDT: radius pencarian di sekitar FDT + koridor ke POP (margin 1,5 km)."""
    bj = geo.Lokal(F[0], F[1]).bbox_deg(prm["radius_cari_m"])
    for q in [F] + ([pop["ll"]] if pop else []):
        b2 = geo.Lokal(q[0], q[1]).bbox_deg(margin)
        bj = (min(bj[0], b2[0]), min(bj[1], b2[1]), max(bj[2], b2[2]), max(bj[3], b2[3]))
    return bj


def _arah(G, v, kid, prevB, u, L, pop):
    """cos sudut antara arah kabel di v (menjauhi POP) dan arah POP->FDT."""
    if u is None:
        return None, "tanpa POP"
    if prevB is not None and prevB[v] is not None:
        a = G.xy[prevB[v][0]]
        b = G.xy[v]
        if a != b:
            s = geo.satuan(a, b)
            return s[0] * u[0] + s[1] * u[1], "jalur kabel dari POP"
    # cadangan geometris: tetangga di kabel yang sama, arah dari yang lebih dekat POP ke yang lebih jauh
    P = L.ke(pop["ll"])
    nb = [w for w, _L, _c, j, r in G.adj[v] if j == "KABEL" and r == kid]
    if not nb:
        return None, "tidak diketahui"
    w = min(nb, key=lambda w: math.hypot(G.xy[w][0] - P[0], G.xy[w][1] - P[1]))
    s = geo.satuan(G.xy[w], G.xy[v])
    return s[0] * u[0] + s[1] * u[1], "geometri kabel (tidak terbukti tersambung ke POP)"


def _bagian_di_koridor(titik, garis, tol=15.0):
    """Bagian (0..1) panjang jalur 'titik' yang berada <= tol m dari salah satu polyline 'garis'."""
    if not garis or len(titik) < 2:
        return 0.0
    pts = geo.rapatkan(titik, 25.0)
    if not pts:
        return 0.0
    kena = 0
    kotak = []      # kotak batas tiap garis dihitung sekali saja (sebelumnya diulang untuk setiap titik)
    for xy in garis:
        if len(xy) < 2:
            continue
        xs = [q[0] for q in xy]
        ys = [q[1] for q in xy]
        kotak.append((min(xs) - tol, max(xs) + tol, min(ys) - tol, max(ys) + tol, xy))
    for p in pts:
        x, y = p[0], p[1]
        for x0, x1, y0, y1, xy in kotak:
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if geo.dekat_garis(p, xy, tol):
                kena += 1
                break
    return kena / float(len(pts))


def _closure_di_jalur(colo_xy, titik_feeder_xy, tol=10.0):
    """Jumlah closure/slack existing yang dilewati jalur feeder POP->titik sambung (tiap closure = satu sambungan)."""
    if not colo_xy or len(colo_xy) < 2 or not titik_feeder_xy:
        return 0
    n = 0
    for q in titik_feeder_xy:
        if geo.dekat_garis(q, colo_xy, tol):
            n += 1
    return n


def _nilai_kandidat(G, k, pilihan, prevA, distB, prevB, prm, P, byid, tanda, koridor_feeder, data, L):
    c, v, cosv, searah, lurus, sumber_arah = pilihan
    rute = _rakit_rute(G, prevA, v, byid, prm["faktor_garis_bantu"])
    pjg = rute["panjang_m"]
    detour = pjg / lurus if lurus > 20 else 1.0
    pjg_est = rute["panjang_est_m"]
    colo_m = None
    colo_xy = []
    colo_gambar = None
    if prevB is not None and distB[v] < INF:
        jl = G.jalur(prevB, v)
        colo_xy = [G.xy[n] for n, _j, _r in jl]
        colo_m = geo.panjang(colo_xy)
        # GAMBAR COLO CABLE mengikuti kabel feeder itu sendiri dari POP sampai titik sambung, bukan kabel lain yang
        # kebetulan lebih pendek (Tomohon: 3 km numpang kabel inventaris jaringan lain). Hanya untuk gambar: jarak,
        # redaman dan biaya tetap dari jalur terpendek (uji sembunyikan-satu Palembang: memakai jalur feeder sendiri
        # untuk keputusan menurunkan kecocokan 48 -> 41 dari 60 karena data feeder di compile sering tidak lengkap).
        me = byid.get(k.get("id")) or {}
        if me.get("sumber") == "COMPILE" and me.get("feeder") is not None:
            kunci = (me.get("pop_folder"), str(me.get("feeder")))
            cache = G.__dict__.setdefault("_jalur_feeder", {})
            if kunci not in cache:
                refs = {i for i, kb in byid.items() if kb.get("sumber") == "COMPILE"
                        and (kb.get("pop_folder"), str(kb.get("feeder"))) == kunci}
                src = jl[0][0]
                cache[kunci] = G.dijkstra(src, jenis_boleh=("KABEL", "SAMBUNG", "AKSES"), maks=distB[v] * 4 + 1000.0,
                                          kabel_boleh=refs)
            d2, p2 = cache[kunci]
            if d2[v] < INF:
                xy2 = [G.xy[n] for n, _j, _r in G.jalur(p2, v)]
                m2 = geo.panjang(xy2)
                if m2 <= 1.5 * colo_m + 50.0:
                    colo_gambar = xy2
    st, bebas, teks, info = k["kap"]
    info = dict(info or {})
    if colo_m is not None:
        feeder_km = colo_m / 1000.0
    elif P is not None:
        feeder_km = prm["faktor_jalur_feeder"] * math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) / 1000.0
    else:
        feeder_km = 5.0
    alasan, gagal = [], []
    jalur_serat = (colo_m if colo_m is not None else feeder_km * 1000.0) + pjg_est
    core = k.get("core") or 0
    core_cabang = int(prm["core_cabang"])
    fe = _angka_feeder(k.get("feeder"))
    koridor = None
    if k["sumber"] == "COMPILE" and fe is not None:
        koridor = _bagian_di_koridor(rute["titik"], koridor_feeder.get((k.get("pop_nama"), fe), []))
    # aturan jarak 48/96 (PDF 3.1; batas 4 km sejak arahan 18-11-2026, dulu 6 km): cabang 48F hanya bila jalur
    # POP->FDT <= batas; lebih jauh lewat kabel 96F (T1-T8), dan
    # kabel baru yang ditarik ke FDT juga 96 core (seperti plugin acuan v0.10.7: kelas kabel dari panjang POP-FDT)
    batas_m = float(prm["batas_48f_km"]) * 1000.0
    if jalur_serat > batas_m:
        core_cabang = 96
    if st in ("LOLOS", "PENUH") and info.get("kelompok"):
        if core >= 144 and jalur_serat > batas_m:
            # closure 144: lebih dari 6 km -> harus cabang 96F dari kelompok T1-T8
            if info.get("bebas_lain"):
                info.update({"kelompok": info["kelompok_lain"], "bebas": info["bebas_lain"], "tube": info["bebas_lain"][0]})
                core_cabang = 96
                alasan.append(T("jarak POP ke FDT %s, lebih dari %s, jadi dipakai kabel 96 core dari closure 144 (%s)",
                                "the POP-to-FDT route is %s, over %s, so a 96-fibre cable from the closure 144 is used (%s)")
                              % (km(jalur_serat), km(batas_m), _teks_tube(info["bebas"])))
                # kelompok berganti: status dihitung ulang dari tube kosong kelompok 96F (termasuk kebutuhan proyek)
                cukup = len(info["bebas"]) >= prm["cadangan_tube"] + int(info.get("butuh") or prm["tube_per_fdt"])
                if st == "PENUH" and cukup:
                    st = "LOLOS"
                elif st == "LOLOS" and not cukup:
                    st = "PENUH"
                    teks = T("hanya %d tube kosong di jalur 96F (%s), proyek ini butuh %d",
                             "only %d free tube(s) on the 96F path (%s), this project needs %d") % (
                        len(info["bebas"]), _teks_tube(info["bebas"]), int(info.get("butuh") or 1))
            else:
                gagal.append(T("jarak POP ke FDT %s, lebih dari %s, sehingga perlu kabel 96 core, tetapi tube T1-T8 "
                               "feeder ini sudah penuh",
                               "the POP-to-FDT route is %s, over %s, so a 96-fibre cable is needed, but this feeder's "
                               "tubes T1-T8 are full") % (km(jalur_serat), km(batas_m)))
        elif info.get("kelompok") == "48F" and jalur_serat > batas_m:
            gagal.append(T("jarak POP ke FDT lewat kabel 48 core ini %s, lebih dari batas %s untuk kabel 48 core",
                           "the POP-to-FDT route via this 48-fibre cable is %s, over the %s limit for 48 fibres")
                         % (km(jalur_serat), km(batas_m)))
    # arahan revisi 23-11-2026 (PRIORITAS): ukuran kabel baru mengikuti JUMLAH TUBE YANG DIBAWA kabel itu - kabel 48 core
    # = 4 tube, 96 core = 8 tube: sampai batas_tube_kabel_48 tube -> 48, lebih -> 96. Kabel FDT pertama sebuah proyek
    # membawa tube seluruh proyek (kebutuhan 'butuh'). Aturan jarak di atas tetap memilih jalur tube (48F hanya sampai
    # batas_48f_km) dan ukuran kabel feeder baru. (Tafsiran 'sisa tube kosong di feeder' ditinggalkan: Gorontalo TEST 2
    # memberi 96 core untuk FDT 1 tube.)
    core_dari = "JARAK"
    if prm.get("kabel_dari_sisa_tube", True) and st in ("LOLOS", "BELUM_TERVERIFIKASI", "PENUH"):
        n_bawa = max(1, int(info.get("butuh") or prm.get("tube_per_fdt", 1)))
        core_cabang = 48 if n_bawa <= int(prm.get("batas_tube_kabel_48", 4)) else 96
        core_dari = "TUBE"
        info["tube_dibawa"] = n_bawa
    if st == "PENUH":
        gagal.append(T("tidak ada tube kosong. %s", "no free tube. %s") % teks)
    elif st == "BELUM_TERVERIFIKASI":
        alasan.append(T("sisa tube belum bisa dipastikan (%s): cek di lapangan",
                        "free tubes cannot be confirmed (%s): check on site") % teks)
    if not searah:
        gagal.append(T("feeder ini berjalan menjauhi FDT (arahnya melenceng %d°, paling banyak %d°)",
                       "this feeder runs away from the FDT (%d° off, at most %d°)") % (
            round(math.degrees(math.acos(max(-1.0, min(1.0, cosv))))) if cosv is not None else 180,
            round(math.degrees(math.acos(max(-1.0, min(1.0, prm["cos_arah_min"])))))))
    # arahan finalisasi: FDT di utara POP memakai feeder yang keluar ke utara dari POP, FDT di selatan feeder ke selatan.
    # Sisi feeder = posisi titik sambungnya terhadap POP (bagian feeder yang benar-benar dipakai). Jalur awal di dekat
    # POP tidak dipakai: banyak feeder keluar POP sedikit ke selatan lalu berbelok ke utara (Palembang).
    # Koordinat lokal berpusat di FDT, jadi utara-selatan FDT terhadap POP = -P[1].
    if prm.get("arah_utara_selatan", True) and P is not None:
        tol = float(prm.get("toleransi_utara_selatan_m", 150.0))
        dy_fdt = -P[1]
        dy_feeder = G.xy[v][1] - P[1]
        if abs(dy_fdt) > tol and abs(dy_feeder) > tol and dy_fdt * dy_feeder < 0:
            gagal.append(T("FDT ada di %s POP, tetapi feeder ini keluar ke arah %s dari POP (arahan: FDT di utara memakai "
                           "feeder ke utara, FDT di selatan feeder ke selatan)",
                           "the FDT is %s of the POP but this feeder leaves the POP to the %s (rule: an FDT in the north "
                           "uses a feeder going north, an FDT in the south a feeder going south)")
                         % ((T("utara", "north"), T("selatan", "south")) if dy_fdt > 0 else
                            (T("selatan", "south"), T("utara", "north"))))
    di_pop = P is not None and math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) <= JARAK_POP_M
    # aturan jarak juga menentukan kelompok: <= batas cabang 48F (T9-T12), > batas kabel 96F (T1-T8)
    perlu = "48F" if jalur_serat <= batas_m else "96F"
    sesuai = not info.get("kelompok") or info["kelompok"] == perlu
    if not sesuai and prm.get("utamakan_aturan_6km", False):
        alasan.append(T("menurut aturan %s, FDT sejauh %s dari POP sebaiknya memakai tube jalur %s, sedangkan kabel ini "
                        "jalur %s", "by the %s rule an FDT %s from the POP should use the %s tubes; this cable is on "
                        "the %s path") % (km(batas_m), km(jalur_serat), perlu, info["kelompok"]))
    if (core >= 144 or di_pop) and koridor is not None and koridor < prm["koridor_min"]:
        gagal.append(T("cabang baru dari closure 144 Feeder %d hampir tidak melewati jalur tiang Feeder %d sendiri "
                       "(hanya %d%%, paling sedikit %d%%), jadi arah feeder ini tidak cocok dengan lokasi FDT",
                       "a new branch from the closure 144 of Feeder %d hardly follows Feeder %d's own pole line "
                       "(only %d%%, at least %d%%), so this feeder's direction does not fit the FDT") % (
            fe or 0, fe or 0, round(100 * koridor), round(100 * prm["koridor_min"])))
    # selisih kurang dari satu bentang tiang bukan 'berbelok' (uji geser 23-11-2026: kabel 53 m vs lurus 34 m ditolak,
    # FDT lalu ditarik 3,2 km ke feeder lain)
    if lurus < prm["detour_lurus_maks_m"] and detour > prm["detour_maks"] and pjg - lurus > DETOUR_LEBIH_MIN_M:
        gagal.append(T("kabel barunya terlalu berbelok: %s jarak lurus (paling banyak %s)",
                       "the new cable winds too much: %s the straight distance (at most %s)") % (
            kali(detour), kali(prm["detour_maks"])))
    if pjg > prm["cabang_maks_m"]:
        gagal.append(T("kabel barunya terlalu panjang: %s (paling panjang %s)",
                       "the new cable is too long: %s (at most %s)") % (m(pjg), m(prm["cabang_maks_m"])))
    if colo_m is None:
        alasan.append(T("di data, feeder ini belum terlihat tersambung ke POP: pastikan di lapangan",
                        "in the data this feeder is not shown as connected to the POP: confirm on site"))
    # sambungan: OTB di POP, closure existing yang dilewati, closure di titik sambung, FDT
    tf_xy = []
    if k["sumber"] == "COMPILE" and fe is not None and data is not None:
        tf_xy = [L.ke(tf["ll"]) for tf in data.titik_feeder(k.get("pop_nama") or "", fe) if tf["jenis"] == "closure"]
    splice = 3 + _closure_di_jalur(colo_xy, tf_xy)
    bud = link_budget(feeder_km + pjg / 1000.0, prm, splice=splice)
    # nilai komponen = nilai MAKSIMUM standar (kasus terburuk); margin cadangan kebijakan hanya syarat tolak bila diatur
    batas_tolak = 0.0 if prm.get("margin_wajib", False) else -float(prm["margin_db"])
    if bud["margin_db"] < batas_tolak:
        gagal.append(T("sinyal terlalu lemah saat sampai di pelanggan (redaman %s, batas %s)",
                       "the signal would be too weak at the customer (loss %s, limit %s)") % (
            db(bud["total_db"]), db(prm["kelas_olt_db"])))
    tap_slack = tanda.get(v)
    if tap_slack is None and k["sumber"] == "COMPILE" and fe is not None and data is not None:
        # titik sambung bebas: adakah slack/closure feeder ini dalam tap_slack_m (dari kabel mana pun)?
        dekat = None
        for tf in data.titik_feeder(k.get("pop_nama") or "", fe):
            d = math.hypot(*[a - b for a, b in zip(L.ke(tf["ll"]), G.xy[v])])
            if d <= prm["tap_slack_m"] and (dekat is None or d < dekat["jarak_m"]):
                dekat = dict(tf, jarak_m=round(d, 1), kabel=k["id"])
        tap_slack = dekat
    if tap_slack is not None and tap_slack["jenis"] == "closure":
        # closure: 1 kabel masuk + paling banyak 5 keluar. Kabel feeder yang berujung di closure = 1 lubang, yang
        # lewat menerus = 2 lubang (masuk + keluar); kabel baru FDT ini menambah 1.
        q = L.ke(tap_slack["ll"])
        lubang = 0
        for xy in koridor_feeder.get(("KABEL", k.get("pop_nama"), fe), []):
            if len(xy) < 2:
                continue
            ujung = min(math.hypot(xy[0][0] - q[0], xy[0][1] - q[1]), math.hypot(xy[-1][0] - q[0], xy[-1][1] - q[1]))
            if ujung <= 10.0:
                lubang += 1
            elif geo.terdekat_di_garis(q, xy)[0] <= 10.0:
                lubang += 2
        tap_slack = dict(tap_slack, lubang=lubang)
        if lubang + 1 > int(prm.get("closure_lubang_maks", 6)):
            gagal.append(T("closure existing '%s' sudah penuh (%d lubang kabel terpakai, batas %d)",
                           "the existing closure '%s' is full (%d cable holes in use, limit %d)") % (
                tap_slack["nama"], lubang, int(prm.get("closure_lubang_maks", 6))))
    if tap_slack is not None and tap_slack["jarak_m"] > 5.0:
        alasan.append(T("titik sambung %s m dari %s (5-10 m: perlu dicek di lapangan)",
                        "the tap point is %s m from %s (5-10 m: check on site)") % (
            tap_slack["jarak_m"], label_tap(tap_slack)))
    elif tap_slack is None and k["sumber"] == "COMPILE" and not gagal:
        alasan.append(T("titik sambungnya di tengah kabel, bukan di slack, closure atau ujung kabel yang sudah ada (dalam "
                        "%d m): pastikan ada cadangan kabel di titik ini",
                        "the tap point is mid-cable, not at an existing slack, closure or cable end (within %d m): "
                        "confirm there is spare cable at this point before using it") % prm["tap_slack_m"])
    # rasio colo: bagian jalur kabel baru yang menumpang tiang existing (PDF: higher colo ratio is better)
    tiang = sum(geo.panjang(s[2]) for s in rute["segmen"] if s[0] in (TIANG_NASIONAL, TIANG_COMPILE))
    colo_rasio = (tiang / pjg) if pjg > 1.0 else 1.0
    # biaya relatif (evaluasi atasan 16-11-2026): colo cable 1, colo pole 20, new infra 100 per meter
    infra_baru = max(0.0, pjg_est - tiang)
    biaya_rel = ((colo_m if colo_m is not None else feeder_km * 1000.0) * float(prm.get("biaya_colo_cable", 1.0)) +
                 tiang * float(prm.get("biaya_colo_pole", 20.0)) + infra_baru * float(prm.get("biaya_new_infra", 100.0)))
    skor = biaya_rel * (1.0 + (0.5 if st == "BELUM_TERVERIFIKASI" else 0) + (0.3 if colo_m is None else 0) +
                (1.0 if gagal else 0))
    llk = k["ll"]
    if len(llk) > 400:
        llk = llk[::int(math.ceil(len(llk) / 400.0))] + [llk[-1]]
    fisik = k["id"]
    if k["sumber"] == "NASIONAL":
        fisik = "B" + str(k["id"])[1:].split("_")[0] + "|" + str(k.get("nama") or "")
    nama = k.get("nama") or k.get("traksi") or ""
    if k["sumber"] == "COMPILE" and fe is not None and core:
        nama = "Feeder %d - %dC (%s)" % (fe, core, str(k.get("traksi") or "")[:14].rstrip("_"))
    return {"ll_kabel": llk, "id": k["id"], "fisik": fisik, "sumber": k["sumber"], "nama": nama,
            "model": k.get("model"), "owner": k.get("owner"), "product": k.get("product"), "core": k.get("core"),
            "spare": k.get("spare"), "kapasitas": st, "tube_bebas": bebas, "ket_kapasitas": teks, "kap_info": info,
            "label_colo": label_colo(k), "feeder": k.get("feeder"), "feeder_int": fe, "pop_folder": k.get("pop_folder"),
            "pop_nama": k.get("pop_nama"), "traksi": k.get("traksi"), "grup": k.get("grup"), "tap_simpul": v,
            "cos": None if cosv is None else round(cosv, 2), "sumber_arah": sumber_arah, "searah": searah,
            "lurus_m": round(lurus), "kabel_baru_m": round(pjg), "detour": round(detour, 2),
            "colo_m": None if colo_m is None else round(colo_m), "colo_xy": colo_xy, "colo_gambar_xy": colo_gambar, "jalur_serat_m": round(jalur_serat),
            "rute": rute, "budget": bud, "gagal": gagal, "catatan": alasan, "skor": skor, "koridor_sendiri": koridor,
            "tap_slack": tap_slack, "core_cabang": core_cabang, "core_dari": core_dari,
            "lolos": not gagal and st == "LOLOS", "biaya": c,
            "kelompok_sesuai": sesuai, "di_pop": di_pop, "colo_rasio": round(colo_rasio, 3),
            "biaya_relatif": round(biaya_rel), "colo_pole_m": round(tiang), "new_infra_m": round(infra_baru)}


def info_route(G, byid, L, bagian_xy, tol=12.0, langkah=10.0, min_m=30.0, celah_m=30.0):
    """Informasi Route Existing (arahan 18-11-2026): kabel inventaris existing yang dilalui garis yang DIGAMBAR (COLO
    CABLE POP->titik sambung, lalu kabel baru ke FDT). Garis ditelusuri tiap 'langkah' m; titik dianggap menumpang kabel
    inventaris bila berjarak <= tol (satu tiang/koridor, seperti sambung_kabel_m). Beberapa kabel sering berbagi satu
    jalur tiang, jadi di tiap titik dipilih kabel yang menemani rute paling panjang (lalu kabel titik sebelumnya, lalu
    nama) - daftarnya pendek dan stabil, tidak berpindah-pindah antar kabel paralel. Potongan < min_m dibuang, potongan
    kabel yang sama yang terputus <= celah_m disambung. Urutan = urutan di sepanjang rute.
    bagian_xy: [(bagian, [xy lokal])]. -> [{nama, descr2, bagian, model, owner, product, panjang_m, ll}]."""
    nasional = {r for r, k in byid.items() if k.get("sumber") == "NASIONAL" and k.get("xy")}
    if not nasional:
        return []

    def kunci_dari(k):      # satu kabel = NAME + DESCR2 (potongan indeks dari kabel yang sama digabung)
        return (str(k.get("nama") or "").strip() or "-", str(k.get("descr2") or "").strip() or "-")
    titik = []              # [(bagian, xy, {kunci: ref})] - kabel inventaris dalam toleransi di tiap titik
    cakupan = {}
    for bagian, xy in bagian_xy:
        if not xy or len(xy) < 2:
            continue
        pts = geo.rapatkan(list(xy), langkah)
        total = max(geo.panjang(pts), 1e-9)
        s = 0.0
        for i, p in enumerate(pts):
            if i:
                s += math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
            f = min(1.0, s / total)         # posisi 0..1 di bagian ini (untuk memindah gambar ke rute yang dirapikan)
            refs = set()
            for _d, j in G.dekat(p, tol + 2 * langkah):
                refs |= G.refs[j] & nasional
            ada = {}
            for r in sorted(refs, key=str):
                kc = kunci_dari(byid[r])
                if kc not in ada and geo.dekat_garis(p, byid[r]["xy"], tol):
                    ada[kc] = r
            for kc in ada:
                cakupan[kc] = cakupan.get(kc, 0) + 1
            titik.append((bagian, p, ada, f))
    pot = []
    kc0 = None
    for bagian, p, ada, f in titik:
        kc = None
        if ada:
            kc = max(ada, key=lambda x: (cakupan[x], x == kc0, x))
        if pot and pot[-1]["kunci"] == kc and pot[-1]["bagian"] == bagian:
            pot[-1]["xy"].append(p)
            pot[-1]["f1"] = f
        else:
            if pot and pot[-1]["bagian"] == bagian:
                pot[-1]["xy"].append(p)         # potongan bersambung ujung ke ujung (tanpa celah di peta)
                pot[-1]["f1"] = f
            pot.append({"kunci": kc, "k": byid[ada[kc]] if kc else None, "bagian": bagian, "xy": [p], "f0": f, "f1": f})
        kc0 = kc
    # potongan pendek (lompatan antar kabel paralel) dibuang, lalu kabel sama yang terpisah celah pendek disambung
    pot = [x for x in pot if x["kunci"] is None or geo.panjang(x["xy"]) >= min_m]
    gab = []
    for x in pot:
        if x["kunci"] is None:
            if gab:
                gab[-1]["_celah"] = gab[-1].get("_celah", []) + x["xy"]
            continue
        if gab and gab[-1]["kunci"] == x["kunci"] and gab[-1]["bagian"] == x["bagian"] and \
                geo.panjang(gab[-1].get("_celah", [])) <= celah_m:
            gab[-1]["xy"].extend(x["xy"])
            gab[-1]["f1"] = x["f1"]
            gab[-1].pop("_celah", None)
            continue
        if gab:
            gab[-1].pop("_celah", None)
        gab.append(x)
    out = []
    for x in gab:
        pjg = geo.panjang(x["xy"])
        if pjg < min_m or len(x["xy"]) < 2:
            continue
        k = x["k"]
        out.append({"nama": x["kunci"][0], "descr2": x["kunci"][1], "bagian": x["bagian"],
                    "model": k.get("model") or "", "owner": k.get("owner") or "", "product": k.get("product") or "",
                    "panjang_m": round(pjg), "ll": [L.balik(p) for p in x["xy"]], "f0": x["f0"], "f1": x["f1"]})
    return out


def _potong_xy(xy, f0, f1):
    """Potongan garis xy dari posisi f0 sampai f1 (0..1 sepanjang garis)."""
    if not xy or len(xy) < 2:
        return []
    cum = [0.0]
    for a, b in zip(xy, xy[1:]):
        cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cum[-1]
    if total <= 0:
        return []
    s0, s1 = max(0.0, min(f0, f1)) * total, min(1.0, max(f0, f1)) * total

    def di(s):
        for i in range(len(xy) - 1):
            if cum[i] <= s <= cum[i + 1]:
                d = cum[i + 1] - cum[i]
                t = 0.0 if d <= 0 else (s - cum[i]) / d
                return (xy[i][0] + t * (xy[i + 1][0] - xy[i][0]), xy[i][1] + t * (xy[i + 1][1] - xy[i][1])), i
        return xy[-1], len(xy) - 2
    p0, i0 = di(s0)
    p1, i1 = di(s1)
    return [p0] + [xy[i] for i in range(i0 + 1, i1 + 1)] + [p1]


def _geser_info_route(daftar, peta, L):
    """Informasi Route Existing dipindah ke gambar rute yang sudah dirapikan: kabel inventarisnya tetap hasil pencocokan
    dengan data asli, garisnya dipotong dari rute baru pada posisi yang sama (seperti keterangan COLO CABLE)."""
    for d in daftar or []:
        xy = peta.get(d.get("bagian"))
        if not xy or "f0" not in d:
            continue
        seg = _potong_xy(xy, d["f0"], d["f1"])
        if len(seg) >= 2:
            d["ll"] = [L.balik(p) for p in seg]
            d["panjang_m"] = round(geo.panjang(seg))


def label_colo_kabel(k):
    """Keterangan COLO CABLE dari kabel yang dilalui (arahan atasan 18-11-2026): kabel feeder compile ->
    'Colo Cable F6 Feeder Perumahan karlia asri' (nomor feeder + nama cluster traksi pemilik kabel itu); kabel
    inventaris -> 'Colo Cable <NAME> (<DESCR2>)'."""
    if k.get("sumber") == "COMPILE":
        fe = _angka_feeder(k.get("feeder"))
        area = str(k.get("area") or "").strip()
        if not area:
            area = re.sub(r"\.km[lz]$", "", str(k.get("traksi") or ""), flags=re.I)
        return ("Colo Cable F%d Feeder %s" % (fe, area)) if fe is not None else ("Colo Cable %s" % area)
    nama = str(k.get("nama") or "").strip() or "-"
    d2 = str(k.get("descr2") or "").strip()
    return "Colo Cable %s%s" % (nama, " (%s)" % d2 if d2 and d2 != nama else "")


def colo_route(G, byid, xy, fe_pakai=None, pop_pakai=None, label_awal=None, tol=30.0, langkah=10.0, min_m=60.0):
    """Arahan atasan 18-11-2026: keterangan COLO CABLE mengikuti rute kabel feeder yang dilalui; bila melewati lebih
    dari satu cluster, garisnya dipecah per cluster sesuai urutan rute. Serat colo secara fisik selalu di kabel feeder
    yang dipakai, jadi yang boleh disebut hanya kabel compile (cluster/traksi) DARI FEEDER ITU; kabel inventaris
    existing dicantumkan terpisah di folder 'Informasi Route Existing'. Garis COLO CABLE yang digambar (POP -> titik
    sambung) ditelusuri tiap 'langkah' m dan dicocokkan dengan kabel feeder itu dalam 'tol' m (garis compile buatan
    desainer tidak selalu tepat di jalur tiang); di jalur bersama dipilih cluster yang menemani rute paling panjang.
    Bagian yang tidak terlacak dan potongan < min_m ikut potongan sebelumnya (garis tidak berlubang).
    -> [{label, s0, s1}] dengan s0/s1 = posisi (0..1) di sepanjang garis."""
    if not xy or len(xy) < 2:
        return []
    from . import sumber

    def milik_feeder(k):
        if k.get("sumber") != "COMPILE" or k.get("koridor") or k.get("jenis") != "NEW_CABLE" or not k.get("xy"):
            return False
        if fe_pakai is None:
            return True
        if _angka_feeder(k.get("feeder")) != fe_pakai:
            return False
        a, b = str(k.get("pop_folder") or ""), str(pop_pakai or "")
        return not b or a == b or sumber.kunci_pop(a) == sumber.kunci_pop(b)
    calon = {r for r, k in byid.items() if milik_feeder(k)}
    if not calon:
        return [{"label": label_awal, "s0": 0.0, "s1": 1.0}] if label_awal else []
    pts = geo.rapatkan(list(xy), langkah)
    jarak = [0.0]
    for a, b in zip(pts, pts[1:]):
        jarak.append(jarak[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = jarak[-1]
    if total <= 0:
        return []
    per_titik, cakupan, info_label = [], {}, {}
    for p in pts:
        refs = set()
        for _d, j in G.dekat(p, tol + 2 * langkah):
            refs |= G.refs[j] & calon
        ada = {}
        for r in sorted(refs, key=str):
            k = byid[r]
            lab = label_colo_kabel(k)
            if lab not in ada and geo.dekat_garis(p, k["xy"], tol):
                ada[lab] = r
                info_label[lab] = (k.get("sumber") == "COMPILE", fe_pakai is not None and
                                   _angka_feeder(k.get("feeder")) == fe_pakai)
        for lab in ada:
            cakupan[lab] = cakupan.get(lab, 0) + 1
        per_titik.append(ada)
    runs = []          # [label, jarak awal, jarak akhir]
    lab0 = None
    for i, ada in enumerate(per_titik):
        lab = None
        if ada:
            lab = max(ada, key=lambda x: (info_label[x][0], info_label[x][1], cakupan[x], x == lab0, x))
        if lab is None:
            lab = lab0                     # bagian tanpa kabel: ikut potongan sebelumnya
        if runs and runs[-1][0] == lab:
            runs[-1][2] = jarak[i]
        else:
            if runs:
                runs[-1][2] = jarak[i]
            runs.append([lab, jarak[i], jarak[i]])
        lab0 = lab
    if runs:
        runs[-1][2] = total
    if runs and runs[0][0] is None and len(runs) > 1:      # awal garis tanpa kabel: ikut potongan berikutnya
        runs[1][1] = 0.0
        runs.pop(0)
    if runs and runs[0][0] is None:                        # tidak ada yang terlacak: satu garis, label feeder dipakai
        runs[0][0] = label_awal
    # potongan pendek (lompatan antar kabel paralel) digabung ke potongan sebelumnya, lalu label sama disatukan
    rapi = []
    for r in runs:
        if rapi and (r[2] - r[1] < min_m or r[0] is None or r[0] == rapi[-1][0]):
            rapi[-1][2] = r[2]
        else:
            rapi.append(list(r))
    if len(rapi) > 1 and rapi[0][2] - rapi[0][1] < min_m:
        rapi[1][1] = rapi[0][1]
        rapi.pop(0)
    gab = []
    for r in rapi:
        if gab and gab[-1][0] == r[0]:
            gab[-1][2] = r[2]
        else:
            gab.append(r)
    return [{"label": r[0], "s0": round(r[1] / total, 6), "s1": round(r[2] / total, 6)} for r in gab if r[0]]


def isi_route_existing(h, G, byid, L, prm=None):
    """Isi 'route_existing' dan 'colo_route' untuk setiap kandidat (dipakai juga bila desainer memilih kandidat lain di
    panel) dan untuk feeder baru. Route existing opsional (tulis_route_existing, 23-11-2026): bila tidak dipilih,
    pencocokan ke inventaris dilewati seluruhnya; keterangan COLO CABLE per cluster tetap dihitung."""
    pakai = bool((prm or {}).get("tulis_route_existing", True))
    for k in h.get("kandidat") or []:
        colo = k.get("colo_gambar_xy") or k.get("colo_xy") or []
        k["route_existing"] = info_route(G, byid, L, [("POP - titik sambung", colo),
                                                      ("kabel baru", (k.get("rute") or {}).get("titik") or [])]) \
            if pakai else []
        sendiri = byid.get(k.get("id")) or {}
        awal = label_colo_kabel(sendiri) if sendiri.get("sumber") == "COMPILE" else None
        k["colo_route"] = colo_route(G, byid, colo, k.get("feeder_int"), k.get("pop_folder"), awal)
    fb = h.get("feeder_baru")
    if fb:
        fb["route_existing"] = info_route(G, byid, L, [("kabel baru", fb.get("titik") or [])]) if pakai else []


def _cg_nama(jenis, inggris=False):
    from . import cek_gambar
    return (cek_gambar.NAMA_EN if inggris else cek_gambar.NAMA).get(jenis, jenis)


def _dekat_jalan(G, p, r):
    """Simpul jalan (bukan simpul kabel) terdekat dalam r meter -> (jarak, simpul) atau None."""
    d = G.dekat(p, r, lambda j: not G.refs[j] and any(e[3] == "JALAN" for e in G.adj[j]))
    return d[0] if d else None


def ikuti_jalan(G, xy, min_m=300.0, faktor=1.4, tambah_m=40.0, ujung_m=60.0, dekat=None):
    """1.6.0 - perbaiki GAMBAR data existing yang salah bentuk. Kabel compile/inventaris kadang digambar dengan bentang
    lurus ratusan meter sampai 1,5 km yang memotong rumah (Jambi F7: 1.496 m lurus dari OTB). Bentang tiang nyata
    40-50 m, jadi bentang lurus >= min_m adalah gambar yang disederhanakan, bukan jalur kabelnya. Bentang seperti itu
    digambar ulang mengikuti jalan di antara kedua ujungnya, bila jalan itu tidak jauh lebih panjang (<= faktor x lurus
    + tambah_m). Bentang yang memang sudah menempel jalan lurus dibiarkan. Hanya gambar: keputusan, biaya dan redaman
    tetap dihitung dari data aslinya.
    -> (xy baru, panjang bentang lurus yang diganti, panjang bentang lurus yang tidak bisa diganti)."""
    from .tulis_kmz import rapikan_garis
    p = rapikan_garis(xy) if len(xy) > 2 else list(xy)
    if len(p) < 2:
        return list(xy), 0.0, 0.0
    out, ganti, sisa = [p[0]], 0.0, 0.0
    for a, b in zip(p, p[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d < min_m:
            out.append(b)
            continue
        n = max(2, int(d // 30.0))
        # dekat jalan = dekat GARIS jalan (dirapatkan 10 m), sama dengan pemeriksaan input (cek_gambar.JalanDekat);
        # bukan dekat titik sudut jalan, yang di jalan lurus bisa ratusan meter jaraknya
        uji = dekat if dekat is not None else (lambda p: _dekat_jalan(G, p, 15.0))
        kena = sum(1 for i in range(1, n) if uji((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)))
        if kena >= 0.8 * (n - 1):           # bentang lurus di sepanjang jalan lurus: sudah benar
            out.append(b)
            continue
        ja, jb = _dekat_jalan(G, a, ujung_m), _dekat_jalan(G, b, ujung_m)
        baru = None
        if ja and jb and ja[1] != jb[1]:
            batas = faktor * d + tambah_m
            dist, prev = G.dijkstra(ja[1], jenis_boleh=("JALAN",), maks=batas * 2.0)
            if dist[jb[1]] < INF:
                jl = [G.xy[s] for s, _j, _r in G.jalur(prev, jb[1])]
                if ja[0] + geo.panjang(jl) + jb[0] <= batas:
                    baru = jl
        if baru:
            out.extend(baru)
            out.append(b)
            ganti += d
        else:
            out.append(b)
            sisa += d
    if ganti:
        out = rapikan_garis(out, taji_m=60.0)      # taji kecil di sambungan ujung bentang - jalan
    return out, ganti, sisa


def rapikan_gambar_data(h, G, prm, rusak=None, dekat=None, L=None):
    """Terapkan ikuti_jalan pada gambar COLO CABLE dan ruas tiang (compile/nasional) semua kandidat dan feeder baru;
    catat untuk desainer bila gambar diperbaiki atau masih ada bentang lurus panjang yang tidak bisa diperbaiki.
    Dampak (1.6.0): keputusan dihitung dari gambar masukan; bila gambar yang diperbaiki mengikuti jalan membuat jalur serat
    melewati batas kabel 48 core atau menghabiskan cadangan redaman, desainer diberi peringatan keras (keputusan tidak
    diubah otomatis agar hasil tetap stabil dan dapat dilacak ke data masukan)."""
    def ruas(rute):
        g = s = tambah = 0.0
        for sg in rute.get("segmen") or []:
            if sg[0] in (TIANG_NASIONAL, TIANG_COMPILE) and len(sg[2]) >= 2:
                awal = geo.panjang(sg[2])
                sg[2], a, b = ikuti_jalan(G, sg[2], dekat=dekat)
                g, s = g + a, s + b
                if a:
                    tambah += geo.panjang(sg[2]) - awal
        if g:
            titik = []
            for sg in rute["segmen"]:
                titik.extend(sg[2] if not titik else sg[2][1:])
            rute["titik"] = titik
        return g, s, tambah

    for k in h.get("kandidat") or []:
        if k.get("_dirapikan"):
            continue
        k["_dirapikan"] = True
        g = s = tambah = 0.0
        colo = k.get("colo_gambar_xy") or k.get("colo_xy")
        if colo and len(colo) >= 2:
            awal = geo.panjang(colo)
            k["colo_gambar_xy"], g, s = ikuti_jalan(G, colo, dekat=dekat)
            if g:
                tambah = geo.panjang(k["colo_gambar_xy"]) - awal
        if k.get("rute"):
            a, b, c = ruas(k["rute"])
            g, s, tambah = g + a, s + b, tambah + c
        k["gambar_diperbaiki_m"], k["gambar_lurus_m"], k["gambar_tambah_m"] = round(g), round(s), round(max(0.0, tambah))
        if g and L is not None:
            _geser_info_route(k.get("route_existing"), {"POP - titik sambung": k.get("colo_gambar_xy") or k.get("colo_xy"),
                                                        "kabel baru": (k.get("rute") or {}).get("titik")}, L)
    fb = h.get("feeder_baru")
    if fb:
        g, s, tambah = ruas(fb)
        fb["gambar_diperbaiki_m"], fb["gambar_lurus_m"], fb["gambar_tambah_m"] = round(g), round(s), round(max(0.0, tambah))
        if g and L is not None:
            _geser_info_route(fb.get("route_existing"), {"kabel baru": fb.get("titik")}, L)
    obj = h.get("terpilih") or (fb if h.get("keputusan") == "FEEDER_BARU" else None)
    if obj and rusak:
        sendiri = [obj.get("id")] if obj is h.get("terpilih") else []
        dipakai = [r for r in dict.fromkeys(sendiri + list((obj.get("rute") or obj).get("ref_kabel") or [])) if r in rusak]
        if dipakai:
            h["pakai_kabel_janggal"] = True
            h["peringatan"].append(T(
                "Salah satu kabel existing yang dipakai gambarnya kurang rapi di data masukan (%s). Kabelnya tetap dipakai "
                "karena tube-nya memang ada; cukup rapikan gambar aslinya di compile atau inventaris. Lokasinya ada di "
                "daftar Pemeriksaan data masukan.",
                "One of the existing cables used here is drawn poorly in the input data (%s). It is still used because "
                "its tubes are real; just tidy the original drawing in the compilation or inventory. The location is in "
                "the input check list.") % gabung(", ", [
                    T(_cg_nama(x["jenis"]), _cg_nama(x["jenis"], True)) for r in dipakai for x in rusak[r]][:3]))
    if obj and obj.get("gambar_tambah_m", 0) >= 50:
        tambah = obj["gambar_tambah_m"]
        js = (obj.get("jalur_serat_m") or obj.get("panjang_est_m") or 0)
        batas = float(prm.get("batas_48f_km", 4.0)) * 1000.0
        core = obj.get("core_cabang") or obj.get("core")
        if core == 48 and obj.get("core_dari", "JARAK") == "JARAK" and js <= batas < js + tambah:
            p = T("Kalau diukur mengikuti jalan, jalur serat dari POP jadi %s, bukan %s seperti di gambar. Itu sudah lewat "
                  "%s, jadi kabelnya seharusnya 96 core (tube T1-T8). Tolong pastikan jalur kabel existing di lapangan.",
                  "Measured along the road, the fibre route from the POP is %s, not %s as drawn. That is past %s, so the "
                  "cable should be 96 fibres (tubes T1-T8). Please check the existing cable route on site.") % (
                km(js + tambah), km(js), km(batas))
            h["peringatan"].insert(0, p)
            h.setdefault("penting", []).append(p)
        mg = (obj.get("budget") or {}).get("margin_db")
        if mg is not None:
            turun = tambah / 1000.0 * float(prm.get("fiber_db_km", 0.40))
            if mg >= 0 > mg - turun:
                p = T("Kalau diukur mengikuti jalan, jalurnya %s lebih panjang dan sisa redaman turun dari %s dB jadi %s dB. "
                      "Cadangannya jadi terpakai, jadi sebaiknya diukur di lapangan.",
                      "Measured along the road, the route is %s longer and the signal margin drops from %s dB to %s dB. "
                      "The reserve gets used, so measure it on site.") % (
                    m(tambah), ("%.1f" % mg).replace(".", ","), ("%.1f" % (mg - turun)).replace(".", ","))
                h["peringatan"].insert(0, p)
                h.setdefault("penting", []).append(p)
    if obj:
        if obj.get("gambar_diperbaiki_m"):
            h["peringatan"].append(T(
                "Di data masukan, sebagian kabel existing digambar sebagai garis lurus panjang yang tidak mengikuti jalan. "
                "Di hasil ini %s di antaranya sudah digambar ulang mengikuti jalan. Cek sebentar apakah kabelnya memang "
                "lewat jalan itu.", "In the input data, part of the existing cable is drawn as long straight lines that "
                "follow no road. In this result %s of it has been redrawn along the road. Take a quick look that the "
                "cable really runs there.") % m(obj["gambar_diperbaiki_m"]))
        if obj.get("gambar_lurus_m", 0) >= 300:
            h["peringatan"].append(T(
                "Masih ada %s garis lurus panjang yang tidak bisa dirapikan karena tidak ada jalan di dekatnya. Kalau di "
                "Google Earth ternyata memotong bangunan, gambar ulang secara manual.",
                "There is still %s of long straight line that could not be tidied because no road is nearby. If it "
                "crosses buildings in Google Earth, redraw it by hand.") % m(obj["gambar_lurus_m"]))


SPAN_TIANG_M = 35.0         # celah New Infra lebih pendek dari satu bentang tiang, di antara dua ruas tiang = tanpa tiang baru
TOL_RENCANA_M = 15.0        # ruas rute sejauh ini dari kabel distribusi rencana = di tiang rencana itu
TOL_TIANG_RENCANA_M = 30.0  # ... atau sejauh ini dari titik tiang rencana distribusi (bentang tiang 40-50 m)


def _dekat_garis(p, garis, tol):
    for g in garis:
        for a, b in zip(g, g[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
            if math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy) <= tol:
                return True
    return False


def label_infra_akhir(h, jalur_ll, tiang_ll=(), prm=None):
    """Setelah keputusan (biaya dan pilihan tidak berubah), perbaiki LABEL infra rute terpilih seperti desainer:
    1) ruas New Infra yang menyusuri kabel distribusi RENCANA cluster ini (tiang FTTH yang dibangun proyek yang sama)
       = 'Colo Pole FTTH' (gambar feeder desainer Gorontalo POP 1: seluruh 2.046 m kabel 48C 'Colo Pole FTTH');
    2) celah New Infra < satu bentang tiang di antara dua ruas tiang = bentangan kabel antar tiang, bukan tiang baru."""
    rutes = []
    for x in (h.get("terpilih"), h.get("feeder_baru")):
        r = (x or {}).get("rute")
        if r and r.get("segmen") and not any(r is y for y in rutes):
            rutes.append(r)
    if not rutes or not h.get("lokal"):
        return
    L = geo.Lokal(*h["lokal"])
    semua = [p for r in rutes for p in r["titik"]]
    x0, x1 = min(p[0] for p in semua) - 50, max(p[0] for p in semua) + 50
    y0, y1 = min(p[1] for p in semua) - 50, max(p[1] for p in semua) + 50
    garis = []
    for g in jalur_ll or ():
        xy = [L.ke(p) for p in g]
        if max(p[0] for p in xy) >= x0 and min(p[0] for p in xy) <= x1 and \
                max(p[1] for p in xy) >= y0 and min(p[1] for p in xy) <= y1:
            garis.append(xy)
    tiang = [q for q in (L.ke(p) for p in tiang_ll or ()) if x0 <= q[0] <= x1 and y0 <= q[1] <= y1]

    def di_rencana(p):
        return _dekat_garis(p, garis, TOL_RENCANA_M) or \
            any(math.hypot(p[0] - q[0], p[1] - q[1]) <= TOL_TIANG_RENCANA_M for q in tiang)
    tiang_kls = (TIANG_COMPILE, TIANG_NASIONAL)
    for r in rutes:
        seg, rencana = [], 0.0
        for kelas, ref, xy in r["segmen"]:
            if kelas not in (NEW_INFRA, GARIS_BANTU) or not (garis or tiang):
                seg.append([kelas, ref, list(xy)])
                continue
            for a, b in zip(xy, xy[1:]):
                n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // 10))
                on = all(di_rencana((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1))
                k = TIANG_COMPILE if on else kelas
                if on:
                    rencana += math.hypot(b[0] - a[0], b[1] - a[1])
                if seg and seg[-1][0] == k and seg[-1][1] is None and seg[-1][2][-1] == a:
                    seg[-1][2].append(b)
                else:
                    seg.append([k, None, [a, b]])
        for i in range(1, len(seg) - 1):
            if seg[i][0] == NEW_INFRA and seg[i - 1][0] in tiang_kls and seg[i + 1][0] in tiang_kls and \
                    geo.panjang(seg[i][2]) < SPAN_TIANG_M:
                seg[i][0] = seg[i - 1][0]
        r["segmen"] = seg
        # angka penjelasan (persen di tiang, 'sisanya perlu tiang baru') ikut label baru; biaya keputusan tidak diubah
        pjg = geo.panjang(r["titik"])
        tiang_m = sum(geo.panjang(s[2]) for s in seg if s[0] in tiang_kls)
        for x in (h.get("terpilih"), h.get("feeder_baru")):
            if x and x.get("rute") is r and "colo_rasio" in x:
                lama = float(x.get("colo_pole_m") or 0)
                p_lama = round(100 * (x.get("colo_rasio") or 0))
                x["colo_pole_m"] = round(tiang_m)
                x["new_infra_m"] = max(0, round(float(x.get("new_infra_m") or 0) - max(0.0, tiang_m - lama)))
                x["colo_rasio"] = round(tiang_m / pjg, 3) if pjg > 1.0 else 1.0
                p_baru = round(100 * x["colo_rasio"])
                if p_baru != p_lama and x is h.get("terpilih"):
                    a = T(", %d%% di tiang yang sudah ada", ", %d%% of it on existing poles")
                    h["alasan"] = [s.replace(a % p_lama, a % p_baru) for s in h["alasan"]]
                if p_baru != p_lama and h.get("penjelasan") is not None:
                    from . import penjelasan as _pj
                    h["penjelasan"] = _pj.susun(h, prm or profil.baru())
        if rencana >= 50 and r is (h.get("terpilih") or {}).get("rute"):
            h["alasan"].append(T("%s dari kabel barunya menumpang tiang rencana distribusi cluster ini, jadi ditulis "
                                 "'Colo Pole FTTH' (bukan New Infra), seperti gambar desainer.",
                                 "%s of the new cable rides the planned distribution poles of this cluster, so it is "
                                 "written as 'Colo Pole FTTH' (not New Infra), as designers draw it.") % m(rencana))


def _rakit_rute(G, prev, tujuan, byid, faktor_bantu=1.35):
    """Jalur dari tujuan (tap/POP) ke FDT dipecah per jenis infrastruktur."""
    jl = G.jalur(prev, tujuan)
    jl.reverse()                                    # tujuan -> FDT
    titik = [G.xy[n] for n, _j, _r in jl]
    seg = []                                        # (kelas, ref, [xy])
    for i in range(1, len(jl)):
        jenis, ref = jl[i - 1][1], jl[i - 1][2]
        k = byid.get(ref) if jenis == "KABEL" else None
        kelas = kelas_infra(k) if jenis == "KABEL" else (GARIS_BANTU if jenis == "BEBAS" else NEW_INFRA)
        a, b = titik[i - 1], titik[i]
        if seg and seg[-1][0] == kelas and seg[-1][1] == (ref if k else None):
            seg[-1][2].append(b)
        else:
            seg.append([kelas, ref if k else None, [a, b]])
    pjg = geo.panjang(titik)
    bantu = sum(geo.panjang(s[2]) for s in seg if s[0] == GARIS_BANTU)
    pemilik = {s[1]: (byid.get(s[1]) or {}).get("owner") for s in seg if s[1]}
    return {"titik": titik, "segmen": seg, "panjang_m": pjg, "ref_kabel": [s[1] for s in seg if s[1]], "pemilik": pemilik,
            "bantu_m": bantu, "panjang_est_m": pjg + bantu * (faktor_bantu - 1.0)}


def link_budget(km, prm, splice=6):
    serat = km * prm["fiber_db_km"]
    total = (serat + prm["splitter_fdt_db"] + prm["splitter_fat_db"] + prm["konektor_n"] * prm["konektor_db"] +
             splice * prm["splice_db"] + prm["margin_db"] + prm["distribusi_km"] * prm["fiber_db_km"])
    return {"km": round(km + prm["distribusi_km"], 2), "total_db": round(total, 2),
            "margin_db": round(prm["kelas_olt_db"] - total, 2) + 0.0, "splice": splice}


def _setara(a, b):
    """Dua kandidat setara bila biaya relatifnya beda <= 5 % (model biaya atasan) atau, tanpa biaya, kabel barunya beda
    < 5 % dan < 100 m."""
    if a.get("biaya_relatif") is not None and b.get("biaya_relatif") is not None:
        return abs(a["biaya_relatif"] - b["biaya_relatif"]) <= TOLERANSI_SETARA * min(a["biaya_relatif"], b["biaya_relatif"])
    return abs(a["kabel_baru_m"] - b["kabel_baru_m"]) <= max(100.0, TOLERANSI_SETARA * min(a["kabel_baru_m"],
                                                                                         b["kabel_baru_m"]))


def _kunci_setara(d):
    """Urutan tetap kandidat setara: titik sambung existing, rasio colo (per 10 %), nomor feeder, kabel baru."""
    return (0 if d.get("tap_slack") else 1, -round(d.get("colo_rasio") or 0.0, 1), d.get("feeder_int") or 999,
            d["kabel_baru_m"], d.get("id") or "")


def _urut_setara(lolos, utamakan=False, prm=None):
    """Urutan kandidat yang lolos, tetap di semua wilayah:
      1. (opsional) kelompok tube sesuai aturan 6 km;
      2. titik sambung di slack, closure atau ujung kabel existing didahulukan bila kabel barunya paling banyak
         toleransi_slack_antar_m (atau 15 %) lebih panjang dari kandidat terbaik - membuka kabel di tengah bentang
         tanpa cadangan kabel lebih sulit dan berisiko (PDF 3.3), jadi selisih kecil itu sepadan, selisih besar tidak;
      3. kandidat dengan kabel baru setara (beda < 5 % dan < 100 m) diurutkan: titik sambung existing, rasio colo,
         nomor feeder terkecil, kabel baru terpendek."""
    if not lolos:
        return lolos
    if utamakan:        # kandidat yang kelompok tubenya sesuai aturan 6 km didahulukan
        a = [d for d in lolos if d.get("kelompok_sesuai", True)]
        b = [d for d in lolos if not d.get("kelompok_sesuai", True)]
        if a and b:
            return _urut_setara(a, False, prm) + _urut_setara(b, False, prm)
    lolos = sorted(lolos, key=lambda d: d["skor"])
    terbaik = lolos[0]
    tol = float((prm or {}).get("toleransi_slack_antar_m", 600))
    # FDT yang sudah menempel di kabel feeder (kabel baru < slack_min_kabel_m) disambung di dekat FDT itu sendiri,
    # seperti desain nyata (mis. PLG1-TPA01-H03: 0 m); prioritas slack hanya untuk cabang yang lebih panjang
    if not terbaik.get("tap_slack") and tol > 0 and \
            terbaik["kabel_baru_m"] >= float((prm or {}).get("slack_min_kabel_m", 150)):
        batas = terbaik["kabel_baru_m"] + max(tol, 0.15 * terbaik["kabel_baru_m"])
        ada = [d for d in lolos if d.get("tap_slack") and d["kabel_baru_m"] <= batas]
        if ada:
            ada.sort(key=lambda d: (d.get("biaya_relatif", d["kabel_baru_m"]), _kunci_setara(d)))
            terbaik = ada[0]
            terbaik["naik_slack"] = True
    setara = [d for d in lolos if _setara(d, terbaik)]
    if terbaik not in setara:
        setara.append(terbaik)
    sisa = [d for d in lolos if d not in setara]
    setara.sort(key=_kunci_setara)
    if terbaik.get("naik_slack") and setara[0] is not terbaik and not setara[0].get("tap_slack"):
        setara.remove(terbaik)
        setara.insert(0, terbaik)
    return setara + sisa


def _alasan_urut(k, x):
    """Kenapa kandidat k didahulukan dari x yang setara (dua bahasa)."""
    if k.get("tap_slack") and not x.get("tap_slack"):
        return T("titik sambungnya di %s", "its tap point is at %s") % label_tap(k["tap_slack"])
    if round(k.get("colo_rasio") or 0, 1) > round(x.get("colo_rasio") or 0, 1):
        return T("jalur kabel barunya lebih banyak menumpang tiang existing (%d%% dibanding %d%%)",
                 "more of its new cable runs on existing poles (%d%% against %d%%)") % (
            round(100 * (k.get("colo_rasio") or 0)), round(100 * (x.get("colo_rasio") or 0)))
    if (k.get("feeder_int") or 999) < (x.get("feeder_int") or 999):
        return T("nomor feedernya lebih kecil", "its feeder number is lower")
    return T("kabel barunya lebih pendek", "its new cable is shorter")


def _ikut_feeder_proyek(lolos, h):
    """FDT kedua dst. dalam satu proyek: kandidat di feeder yang dipakai FDT pertama proyek itu didahulukan (urutan lain
    tetap), supaya satu cluster tidak terpecah ke beberapa feeder."""
    pf = (h.get("fdt") or {}).get("_proyek_feeder")
    if not pf or not lolos:
        return lolos
    from . import sumber

    def sama(k):
        if k.get("feeder_int") != pf.get("feeder"):
            return False
        a, b = str(k.get("pop_folder") or ""), str(pf.get("pop_folder") or "")
        return a == b or sumber.kunci_pop(a) == sumber.kunci_pop(b)
    depan = [k for k in lolos if sama(k)]
    if not depan:
        return lolos
    depan[0].setdefault("catatan", []).append(T(
        "feeder yang sama dengan FDT %s dalam proyek ini, supaya satu cluster tidak terpecah",
        "the same feeder as FDT %s of this project, so one cluster is not split") % pf.get("kode", "-"))
    return depan + [k for k in lolos if not sama(k)]


def _putuskan(h, prm):
    fb = h["feeder_baru"]
    if h["pop"] is None:
        h["keputusan"] = "PERLU_MANUAL"
        h["alasan"].append(T("Tidak ada POP/OLT dalam %s, jadi sisa tube, arah dan redaman sinyal tidak bisa "
                             "dibuktikan. Kandidat di tabel hanya bahan tinjauan: rancang FDT ini secara manual.",
                             "No POP/OLT within %s, so free tubes, direction and signal loss cannot be proven. The "
                             "candidates in the table are for review only: design this FDT by hand.") % km(prm["pop_maks_m"]))
        return
    tolak_memutar = bool(prm.get("tolak_jalur_memutar", False))
    for k in h["kandidat"]:
        k["rasio_jalur"] = round(k["jalur_serat_m"] / fb["panjang_est_m"], 2) if fb and fb["panjang_est_m"] > 0 else None
        k["gagal_lain"] = len(k["gagal"])       # alasan tolak selain 'memutar' (dipakai penentuan zona batas)
        if k["rasio_jalur"] is not None and k["rasio_jalur"] > prm["rasio_jalur_maks"]:
            if tolak_memutar:
                k["gagal"].append(T("jalurnya memutar terlalu jauh: lewat feeder ini totalnya %s, sedangkan feeder baru "
                                    "langsung dari POP hanya %s (paling banyak %s panjangnya)",
                                    "the route goes too far round: through this feeder it is %s in total, while a new "
                                    "feeder straight from the POP is only %s (at most %s as long)") % (
                    km(k["jalur_serat_m"]), km(fb["panjang_est_m"]), kali(prm["rasio_jalur_maks"])))
                k["lolos"] = False
                k["skor"] *= 2.0
            else:
                # arahan atasan 18-11-2026: tube kosong di feeder existing dipakai; jalur panjang hanya dicatat. Feeder
                # yang jalurnya wajar tetap didahulukan (lihat di bawah): feeder yang memutar dipakai hanya bila
                # pilihan lainnya adalah membuat feeder baru
                k["memutar"] = True
                k["catatan"].append(T("jalur lewat feeder ini %s, lebih panjang dari feeder baru langsung dari POP (%s), "
                                      "tetapi feeder ini tetap dipakai karena masih ada tube kosong",
                                      "the route through this feeder is %s, longer than a new feeder straight from the "
                                      "POP (%s), but this feeder is still used because it has a free tube") % (
                    km(k["jalur_serat_m"]), km(fb["panjang_est_m"])))
    lolos = _urut_setara([k for k in h["kandidat"] if k["lolos"]], bool(prm.get("utamakan_aturan_6km", False)), prm)
    lolos = [k for k in lolos if not k.get("memutar")] + [k for k in lolos if k.get("memutar")]
    lolos = _ikut_feeder_proyek(lolos, h)
    lain = [k for k in h["kandidat"] if not k["lolos"]]
    lain.sort(key=lambda d: d["skor"])
    h["kandidat"] = lolos + lain
    near = [k for k in h["kandidat"][:3] if tolak_memutar and k["rasio_jalur"] is not None and
            not k.get("gagal_lain", len(k["gagal"])) and abs(k["rasio_jalur"] - prm["rasio_jalur_maks"]) <= prm["zona_batas"]]
    if near:
        h["batas"] = True
        h["peringatan"].append(T("Dua pilihan hampir sama bagusnya: memakai feeder %s, atau membuat feeder baru (jalur lewat "
                                 "feeder ini %s panjang feeder baru, batasnya %s). Sebaiknya lihat keduanya dulu.",
                                 "Two options are almost equally good: using feeder %s, or building a new feeder (the "
                                 "route through this feeder is %s a new feeder, the limit is %s). Worth looking at "
                                 "both.") % (near[0]["nama"] or near[0]["id"], kali(near[0]["rasio_jalur"]),
                                                 kali(prm["rasio_jalur_maks"])))
    cek = [k for k in h["kandidat"] if not k["gagal"] and k["kapasitas"] == "BELUM_TERVERIFIKASI"]
    if lolos:
        k = lolos[0]
        h["keputusan"], h["terpilih"] = "COLO", k
        inf = k.get("kap_info") or {}
        bud = k.get("budget") or {}
        h["alasan"].append(T("%s masih punya tube kosong, arahnya menuju FDT, dan sinyal sampai pelanggan masih aman "
                             "(redaman %s dari batas %s, di luar cadangan %s).",
                             "%s still has a free tube, runs toward the FDT, and the signal at the customer is fine "
                             "(loss %s of the %s limit, besides a %s reserve).") % (
            k["nama"] or k["id"], db((bud.get("total_db") or 0) - prm["margin_db"]), db(prm["kelas_olt_db"]),
            db(prm["margin_db"])))
        if k.get("biaya_relatif") is not None:
            h["alasan"].append(T("Biayanya paling hemat: %s (numpang kabel %s x%s, numpang tiang %s x%s, tiang baru %s x%s).",
                                 "The lowest cost: %s (riding cable %s x%s, riding poles %s x%s, new poles %s x%s).") % (
                "{:,}".format(k["biaya_relatif"]).replace(",", "."), m(k.get("colo_m") or 0),
                prm.get("biaya_colo_cable", 1), m(k.get("colo_pole_m") or 0), prm.get("biaya_colo_pole", 20),
                m(k.get("new_infra_m") or 0), prm.get("biaya_new_infra", 100)))
        if k.get("tap_slack"):
            h["alasan"].append(T("Kabel baru disambung di %s.", "The new cable is joined at %s.") % label_tap(k["tap_slack"]))
        if k.get("naik_slack"):
            x0 = next((x for x in h["kandidat"] if x["lolos"] and x is not k and not x.get("tap_slack")), None)
            if x0 is not None and x0["kabel_baru_m"] < k["kabel_baru_m"]:
                h["alasan"].append(T("Dipilih meski kabel barunya %s lebih panjang daripada %s, karena menyambung di "
                                     "tengah kabel tanpa slack tidak bisa langsung dikerjakan.",
                                     "Chosen although its new cable is %s longer than %s, because a mid-cable tap "
                                     "without slack cannot be built directly.") % (
                    m(k["kabel_baru_m"] - x0["kabel_baru_m"]), x0["nama"] or x0["id"]))
        setara = [x for x in lolos[1:] if _setara(x, k)
                  and (x.get("feeder_int"), x.get("sumber")) != (k.get("feeder_int"), k.get("sumber"))]
        if setara:
            h["peringatan"].append(T("Ada pilihan yang hampir sama: %s juga bisa dipakai dengan kabel baru hampir sama "
                                     "panjang (%s). Yang dipakai %s karena %s. Kalau rencana cluster lebih cocok dengan "
                                     "yang lain, pilih saja di panel.",
                                     "There is a near-equal option: %s also works with almost the same new cable "
                                     "length (%s). %s is used because %s. If the cluster plan suits the other better, "
                                     "just pick it in the panel.") % (
                gabung(", ", [T("feeder %s", "feeder %s") % (x["nama"] or x["id"]) for x in setara[:3]]),
                gabung(", ", [m(x["kabel_baru_m"]) for x in setara[:3]]), k["nama"] or k["id"],
                _alasan_urut(k, setara[0])))
        if not k.get("tap_slack") and k["sumber"] == "COMPILE":
            h["peringatan"].append(T("Titik sambungnya tidak di slack, closure atau ujung kabel yang sudah ada. Karena slack "
                                     "baru tidak dibuat, pastikan di lapangan masih ada cadangan kabel di titik ini, atau "
                                     "pilih opsi lain di panel.",
                                     "The tap point is not at an existing slack, closure or cable end. Since no new "
                                     "slack is made, check on site that there is spare cable at this point, or pick "
                                     "another option in the panel."))
            h["batas"] = True
        if inf.get("tube") and k["sumber"] == "COMPILE":
            h["peringatan"].append(T("Tube T%d dipilih karena di compile belum tercatat terpakai. Belum tercatat belum tentu "
                                     "kosong, jadi cek dulu di OTB atau catatan tube.",
                                     "Tube T%d is proposed because the compilation does not show it as used. Not "
                                     "recorded does not always mean free, so check at the OTB or in the tube record "
                                     "first.") % inf["tube"])
    elif cek:
        h["keputusan"], h["terpilih"] = "COLO_CEK", cek[0]
        h["alasan"].append(T("Feeder %s cocok arah dan jaraknya, tapi sisa tube-nya tidak tercatat di data. Pastikan "
                             "dulu masih ada tube kosong.",
                             "Feeder %s fits in direction and distance, but its free tubes are not recorded in the "
                             "data. Confirm there is a free tube before using it.") % (cek[0]["nama"] or cek[0]["id"]))
    elif fb:
        h["keputusan"] = "FEEDER_BARU"
        if not h["kandidat"]:
            h["alasan"].append(T("Tidak ada feeder dengan tube kosong dalam radius %s dari FDT.",
                                 "There is no feeder with a free tube within %s of the FDT.") % m(prm["radius_cari_m"]))
        else:
            k = h["kandidat"][0]
            h["alasan"].append(T("Feeder terdekat, %s, tidak bisa dipakai: %s.",
                                 "The nearest feeder, %s, cannot be used: %s.") % (
                k["nama"] or k["id"], gabung("; ", k["gagal"] or k["catatan"])))
        core_fb = core_feeder_baru(h, prm)
        h["alasan"].append(T("Susunannya OTB 144 di POP, kabel 144 core sampai closure 144, lalu kabel %d core ke FDT. "
                             "Pastikan slack 144-nya tidak bertumpuk dengan slack feeder lain.",
                             "Layout: OTB 144 at the POP, a 144-fibre cable to the closure 144, then a %d-fibre cable to "
                             "the FDT. Make sure its 144 slack is not at the same spot as another feeder's slack.") % core_fb)
        if prm.get("feeder_baru_ikut_jarak", True):
            h["alasan"].append(T("Kabelnya %d core karena jalur POP ke FDT %s (sampai %s cukup 48 core).",
                                 "A %d-fibre cable because the POP-to-FDT route is %s (48-fibre limit %s).") % (
                core_fb, km(fb.get("panjang_est_m") or fb.get("panjang_m") or 0),
                km(float(prm["batas_48f_km"]) * 1000.0)))
    else:
        h["alasan"].append(T("Di data ini tidak ada jalur ke POP maupun ke feeder yang ada, jadi FDT ini perlu "
                             "dirancang manual.", "No route to the POP or to an existing feeder in this data: design this FDT "
                             "by hand."))
    sel = h.get("terpilih")
    bud = (sel or {}).get("budget") or {}
    if sel and bud.get("margin_db") is not None and bud["margin_db"] < 0:
        h["peringatan"].append(T("Redaman %s masih di bawah batas GPON %s, tapi cadangan %s-nya sudah terpakai (tinggal "
                                 "%s). Ukur redamannya di lapangan setelah penyambungan.",
                                 "Signal loss %s: within the GPON class limit %s with maximum standard component values, "
                                 "but the %s reserve margin is not complete (%s left). Measure the loss on site after "
                                 "splicing.") % (
            db(bud["total_db"] - prm["margin_db"]), db(prm["kelas_olt_db"]), db(prm["margin_db"]),
            db(prm["margin_db"] + bud["margin_db"])))
    elif sel and bud.get("margin_db") is not None and 0 <= bud["margin_db"] < MARGIN_TIPIS_DB:
        h["peringatan"].append(T("Redaman sudah dekat batas (%s dari %s, sisa %s). Angka ini memakai nilai standar, jadi "
                                 "sebaiknya diukur di lapangan atau cek dulu kelas perangkatnya.",
                                 "Signal loss is close to the limit (%s of %s, %s to spare). The figure uses standard "
                                 "values, so measure on site or confirm the optical class before building.") % (
            db(bud["total_db"]), db(prm["kelas_olt_db"]), db(bud["margin_db"])))
    rute = sel["rute"] if sel else (fb if h["keputusan"] == "FEEDER_BARU" else None)
    if rute and rute.get("bantu_m", 0) > 1:
        h["peringatan"].append(T("Masih ada %s garis bantu lurus karena di bagian itu tidak ada data jalan atau kabel. "
                                 "Gambar ulang mengikuti tiang atau jalan.",
                                 "%s of the route is still a straight helper line (no road or cable data there): redraw "
                                 "it along poles or the road.") % m(rute["bantu_m"]))


def pilih_manual(h, i, data, prm=None):
    """Desainer memilih kandidat ke-i (0-based) di panel atau menerima Saran Tembuku: keputusan diganti, alasan dicatat,
    penomoran dan penjelasan dihitung ulang."""
    k = h["kandidat"][i]
    h["terpilih"] = k
    h["keputusan"] = "COLO" if k["lolos"] else "COLO_MANUAL"
    s = h.get("saran")
    dari_saran = bool(s and s.get("kandidat") is k)
    if s:
        s["dipakai"] = dari_saran
    awal = T("Memakai Saran Tembuku", "Using Tembuku's suggestion") if dari_saran else \
        T("Pilihan desainer", "Designer's choice")
    h["alasan"] = [T("%s: feeder %s (%s), kabel baru %s.%s", "%s: feeder %s (%s), new cable %s.%s") % (
        awal, k["nama"] or k["id"], k["label_colo"], m(k["kabel_baru_m"]),
        "" if k["lolos"] else T(" Catatan Tembuku: %s.", " Tembuku's note: %s.") % gabung("; ", k["gagal"] + k["catatan"]))]
    h["dipilih_desainer"] = "SARAN" if dari_saran else "MANUAL"
    if dari_saran:
        h["alasan"].append(s["alasan"])
    h["penomoran"] = penomoran(h, data)
    from . import penjelasan as _pj
    h["penjelasan"] = _pj.susun(h, prm or profil.baru())
    return h


def pilih_feeder_baru(h, data, prm=None):
    h["terpilih"] = None
    h["keputusan"] = "FEEDER_BARU"
    h["dipilih_desainer"] = "MANUAL"
    if h.get("saran"):
        h["saran"]["dipakai"] = False
    h["alasan"] = [T("Pilihan desainer: feeder baru dari %s (%s).", "Designer's choice: a new feeder from %s (%s).") % (
        h["pop"]["nama"] if h["pop"] else "POP", m(h["feeder_baru"]["panjang_m"] if h.get("feeder_baru") else 0))]
    h["penomoran"] = penomoran(h, data)
    from . import penjelasan as _pj
    h["penjelasan"] = _pj.susun(h, prm or profil.baru())
    return h
