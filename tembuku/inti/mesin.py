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

    # ------------------------------------------------------------------ identitas POP & traksi
    def nama_pop(self, popf, c=None):
        """Nama POP sebuah folder POP compile ('BENGKULU POP 4' -> titik OLT 'Bengkulu POP 4'); compile tanpa folder
        POP (Tomohon) -> satu-satunya POP/OLT di compile itu."""
        from . import sumber
        kp = sumber.kunci_pop(popf)
        if kp:
            for p in self.pops:
                kn = sumber.kunci_pop(p["nama"])
                if kp == kn or kn.endswith(kp) or kp in kn:
                    return p["nama"]
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
        for c in self.compiles:
            for (_b, popf, _f, kode), t in c["traksi"].items():
                if kode in self.kecuali:
                    continue
                inf = t.get("info") or {}
                fe = _angka_feeder(inf.get("feeder") or t.get("feeder"))
                if fe is None or sumber.kunci_pop(self.nama_pop(popf, c)) != kp:
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
                out.setdefault(int(afdr), {"tube": set(), "fdt": set(), "traksi": set()})["tube"] |= set(at)
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
    nama_grup = T("kelompok %s (%s)", "group %s (%s)") % (kel, _teks_tube(grup))
    if ok:
        teks = T("feeder %d: tube terpakai %s; %s masih kosong %s -> usulan T%d",
                 "feeder %d: tubes in use %s; %s still free %s -> proposed T%d") % (
            fe, _teks_tube(pakai), nama_grup, _teks_tube(bebas), bebas[0])
    elif not bebas:
        teks = T("feeder %d: %s sudah terpakai semua (tube terpakai %s)",
                 "feeder %d: %s is fully used (tubes in use %s)") % (fe, nama_grup, _teks_tube(pakai))
    else:
        teks = T("kabel %dC ini sudah melayani %d FDT (kapasitas %d tube)",
                 "this %dC cable already serves %d FDT(s) (capacity %d tubes)") % (core, terpakai, tube)
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
    daftar = _gabung_fisik(daftar)
    daftar.sort(key=lambda d: d["skor"])
    hasil["kandidat"] = daftar[:10]
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
    # penyeberangan jalan utama di ruas New Infra jalur terpilih (tiang 9 m di kedua sisi)
    besar = [[L.ke(p) for p in j["ll"]] for j in jalan if (j.get("kelas") or "").lower() in KELAS_SEBERANG]
    for r in ([hasil["terpilih"]["rute"]] if hasil.get("terpilih") else []) + ([hasil["feeder_baru"]] if hasil.get("feeder_baru") else []):
        r["seberang"] = _penyeberangan(r, besar)
    return hasil


