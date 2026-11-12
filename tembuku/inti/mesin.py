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

from . import geo, osm, profil, validasi
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
    info = {"kelompok": None, "bebas": [], "tube": None, "terpakai": [], "feeder": _angka_feeder(k.get("feeder")),
            "sisa_kabel": None, "bebas_lain": [], "kelompok_lain": None}
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
        return ("LOLOS" if bebas >= prm["tube_per_fdt"] else "PENUH"), bebas, T(
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
        return ("LOLOS" if bebas >= prm["tube_per_fdt"] else "PENUH"), bebas, T(
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
    ok = bool(bebas) and len(bebas) > prm["cadangan_tube"] and sisa_kabel >= prm["tube_per_fdt"]
    nama_grup = T("tube %s (jalur kabel %s)", "tubes %s (the %s path)") % (_teks_tube(grup), kel)
    if ok:
        teks = T("Feeder %d sudah memakai %s; yang masih kosong di %s: %s. Diusulkan %s",
                 "Feeder %d already uses %s; still free in %s: %s. Proposed: %s") % (
            fe, _teks_tube(pakai), nama_grup, _teks_tube(bebas), "T%d" % bebas[0])
    elif not bebas:
        teks = T("Feeder %d sudah memakai semua %s", "Feeder %d already uses all %s") % (fe, nama_grup)
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
TOLERANSI_SETARA = 0.05     # kandidat yang kabel barunya beda < 5 % (dan < 100 m) dianggap setara


def analisis(fdt, data, prm=None, log=None):
    prm = prm or profil.baru()
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
    for d, j in G.dekat(fx, prm["akses_maks_m"], lambda j: j != nf)[:8]:
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
        best = best_any = best_slack = None
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
        if best_any is None:
            continue
        pilihan = best if best is not None and best[0] <= best_any[0] * 1.5 else best_any
        # titik sambung dipindah ke slack/closure existing bila tidak jauh lebih mahal (closure baru tepat di slack)
        if best_slack is not None and best_slack is not pilihan and \
                best_slack[0] <= pilihan[0] + prm["tap_slack_toleransi_m"]:
            pilihan = best_slack
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
    _putuskan(hasil, prm)
    hasil["penomoran"] = penomoran(hasil, data)
    hasil["lokal"] = (F[0], F[1])
    hasil["alasan"].insert(0, ringkasan_awam(hasil, prm))
    # penyeberangan jalan di ruas New Infra jalur terpilih (tiang 9 m di kedua sisi)
    seberang = _daftar_kelas(prm.get("kelas_seberang")) or KELAS_SEBERANG
    besar = [[L.ke(p) for p in j["ll"]] for j in jalan if (j.get("kelas") or "").lower() in seberang]
    for r in ([hasil["terpilih"]["rute"]] if hasil.get("terpilih") else []) + ([hasil["feeder_baru"]] if hasil.get("feeder_baru") else []):
        r["seberang"] = _penyeberangan(r, besar)
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
        best = None
        for xy, kb in zip(besar, kotak):
            if not (kb[0] - 3 <= p[0] <= kb[2] + 3 and kb[1] - 3 <= p[1] <= kb[3] + 3):
                continue
            nb = geo.terdekat_di_garis(p, xy)
            if nb and nb[0] <= 2.0 and (best is None or nb[0] < best[0]):
                best = (nb[0], geo.satuan(xy[nb[1]], xy[nb[1] + 1]))
        return best[1] if best else None

    def sinus(u, v):
        return abs(u[0] * v[1] - u[1] * v[0])
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
        # (2) memotong tepat di simpul jalan: arah masuk dan keluar sama-sama melintang terhadap jalan utama
        if i + 2 < len(titik) and (b, titik[i + 2]) in baru and b != titik[i + 2]:
            rj = arah_jalan(b)
            if rj and sinus(geo.satuan(a, b), rj) >= 0.5 and sinus(geo.satuan(b, titik[i + 2]), rj) >= 0.5:
                ketemu.append(ch_seg[i + 1])
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
        s = T("Keputusan: sambungkan FDT ini ke %s yang sudah ada dan pakai tube T%s (folder %s). Perlu kabel baru %s "
              "dari titik sambung ke FDT", "Decision: connect this FDT to the existing %s and use tube T%s (folder %s). "
              "It needs %s of new cable from the tap point to the FDT") % (siapa, n.get("t"), folder, m(k["kabel_baru_m"]))
        if k.get("colo_rasio") is not None and k["kabel_baru_m"] >= 50:
            s += T(", %d%% di antaranya menumpang tiang yang sudah ada", ", %d%% of it on existing poles") % round(
                100 * k["colo_rasio"])
        s += T(".", ".")
        if fb:
            s += T(" Sebagai pembanding, feeder baru dari POP butuh %s kabel baru, ditambah OTB dan kabel 144 core.",
                   " For comparison, a new feeder from the POP needs %s of new cable plus an OTB and a 144-fibre "
                   "cable.") % m(fb["panjang_m"])
        if kep == "COLO_CEK":
            s += T(" Sisa tube feeder ini belum tercatat, jadi pastikan dulu masih ada yang kosong.",
                   " This feeder's free tubes are not recorded, so first confirm one is free.")
        return s
    if kep == "FEEDER_BARU" and fb:
        return T("Keputusan: buat feeder baru dari %s sepanjang %s (folder %s), karena tidak ada feeder yang sudah ada "
                 "yang cocok.", "Decision: build a new feeder from %s, %s long (folder %s), because no existing feeder "
                 "fits.") % (h["pop"]["nama"] if h.get("pop") else "POP", m(fb["panjang_m"]), folder)
    return T("Keputusan: FDT ini perlu dirancang manual oleh desainer; alasannya di bawah.",
             "Decision: this FDT needs to be designed by hand; the reason is below.")


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
    core = int(prm["core_feeder_baru"] if h["keputusan"] == "FEEDER_BARU" else (sel or {}).get("core_cabang") or prm["core_cabang"])
    if not data.compiles or data.compiles[-1].get("berkas") != "_TEMBUKU_BATCH":
        data.compiles.append({"pops": [], "traksi": {}, "kabel": [], "fdt": [], "berkas": "_TEMBUKU_BATCH"})
    c = data.compiles[-1]
    popf = n["pop_folder"]
    ll = [L.balik(p) for p in rute["titik"]]
    fdt = dict(h["fdt"], traksi=kode, feeder=str(n["feeder"]), pop_folder=popf, colo_saudara=False)
    kab = {"id": "V%d" % (len(c["kabel"]) + 1), "ll": ll, "core": core, "jenis": "NEW_CABLE", "nama": "%dC" % core,
           "traksi": kode, "feeder": str(n["feeder"]), "pop_folder": popf, "berkas": "_TEMBUKU_BATCH",
           "sumber": "COMPILE", "warna": None, "folder": "New Cable %dC" % core}
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
                 "area": h["fdt"].get("area")}}
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
        return T("Ditolak: ", "Rejected: ") + gabung("; ", k["gagal"])
    if k["catatan"]:
        return T("Bisa dipakai, tetapi ", "Usable, but ") + gabung("; ", k["catatan"])
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
         "alasan": [T("Tembuku gagal menganalisis FDT ini (%s). Rancang FDT ini secara manual.",
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
    if prevB is not None and distB[v] < INF:
        jl = G.jalur(prevB, v)
        colo_xy = [G.xy[n] for n, _j, _r in jl]
        colo_m = geo.panjang(colo_xy)
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
    # aturan 6 km (PDF 3.1): cabang 48F hanya bila jalur POP->FDT <= batas; lebih jauh lewat kabel 96F (T1-T8), dan
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
                if st == "PENUH" and info["bebas"]:
                    st = "LOLOS"
            else:
                gagal.append(T("jarak POP ke FDT %s, lebih dari %s, sehingga perlu kabel 96 core, tetapi tube T1-T8 "
                               "feeder ini sudah penuh",
                               "the POP-to-FDT route is %s, over %s, so a 96-fibre cable is needed, but this feeder's "
                               "tubes T1-T8 are full") % (km(jalur_serat), km(batas_m)))
        elif info.get("kelompok") == "48F" and jalur_serat > batas_m:
            gagal.append(T("jarak POP ke FDT lewat kabel 48 core ini %s, lebih dari batas %s untuk kabel 48 core",
                           "the POP-to-FDT route via this 48-fibre cable is %s, over the %s limit for 48 fibres")
                         % (km(jalur_serat), km(batas_m)))
    if st == "PENUH":
        gagal.append(T("tidak ada tube kosong (%s)", "no free tube (%s)") % teks)
    elif st == "BELUM_TERVERIFIKASI":
        alasan.append(T("sisa tube belum bisa dipastikan (%s): cek di lapangan",
                        "free tubes cannot be confirmed (%s): check on site") % teks)
    if not searah:
        gagal.append(T("feeder ini berjalan menjauhi FDT (arahnya melenceng %d°, paling banyak %d°)",
                       "this feeder runs away from the FDT (%d° off, at most %d°)") % (
            round(math.degrees(math.acos(max(-1.0, min(1.0, cosv))))) if cosv is not None else 180,
            round(math.degrees(math.acos(max(-1.0, min(1.0, prm["cos_arah_min"])))))))
    di_pop = P is not None and math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) <= JARAK_POP_M
    # aturan 6 km juga menentukan kelompok: <= 6 km cabang 48F (T9-T12), > 6 km kabel 96F (T1-T8)
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
    if lurus < prm["detour_lurus_maks_m"] and detour > prm["detour_maks"]:
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
    if bud["margin_db"] < 0:
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
    skor = c * (1.0 + (0.5 if st == "BELUM_TERVERIFIKASI" else 0) + (0.3 if colo_m is None else 0) +
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
            "colo_m": None if colo_m is None else round(colo_m), "colo_xy": colo_xy, "jalur_serat_m": round(jalur_serat),
            "rute": rute, "budget": bud, "gagal": gagal, "catatan": alasan, "skor": skor, "koridor_sendiri": koridor,
            "tap_slack": tap_slack, "core_cabang": core_cabang, "lolos": not gagal and st == "LOLOS", "biaya": c,
            "kelompok_sesuai": sesuai, "di_pop": di_pop, "colo_rasio": round(colo_rasio, 3)}


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
    """Kabel baru dua kandidat dianggap setara bila selisihnya < 5 % dan < 100 m."""
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
            ada.sort(key=lambda d: (d["kabel_baru_m"], _kunci_setara(d)))
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


def _putuskan(h, prm):
    fb = h["feeder_baru"]
    if h["pop"] is None:
        h["keputusan"] = "PERLU_MANUAL"
        h["alasan"].append(T("Tidak ada POP/OLT dalam %s, jadi sisa tube, arah dan redaman sinyal tidak bisa "
                             "dibuktikan. Kandidat di tabel hanya bahan tinjauan: rancang FDT ini secara manual.",
                             "No POP/OLT within %s, so free tubes, direction and signal loss cannot be proven. The "
                             "candidates in the table are for review only: design this FDT by hand.") % km(prm["pop_maks_m"]))
        return
    for k in h["kandidat"]:
        k["rasio_jalur"] = round(k["jalur_serat_m"] / fb["panjang_est_m"], 2) if fb and fb["panjang_est_m"] > 0 else None
        k["gagal_lain"] = len(k["gagal"])       # alasan tolak selain 'memutar' (dipakai penentuan zona batas)
        if k["rasio_jalur"] is not None and k["rasio_jalur"] > prm["rasio_jalur_maks"]:
            k["gagal"].append(T("jalurnya memutar terlalu jauh: lewat feeder ini totalnya %s, sedangkan feeder baru "
                                "langsung dari POP hanya %s (paling banyak %s panjangnya)",
                                "the route goes too far round: through this feeder it is %s in total, while a new "
                                "feeder straight from the POP is only %s (at most %s as long)") % (
                km(k["jalur_serat_m"]), km(fb["panjang_est_m"]), kali(prm["rasio_jalur_maks"])))
            k["lolos"] = False
            k["skor"] *= 2.0
    lolos = _urut_setara([k for k in h["kandidat"] if k["lolos"]], bool(prm.get("utamakan_aturan_6km", False)), prm)
    lain = [k for k in h["kandidat"] if not k["lolos"]]
    lain.sort(key=lambda d: d["skor"])
    h["kandidat"] = lolos + lain
    near = [k for k in h["kandidat"][:3] if k["rasio_jalur"] is not None and not k.get("gagal_lain", len(k["gagal"]))
            and abs(k["rasio_jalur"] - prm["rasio_jalur_maks"]) <= prm["zona_batas"]]
    if near:
        h["batas"] = True
        h["peringatan"].append(T("Perlu ditinjau: memakai feeder %s dan membuat feeder baru hampir sama baiknya (jalur "
                                 "lewat feeder ini %s panjang feeder baru, batasnya %s). Periksa keduanya sebelum "
                                 "memutuskan.",
                                 "Please review: using feeder %s and building a new feeder are almost equally good (the "
                                 "route through this feeder is %s a new feeder, the limit is %s). Check both before "
                                 "deciding.") % (near[0]["nama"] or near[0]["id"], kali(near[0]["rasio_jalur"]),
                                                 kali(prm["rasio_jalur_maks"])))
    cek = [k for k in h["kandidat"] if not k["gagal"] and k["kapasitas"] == "BELUM_TERVERIFIKASI"]
    if lolos:
        k = lolos[0]
        h["keputusan"], h["terpilih"] = "COLO", k
        inf = k.get("kap_info") or {}
        bud = k.get("budget") or {}
        h["alasan"].append(T("Alasannya: kabel %s masih punya tube kosong, arahnya menuju FDT, dan kekuatan sinyal sampai "
                             "pelanggan masih dalam batas (redaman %s, batasnya %s).",
                             "Why: cable %s still has a free tube, runs toward the FDT, and the signal at the customer "
                             "is within the limit (loss %s, limit %s).") % (
            k["nama"] or k["id"], db(bud.get("total_db") or 0), db(prm["kelas_olt_db"])))
        if k.get("tap_slack"):
            h["alasan"].append(T("Kabel baru disambung di %s.", "The new cable is joined at %s.") % label_tap(k["tap_slack"]))
        if k.get("naik_slack"):
            x0 = next((x for x in h["kandidat"] if x["lolos"] and x is not k and not x.get("tap_slack")), None)
            if x0 is not None and x0["kabel_baru_m"] < k["kabel_baru_m"]:
                h["alasan"].append(T("Dipilih walau kabel barunya %s lebih panjang dari %s, karena titik sambung di "
                                     "tengah kabel tanpa slack tidak bisa langsung dikerjakan.",
                                     "Chosen although its new cable is %s longer than %s, because a mid-cable tap "
                                     "without slack cannot be built directly.") % (
                    m(k["kabel_baru_m"] - x0["kabel_baru_m"]), x0["nama"] or x0["id"]))
        setara = [x for x in lolos[1:] if _setara(x, k)
                  and (x.get("feeder_int"), x.get("sumber")) != (k.get("feeder_int"), k.get("sumber"))]
        if setara:
            h["peringatan"].append(T("Pilihan setara: %s juga memenuhi syarat dengan kabel baru hampir sama panjang "
                                     "(%s). Dipakai %s karena %s; pilih yang lain di panel bila perencanaan cluster "
                                     "menghendaki.",
                                     "Equal alternative: %s also qualifies with almost the same new cable length (%s). "
                                     "%s is used because %s; pick the other in the panel if the cluster plan says so.") % (
                gabung(", ", [T("feeder %s", "feeder %s") % (x["nama"] or x["id"]) for x in setara[:3]]),
                gabung(", ", [m(x["kabel_baru_m"]) for x in setara[:3]]), k["nama"] or k["id"],
                _alasan_urut(k, setara[0])))
        if not k.get("tap_slack") and k["sumber"] == "COMPILE":
            h["peringatan"].append(T("Perlu dicek: titik sambungnya tidak berada di slack, closure atau ujung kabel yang "
                                     "sudah ada. Aturannya, slack baru tidak dibuat bila tidak tersedia, jadi pastikan di "
                                     "lapangan ada cadangan kabel di titik ini, atau pilih kandidat lain di panel.",
                                     "The tap point is not at an existing slack, closure or cable end. Rule: no new "
                                     "slack is created where none exists, so confirm on site that there is spare "
                                     "cable at this point, or choose another candidate in the panel."))
            h["batas"] = True
        if inf.get("tube") and k["sumber"] == "COMPILE":
            h["peringatan"].append(T("Perlu dicek: tube T%d dipilih karena di compile belum tercatat dipakai. Belum "
                                     "tercatat belum tentu kosong, jadi pastikan di OTB atau catatan tube sebelum dipakai.",
                                     "Tube T%d is proposed because the compilation does not record it as used. A "
                                     "missing record is not proof that the tube is free: confirm at the OTB or in the "
                                     "tube record before using it.") % inf["tube"])
    elif cek:
        h["keputusan"], h["terpilih"] = "COLO_CEK", cek[0]
        h["alasan"].append(T("Feeder %s cocok arah dan jaraknya, tetapi sisa tube-nya tidak tercatat di data. Pastikan "
                             "masih ada tube kosong sebelum dipakai.",
                             "Feeder %s fits in direction and distance, but its free tubes are not recorded in the "
                             "data. Confirm there is a free tube before using it.") % (cek[0]["nama"] or cek[0]["id"]))
    elif fb:
        h["keputusan"] = "FEEDER_BARU"
        if not h["kandidat"]:
            h["alasan"].append(T("Alasannya: tidak ada feeder dengan tube kosong dalam radius %s dari FDT.",
                                 "Why: no feeder with a free tube within %s of the FDT.") % m(prm["radius_cari_m"]))
        else:
            k = h["kandidat"][0]
            h["alasan"].append(T("Alasannya: feeder terdekat, %s, tidak bisa dipakai karena %s.",
                                 "Why: the nearest feeder, %s, cannot be used because %s.") % (
                k["nama"] or k["id"], gabung("; ", k["gagal"] or k["catatan"])))
        h["alasan"].append(T("Susunannya: OTB 144 di POP, kabel 144 core sampai closure 144, lalu kabel %d core ke FDT. "
                             "Pastikan slack 144-nya tidak di titik yang sama dengan slack feeder lain.",
                             "Layout: OTB 144 at the POP, a 144-fibre cable to the closure 144, then a %d-fibre cable to "
                             "the FDT. Make sure its 144 slack is not at the same spot as another feeder's slack.") %
                           int(prm["core_feeder_baru"]))
    else:
        h["alasan"].append(T("Tidak ada jalur ke POP maupun ke feeder yang ada di data ini: rancang FDT ini secara "
                             "manual.", "No route to the POP or to an existing feeder in this data: design this FDT "
                             "by hand."))
    sel = h.get("terpilih")
    bud = (sel or {}).get("budget") or {}
    if sel and bud.get("margin_db") is not None and 0 <= bud["margin_db"] < MARGIN_TIPIS_DB:
        h["peringatan"].append(T("Redaman sinyal hampir di batas (%s dari batas %s, sisa %s). Hitungan ini memakai nilai "
                                 "standar, jadi ukur di lapangan atau pastikan kelas perangkat optiknya sebelum dibangun.",
                                 "Signal loss is close to the limit (%s of %s, %s to spare). The figure uses standard "
                                 "values, so measure on site or confirm the optical class before building.") % (
            db(bud["total_db"]), db(prm["kelas_olt_db"]), db(bud["margin_db"])))
    rute = sel["rute"] if sel else (fb if h["keputusan"] == "FEEDER_BARU" else None)
    if rute and rute.get("bantu_m", 0) > 1:
        h["peringatan"].append(T("%s jalur masih berupa garis bantu lurus (tidak ada data jalan atau kabel di bagian "
                                 "itu): gambar ulang mengikuti tiang atau jalan.",
                                 "%s of the route is still a straight helper line (no road or cable data there): redraw "
                                 "it along poles or the road.") % m(rute["bantu_m"]))


def pilih_manual(h, i, data):
    """Desainer memilih kandidat ke-i (0-based) di panel: keputusan diganti, alasan dicatat, penomoran dihitung ulang."""
    k = h["kandidat"][i]
    h["terpilih"] = k
    h["keputusan"] = "COLO" if k["lolos"] else "COLO_MANUAL"
    h["alasan"] = [T("Pilihan desainer: feeder %s (%s), kabel baru %s.%s",
                     "Designer's choice: feeder %s (%s), new cable %s.%s") % (
        k["nama"] or k["id"], k["label_colo"], m(k["kabel_baru_m"]),
        "" if k["lolos"] else T(" Catatan Tembuku: %s.", " Tembuku's note: %s.") % gabung("; ", k["gagal"] + k["catatan"]))]
    h["penomoran"] = penomoran(h, data)
    return h


def pilih_feeder_baru(h, data):
    h["terpilih"] = None
    h["keputusan"] = "FEEDER_BARU"
    h["alasan"] = [T("Pilihan desainer: feeder baru dari %s (%s).", "Designer's choice: a new feeder from %s (%s).") % (
        h["pop"]["nama"] if h["pop"] else "POP", m(h["feeder_baru"]["panjang_m"] if h.get("feeder_baru") else 0))]
    h["penomoran"] = penomoran(h, data)
    return h