KELAS_SEBERANG = {"trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary",
                  "tertiary_link"}


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
    c["traksi"][("_TEMBUKU_BATCH", popf, str(n["feeder"]), kode)] = {
        "kode": kode, "pop_folder": popf, "feeder": str(n["feeder"]), "berkas": "_TEMBUKU_BATCH", "fdt": [fdt],
        "kabel": [kab], "colo": colo, "closure": [], "slack": [], "lain": [],
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
        bag.append(T("Titik sambung di %s existing '%s' (%s m).", "Tap at the existing %s '%s' (%s m).") % (
            ts["jenis"], ts["nama"], ts["jarak_m"]))
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
    for p in pts:
        for xy in garis:
            if len(xy) < 2:
                continue
            xs = [q[0] for q in xy]
            ys = [q[1] for q in xy]
            if not (min(xs) - tol <= p[0] <= max(xs) + tol and min(ys) - tol <= p[1] <= max(ys) + tol):
                continue
            if geo.terdekat_di_garis(p, xy)[0] <= tol:
                kena += 1
                break
    return kena / float(len(pts))


def _closure_di_jalur(colo_xy, titik_feeder_xy, tol=10.0):
    """Jumlah closure/slack existing yang dilewati jalur feeder POP->titik sambung (tiap closure = satu sambungan)."""
    if not colo_xy or len(colo_xy) < 2 or not titik_feeder_xy:
        return 0
    n = 0
    for q in titik_feeder_xy:
        if geo.terdekat_di_garis(q, colo_xy)[0] <= tol:
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
    # aturan 6 km: cabang 48F hanya bila jalur POP->FDT <= batas; lebih jauh lewat kabel 96F (T1-T8)
    batas_m = float(prm["batas_48f_km"]) * 1000.0
    if st in ("LOLOS", "PENUH") and info.get("kelompok"):
        if core >= 144 and jalur_serat > batas_m:
            # closure 144: lebih dari 6 km -> harus cabang 96F dari kelompok T1-T8
            if info.get("bebas_lain"):
                info.update({"kelompok": info["kelompok_lain"], "bebas": info["bebas_lain"], "tube": info["bebas_lain"][0]})
                core_cabang = 96
                alasan.append(T("jalur POP->FDT %s lebih dari %s: memakai kabel 96F dari closure 144 (tube %s)",
                                "the POP->FDT route of %s exceeds %s: a 96F cable from the closure 144 is used (tube %s)")
                              % (km(jalur_serat), km(batas_m), _teks_tube(info["bebas"])))
                if st == "PENUH" and info["bebas"]:
                    st = "LOLOS"
            else:
                gagal.append(T("jalur POP->FDT %s lebih dari %s dan kelompok 96F (T1-T8) feeder ini sudah penuh",
                               "the POP->FDT route of %s exceeds %s and this feeder's 96F group (T1-T8) is full")
                             % (km(jalur_serat), km(batas_m)))
        elif info.get("kelompok") == "48F" and jalur_serat > batas_m:
            gagal.append(T("jalur POP->FDT lewat kabel 48F ini %s, lebih dari batas %s untuk cabang 48F",
                           "the POP->FDT route via this 48F cable is %s, over the %s limit for a 48F branch")
                         % (km(jalur_serat), km(batas_m)))
    if st == "PENUH":
        gagal.append(T("tidak ada tube kosong (%s)", "no free tube (%s)") % teks)
    elif st == "BELUM_TERVERIFIKASI":
        alasan.append(T("sisa tube belum bisa dipastikan (%s): cek di lapangan",
                        "free tubes cannot be confirmed (%s): check on site") % teks)
    if not searah:
        gagal.append(T("arah feeder menjauhi FDT (melenceng %d°, batas %d°)",
                       "the feeder runs away from the FDT (%d° off, limit %d°)") % (
            round(math.degrees(math.acos(max(-1.0, min(1.0, cosv))))) if cosv is not None else 180,
            round(math.degrees(math.acos(max(-1.0, min(1.0, prm["cos_arah_min"])))))))
    di_pop = P is not None and math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) <= JARAK_POP_M
    # aturan 6 km juga menentukan kelompok: <= 6 km cabang 48F (T9-T12), > 6 km kabel 96F (T1-T8)
    perlu = "48F" if jalur_serat <= batas_m else "96F"
    sesuai = not info.get("kelompok") or info["kelompok"] == perlu
    if not sesuai:
        alasan.append(T("jalur POP->FDT %s: menurut aturan %s seharusnya kelompok %s, kabel ini kelompok %s",
                        "POP->FDT route of %s: by the %s rule it should be group %s, this cable is group %s") % (
            km(jalur_serat), km(batas_m), perlu, info["kelompok"]))
    if (core >= 144 or di_pop) and koridor is not None and koridor < prm["koridor_min"]:
        gagal.append(T("cabang baru dari closure 144 feeder %d tidak mengikuti koridor feeder itu (hanya %d%% jalur; "
                       "batas %d%%): arah feeder tidak sesuai cluster",
                       "a new branch from the closure 144 of feeder %d does not follow that feeder's corridor (only "
                       "%d%% of the route; limit %d%%): the feeder direction does not fit the cluster") % (
            fe or 0, round(100 * koridor), round(100 * prm["koridor_min"])))
    if lurus < prm["detour_lurus_maks_m"] and detour > prm["detour_maks"]:
        gagal.append(T("kabel baru harus memutar (%s jarak lurus, batas %s)",
                       "the new cable would go a long way round (%s the straight distance, limit %s)") % (
            kali(detour), kali(prm["detour_maks"])))
    if pjg > prm["cabang_maks_m"]:
        gagal.append(T("kabel baru terlalu panjang (%s, batas %s)", "new cable too long (%s, limit %s)") % (
            m(pjg), m(prm["cabang_maks_m"])))
    if colo_m is None:
        alasan.append(T("feeder ini belum terlihat tersambung ke POP di data: cek di lapangan",
                        "this feeder is not shown as connected to the POP in the data: check on site"))
    # sambungan: OTB di POP, closure existing yang dilewati, closure di titik sambung, FDT
    tf_xy = []
    if k["sumber"] == "COMPILE" and fe is not None and data is not None:
        tf_xy = [L.ke(tf["ll"]) for tf in data.titik_feeder(k.get("pop_nama") or "", fe) if tf["jenis"] == "closure"]
    splice = 3 + _closure_di_jalur(colo_xy, tf_xy)
    bud = link_budget(feeder_km + pjg / 1000.0, prm, splice=splice)
    if bud["margin_db"] < 0:
        gagal.append(T("redaman sinyal terlalu besar (%s, batas %s)", "signal loss too high (%s, limit %s)") % (
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
        alasan.append(T("titik sambung %s m dari %s existing '%s' (5-10 m: perlu dicek di lapangan)",
                        "the tap point is %s m from the existing %s '%s' (5-10 m: check on site)") % (
            tap_slack["jarak_m"], tap_slack["jenis"], tap_slack["nama"]))
    elif tap_slack is None and k["sumber"] == "COMPILE" and not gagal:
        alasan.append(T("tidak ada slack/closure existing dalam %d m dari titik sambung: perlu slack dan closure baru di "
                        "titik ini", "no existing slack/closure within %d m of the tap point: a new slack and closure "
                        "are needed there") % prm["tap_slack_m"])
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
            "kelompok_sesuai": sesuai, "di_pop": di_pop}


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
    return {"titik": titik, "segmen": seg, "panjang_m": pjg, "ref_kabel": [s[1] for s in seg if s[1]],
            "bantu_m": bantu, "panjang_est_m": pjg + bantu * (faktor_bantu - 1.0)}


def link_budget(km, prm, splice=6):
    serat = km * prm["fiber_db_km"]
    total = (serat + prm["splitter_fdt_db"] + prm["splitter_fat_db"] + prm["konektor_n"] * prm["konektor_db"] +
             splice * prm["splice_db"] + prm["margin_db"] + prm["distribusi_km"] * prm["fiber_db_km"])
    return {"km": round(km + prm["distribusi_km"], 2), "total_db": round(total, 2),
            "margin_db": round(prm["kelas_olt_db"] - total, 2) + 0.0, "splice": splice}


def _urut_setara(lolos, utamakan=False):
    """Kandidat yang kabel barunya setara (beda < 5 % dan < 100 m dari yang terbaik) diurutkan dengan aturan tetap:
    titik sambung di slack/closure existing dahulu, lalu nomor feeder terkecil, lalu kabel baru terpendek. Urutan ini
    stabil di semua wilayah dan tidak bergantung pada selisih beberapa meter."""
    if not lolos:
        return lolos
    if utamakan:        # kandidat yang kelompok tubenya sesuai aturan 6 km didahulukan
        a = [d for d in lolos if d.get("kelompok_sesuai", True)]
        b = [d for d in lolos if not d.get("kelompok_sesuai", True)]
        if a and b:
            return _urut_setara(a) + _urut_setara(b)
    lolos = sorted(lolos, key=lambda d: d["skor"])
    b = lolos[0]["kabel_baru_m"]
    setara = [d for d in lolos if abs(d["kabel_baru_m"] - b) <= max(100.0, TOLERANSI_SETARA * b)]
    sisa = [d for d in lolos if d not in setara]
    setara.sort(key=lambda d: (0 if d.get("tap_slack") else 1, d.get("feeder_int") or 999, d["kabel_baru_m"],
                               d.get("id") or ""))
    return setara + sisa


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
            k["gagal"].append(T("jalur lewat feeder ini memutar jauh (%s, yaitu %s panjang feeder baru %s; batas %s)",
                                "the route through this feeder is a long way round (%s, which is %s a new feeder of %s; "
                                "limit %s)") % (km(k["jalur_serat_m"]), kali(k["rasio_jalur"]), km(fb["panjang_est_m"]),
                                                kali(prm["rasio_jalur_maks"])))
            k["lolos"] = False
            k["skor"] *= 2.0
    lolos = _urut_setara([k for k in h["kandidat"] if k["lolos"]], bool(prm.get("utamakan_aturan_6km", True)))
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
        tube = (T(" Tube yang diusulkan: T%d (nomor kosong terkecil di kelompok %s).",
                  " Proposed tube: T%d (the lowest free number in group %s).") % (inf["tube"], inf.get("kelompok") or "-")
                ) if inf.get("tube") else ""
        h["alasan"].append(T("Pakai feeder %s (%s): masih ada tube kosong dan arahnya menuju FDT. Kabel baru %dC dari "
                             "titik sambung (tap) ke FDT: %s.%s%s",
                             "Use feeder %s (%s): it has a free tube and runs toward the FDT. New %dC cable from the tap "
                             "point to the FDT: %s.%s%s") % (
            k["nama"] or k["id"], k["label_colo"], k.get("core_cabang") or prm["core_cabang"], m(k["kabel_baru_m"]), tube,
            (T(" Sebagai pembanding, feeder baru dari POP: %s.", " For comparison, a new feeder from the POP: %s.")
             % m(fb["panjang_m"])) if fb else ""))
        setara = [x for x in lolos[1:] if abs(x["kabel_baru_m"] - k["kabel_baru_m"]) <= max(100.0, TOLERANSI_SETARA * k["kabel_baru_m"])
                  and (x.get("feeder_int"), x.get("sumber")) != (k.get("feeder_int"), k.get("sumber"))]
        if setara:
            h["peringatan"].append(T("Pilihan setara: %s juga memenuhi syarat dengan kabel baru hampir sama panjang "
                                     "(%s). Feeder bernomor terkecil yang dipakai; pilih yang lain di panel bila "
                                     "perencanaan cluster menghendaki.",
                                     "Equal alternative: %s also qualifies with almost the same new cable length (%s). "
                                     "The lowest-numbered feeder is used; pick the other in the panel if the cluster "
                                     "plan says so.") % (
                gabung(", ", [T("feeder %s", "feeder %s") % (x["nama"] or x["id"]) for x in setara[:3]]),
                gabung(", ", [m(x["kabel_baru_m"]) for x in setara[:3]])))
    elif cek:
        h["keputusan"], h["terpilih"] = "COLO_CEK", cek[0]
        h["alasan"].append(T("Feeder %s cocok arah dan jaraknya, tetapi sisa tube-nya tidak tercatat di data. Pastikan "
                             "masih ada tube kosong sebelum dipakai.",
                             "Feeder %s fits in direction and distance, but its free tubes are not recorded in the "
                             "data. Confirm there is a free tube before using it.") % (cek[0]["nama"] or cek[0]["id"]))
    elif fb:
        h["keputusan"] = "FEEDER_BARU"
        if not h["kandidat"]:
            h["alasan"].append(T("Tidak ada feeder dengan tube kosong dalam radius %s dari FDT.",
                                 "No feeder with a free tube within %s of the FDT.") % m(prm["radius_cari_m"]))
        else:
            k = h["kandidat"][0]
            h["alasan"].append(T("Feeder terdekat %s tidak dipakai: %s.", "The nearest feeder %s is not used: %s.") % (
                k["nama"] or k["id"], gabung("; ", k["gagal"] or k["catatan"])))
        h["alasan"].append(T("Usulan: feeder baru dari %s sepanjang %s (OTB 144, kabel 144C lalu %dC). Pastikan titik "
                             "slack 144 tidak berimpit dengan slack feeder lain.",
                             "Proposal: a new feeder from %s, %s long (OTB 144, 144C cable then %dC). Make sure its "
                             "144-fibre slack point does not share a spot with another feeder's slack.") % (
            h["pop"]["nama"] if h["pop"] else "POP", m(fb["panjang_m"]), int(prm["core_feeder_baru"])))
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
