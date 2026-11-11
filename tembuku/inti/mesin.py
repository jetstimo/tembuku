# -*- coding: utf-8 -*-
# Tembuku - mesin keputusan feeder (slide 1-6 "Feeder Design APD Ruas Jalan").
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Untuk setiap FDT target:

 1. Kumpulkan kabel di sekitar FDT: kabel nasional (indeks nasional) + kabel baru di Compile APD Feeder (slide 2).
 2. Kapasitas tiap kabel (slide 4 "feeder yang masih tersedia tubenya"):
      kabel nasional : tube bebas = floor(NUM_SPARE_ / core per tube); NUM_SPARE_ kosong = BELUM TERVERIFIKASI.
      Compile : tube kabel - jumlah FDT yang sudah dilayani feeder yang sama (1 FDT = 1 tube, kebijakan).
 3. Graf gabungan: kabel eksisting (tiang eksisting, faktor 0,8) + jalan OSM (faktor 1,0-1,3) + sambungan antar-kabel
    (<= 12 m) & kabel-jalan (<= 25 m) + akses FDT (<= 150 m). Dijkstra SEKALI dari FDT memberi biaya kabel baru ke
    SETIAP calon titik tap (setara multi-source; Dijkstra 1959).
 4. Dijkstra kedua dari POP hanya di atas kabel: membuktikan kabel yang dipetik memang tersambung ke POP, memberi
    panjang colo (link budget) dan ARAH kabel di titik tap (slide 4 "searah untuk FDT").
 5. Tap terbaik per kabel = titik dengan kabel baru termurah yang searah (cos >= 0,5 atau FDT <= 300 m).
 6. Keputusan (slide 3): COLO bila ada kandidat lolos kapasitas, arah, detour, panjang cabang, link budget, dan kabel
    barunya < 85 % feeder baru dari POP; selain itu FEEDER BARU dari POP (slide 8-10, digambar sebagai usulan).
 7. Jalur digambar dari titik tap ke FDT (slide 5-6), dipecah per jenis infrastruktur: tiang jaringan eksisting (di atas
    kabel nasional), tiang FTTH on-going (di atas kabel compile), New Infra (jalan / tiang baru)."""
import math

from . import geo, osm, profil, validasi
from .teks import T, gabung, m, km, kali, db
from .graf import Graf, INF

_CACHE_PAKAI = {}


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

    def kabel_compile(self, bb):
        out = []
        for c in self.compiles:
            pakai = self._pakai_kabel(c)
            for k in c["kabel"]:
                if k["jenis"] != "NEW_CABLE" or k["traksi"] in self.kecuali:
                    continue
                if not _bb_kena(k["ll"], bb):
                    continue
                d = dict(k)
                d["grup"] = (c["berkas"], k["pop_folder"], k["feeder"])
                d["fdt_di_feeder"] = sorted(pakai.get(k["id"], ()))
                out.append(d)
        return out

    def _pakai_kabel(self, c):
        """FDT yang dilayani SETIAP kabel compile = FDT traksi pemiliknya + FDT traksi lain yang colo di atasnya
        (Colo Cable berimpit >= 50 % dengan kabel itu, toleransi 15 m). Hasil disimpan per himpunan pengecualian."""
        kunci = (id(c), frozenset(self.kecuali))
        if kunci in _CACHE_PAKAI:
            return _CACHE_PAKAI[kunci]
        fdt_traksi = {}
        for (_b, _p, _f, kode), t in c["traksi"].items():
            if kode not in self.kecuali:
                fdt_traksi[kode] = set(f["kode"].upper() for f in t["fdt"])
        kab = [k for k in c["kabel"] if k["jenis"] == "NEW_CABLE" and k["traksi"] not in self.kecuali]
        pakai = {k["id"]: set(fdt_traksi.get(k["traksi"], ())) for k in kab}
        semua_traksi = list(c["traksi"].items())
        for c2 in self.compiles:
            if c2 is not c and c2.get("berkas") == "_TEMBUKU_BATCH":
                for kk, t in c2["traksi"].items():
                    fdt_traksi[kk[3]] = set(f["kode"].upper() for f in t["fdt"])
                    semua_traksi.append((kk, t))
        for (_b, _p, _f, kode), t in semua_traksi:
            if kode in self.kecuali or not t["colo"]:
                continue
            L = geo.Lokal(*t["colo"][0]["ll"][0])
            pts = [p for col in t["colo"] for p in geo.rapatkan([L.ke(q) for q in col["ll"]], 20)]
            for k in kab:
                if k["traksi"] == kode:
                    continue
                xy = [L.ke(q) for q in k["ll"]]
                xs, ys = [p[0] for p in xy], [p[1] for p in xy]
                dekat = [p for p in pts if min(xs) - 15 <= p[0] <= max(xs) + 15 and min(ys) - 15 <= p[1] <= max(ys) + 15]
                if not dekat:
                    continue
                n = sum(1 for p in dekat if geo.terdekat_di_garis(p, xy)[0] <= 15)
                if n >= 3 and n >= 0.5 * min(len(dekat), len(geo.rapatkan(xy, 20))):
                    pakai[k["id"]] |= fdt_traksi.get(kode, set())
        _CACHE_PAKAI[kunci] = pakai
        return pakai

    def kabel_nasional(self, bb):
        out = []
        for ix in self.indeks:
            out.extend(ix.di_bbox(bb))
        return out


def _sama_pop(a, b):
    return geo.haversine(a["ll"], b["ll"]) < 30


def _bb_kena(ll, bb):
    xs = [c[0] for c in ll]
    ys = [c[1] for c in ll]
    return max(xs) >= bb[0] and min(xs) <= bb[2] and max(ys) >= bb[1] and min(ys) <= bb[3]


# ----------------------------------------------------------------------------- kapasitas
def kapasitas(k, prm, butuh_core):
    """-> (status, tube_bebas, teks). status: LOLOS / PENUH / BELUM_TERVERIFIKASI / BUKAN_FEEDER."""
    cpt = prm["core_per_tube"]
    if k["sumber"] == "NASIONAL":
        boleh = [x.strip().upper() for x in str(prm["produk_feeder"]).split(",") if x.strip()]
        if (k.get("product") or "").upper() not in boleh:
            return "BUKAN_FEEDER", None, T("%s %s: hanya jalur tiang (colo pole), bukan feeder FTTH",
                                           "%s %s: pole route only (colo pole), not an FTTH feeder") % (
                k.get("product") or "-", k.get("owner") or "")
        if k.get("core") and k["core"] < prm["core_feeder_min"]:
            return "BUKAN_FEEDER", None, T("%d core: terlalu kecil untuk feeder (minimal %d core), dianggap kabel "
                                           "distribusi", "%d fibres: too small for a feeder (at least %d), treated as a "
                                           "distribution cable") % (k["core"], prm["core_feeder_min"])
        if k.get("spare") is None:
            return "BELUM_TERVERIFIKASI", None, T("jumlah core cadangan (spare) tidak tercatat di inventaris kabel",
                                                  "spare fibre count not recorded in the cable inventory")
        c = k.get("cpt") or cpt
        if prm["mode_kapasitas"] == "core":
            ok = k["spare"] >= butuh_core
            return ("LOLOS" if ok else "PENUH"), int(k["spare"] // c), T("cadangan %d core (butuh %d core)", "%d spare fibres (%d needed)") % (
                k["spare"], butuh_core)
        bebas = int(k["spare"] // c) - prm["cadangan_tube"]
        return ("LOLOS" if bebas >= prm["tube_per_fdt"] else "PENUH"), bebas, T("cadangan %d core = %d tube kosong", "%d spare fibres = %d free tubes") % (
            k["spare"], max(bebas, 0))
    core = k.get("core")
    if not core:
        return "BELUM_TERVERIFIKASI", None, T("ukuran kabel tidak terbaca", "cable size could not be read")
    tube = core // cpt
    terpakai = len(k.get("fdt_di_feeder") or ())
    if prm["mode_kapasitas"] == "core":
        sisa = core - terpakai * max(butuh_core, 1)
        return ("LOLOS" if sisa >= butuh_core else "PENUH"), sisa // cpt, T("%d core, sudah %d FDT di feeder ini",
                                                                    "%d fibres, already used by %d FDT(s)") % (core, terpakai)
    bebas = tube - terpakai * prm["tube_per_fdt"] - prm["cadangan_tube"]
    return ("LOLOS" if bebas >= prm["tube_per_fdt"] else "PENUH"), bebas, T("%d core = %d tube, sudah melayani %d FDT",
                                                                         "%d fibres = %d tubes, already used by %d FDT(s)") % (
        core, tube, terpakai)


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
    kab = kb + data.kabel_compile(bb)
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
    if pop:
        P = L.ke(pop["ll"])
        np_ = G.simpul(P)
        for d, j in G.dekat(P, 300.0, lambda j: j != np_)[:8]:
            G.tepi(np_, j, "AKSES", None, prm["faktor_akses"])
        # garis bantu POP->FDT (dipakai hanya bila tidak ada jalur jalan/kabel yang lebih murah)
        G.tepi(np_, nf, "BEBAS", None, prm["faktor_bebas"] * (2.0 if jalan else 1.0))

    # kapasitas & kandidat
    kand = {}
    for k in kab:
        st, bebas, teks = kapasitas(k, prm, butuh_core)
        k["kap"] = (st, bebas, teks)
        if st == "LOLOS" or (st == "BELUM_TERVERIFIKASI" and prm["pakai_spare_kosong"]):
            kand[k["id"]] = k
    # garis bantu lurus ke titik terdekat setiap kandidat (dipakai hanya bila lebih murah dari jalur jalan/kabel)
    fb = prm["faktor_bebas"] * (2.0 if jalan else 1.0)
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

    # node per kandidat
    per_ref = {}
    for i, rs in enumerate(G.refs):
        for r in rs:
            if r in kand:
                per_ref.setdefault(r, []).append(i)
    daftar = []
    for kid, nodes in per_ref.items():
        k = kand[kid]
        best = best_any = None
        for v in nodes:
            c = distA[v]
            if c == INF:
                continue
            lurus = math.hypot(G.xy[v][0], G.xy[v][1])
            cosv, sumber_arah = _arah(G, v, kid, prevB, u, L, pop)
            searah = lurus <= prm["jarak_dekat_m"] or cosv is None or cosv >= prm["cos_arah_min"]
            rec = (c, v, cosv, searah, lurus, sumber_arah)
            if best_any is None or c < best_any[0]:
                best_any = rec
            if searah and (best is None or c < best[0]):
                best = rec
        if best_any is None:
            continue
        pilihan = best if best is not None and best[0] <= best_any[0] * 1.5 else best_any
        daftar.append(_nilai_kandidat(G, k, pilihan, prevA, distB, prevB, prm, L.ke(pop["ll"]) if pop else None, byid))
    daftar.sort(key=lambda d: d["skor"])
    hasil["kandidat"] = daftar[:8]
    hasil["n_kabel_diperiksa"] = len(kab)
    hasil["n_kandidat_kapasitas"] = len(kand)
    hasil["ada_jalan"] = bool(jalan)

    # feeder baru dari POP
    if np_ is not None and distA[np_] < INF:
        hasil["feeder_baru"] = _rakit_rute(G, prevA, np_, byid, prm["faktor_garis_bantu"])
        hasil["feeder_baru"]["biaya"] = distA[np_]
    _putuskan(hasil, prm)
    hasil["penomoran"] = penomoran(hasil, data)
    hasil["lokal"] = (F[0], F[1])
    return hasil


def komit(h, data, prm):
    """Masukkan hasil desain (kabel baru + FDT) ke data sebagai traksi virtual, agar FDT berikutnya dalam satu batch
    melihat kapasitas terbaru dan dapat memetik kabel yang baru didesain (pola riil: F2_T5 memetik 48C milik F2_T4)."""
    if h["keputusan"] not in ("COLO", "COLO_CEK", "COLO_MANUAL", "FEEDER_BARU"):
        return
    rute = h["terpilih"]["rute"] if h.get("terpilih") else h.get("feeder_baru")
    if not rute or len(rute["titik"]) < 2:
        return
    L = geo.Lokal(*h["lokal"])
    n = h["penomoran"]
    kode = "F%d_T%d_TEMBUKU_%s" % (n["feeder"], n["t"], h["fdt"]["kode"])
    core = int(prm["core_feeder_baru"] if h["keputusan"] == "FEEDER_BARU" else prm["core_cabang"])
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
    sel = h.get("terpilih")
    if sel and sel.get("colo_xy"):
        colo.append({"ll": [L.balik(p) for p in sel["colo_xy"]]})
        # FDT baru juga terhitung di kabel yang dipetik (kabel compile asli)
        for cc in data.compiles:
            for t in cc["traksi"].values():
                if t["kode"] == sel.get("traksi"):
                    t.setdefault("_tambahan", []).append(fdt["kode"])
    c["traksi"][("_TEMBUKU_BATCH", popf, str(n["feeder"]), kode)] = {
        "kode": kode, "pop_folder": popf, "feeder": str(n["feeder"]), "berkas": "_TEMBUKU_BATCH", "fdt": [fdt],
        "kabel": [kab], "colo": colo, "closure": [], "lain": []}
    c["kabel"].append(kab)
    c["fdt"].append(fdt)
    _CACHE_PAKAI.clear()


def _pop_traksi(popf, c, data):
    """Nama POP sebuah traksi: dari nama folder POP (mis. 'BITUNG POP 1' -> 'KOTA BITUNG POP 1'), atau - bila compile tidak
    punya folder POP (contoh: Tomohon) - satu-satunya POP/OLT di compile itu."""
    pf = (popf or "").upper().strip()
    if pf:
        for p in data.pops:
            pn = p["nama"].upper()
            if pf == pn or pn.endswith(pf) or pf in pn:
                return p["nama"]
        return popf
    if len(c.get("pops") or []) == 1:
        return c["pops"][0]["nama"]
    return "?" + c.get("berkas", "")


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
    """Feeder & nomor T untuk folder KMZ: colo -> Feeder kabel yang dipetik, T berikutnya; feeder baru -> nomor feeder
    berikutnya di POP yang dipakai, T1. Nomor dibaca dari Compile APD Feeder yang dimuat (traksi tersembunyi diabaikan)."""
    import re
    sel = h.get("terpilih")
    pop = h.get("pop") or {}
    traksi = []          # (nama POP, folder POP, feeder, T)
    for c in data.compiles:
        for (b, popf, fdr, kode), t in c["traksi"].items():
            if kode in data.kecuali:
                continue
            inf = t.get("info") or {}
            nomor_t = validasi.nomor_tube(inf.get("t", ""))
            if inf.get("feeder") and nomor_t:
                traksi.append((_pop_traksi(popf, c, data), popf, int(inf["feeder"]), nomor_t))
    asal = None
    if sel and sel["sumber"] == "COMPILE" and sel.get("feeder"):
        c0 = next((c for c in data.compiles if c["berkas"] == (sel.get("grup") or ("",))[0]), {})
        asal = (int(sel["feeder"]), sel.get("pop_folder") or "", c0)
    elif sel and h["keputusan"] != "FEEDER_BARU":
        asal = _feeder_kabel_inventaris(h, sel, data)
    if asal:
        n, popf_sel, c0 = asal
        sel = dict(sel, pop_folder=popf_sel)
        pnama = _pop_traksi(popf_sel, c0, data)
        pakai = set()
        for x in traksi:
            if x[0] == pnama and x[2] == n:
                pakai |= x[3]
        pop_unik = set(x[0] for x in traksi)
        kunci = [re.sub(r"[^A-Z0-9]", "", str(s or "").upper().replace(".KMZ", "")) for s in (pnama, sel.get("pop_folder"))]
        for apop, afdr, at in getattr(data, "audit", ()):
            ap = re.sub(r"[^A-Z0-9]", "", apop.upper())
            if afdr == n and (len(pop_unik) <= 1 or not ap or any(k and (ap in k or k in ap) for k in kunci)):
                pakai |= at
        t = max(pakai or [0]) + 1
        if t > TUBE_PER_FEEDER:
            kosong = [i for i in range(1, TUBE_PER_FEEDER + 1) if i not in pakai]
            if kosong:
                t = kosong[0]
                pesan = T("Feeder %d: nomor T terakhir sudah %d, jadi dipakai nomor yang belum tercatat (T%d). Nomor ini "
                          "baru kandidat: pastikan tube-nya benar-benar kosong sebelum dipakai.",
                          "Feeder %d: the last T number is already %d, so an unrecorded number is used (T%d). It is only "
                          "a candidate: confirm the tube is really free before using it.") % (n, TUBE_PER_FEEDER, t)
            else:
                pesan = T("Feeder %d: semua %d nomor T sudah tercatat terpakai. Periksa apakah masih ada tube kosong, atau "
                          "pilih feeder lain / feeder baru.",
                          "Feeder %d: all %d T numbers are already recorded as used. Check whether a tube is still free, "
                          "or choose another feeder / a new feeder.") % (n, TUBE_PER_FEEDER)
            if str(pesan) not in [str(x) for x in h.setdefault("peringatan", [])]:
                h["peringatan"].append(pesan)
        return {"pop_folder": sel.get("pop_folder") or pnama, "feeder": n, "t": t, "baru": False,
                "t_tercatat": sorted(pakai)}
    pnama = pop.get("nama", "POP")
    sama = [x for x in traksi if x[0] == pnama]
    folder = next((x[1] for x in sama if x[1]), pnama)
    n = max([x[2] for x in sama] or [0]) + 1
    return {"pop_folder": folder, "feeder": n, "t": 1, "baru": h["keputusan"] == "FEEDER_BARU"}


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


def _nilai_kandidat(G, k, pilihan, prevA, distB, prevB, prm, P, byid):
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
    st, bebas, teks = k["kap"]
    if colo_m is not None:
        feeder_km = colo_m / 1000.0
    elif P is not None:
        feeder_km = prm["faktor_jalur_feeder"] * math.hypot(G.xy[v][0] - P[0], G.xy[v][1] - P[1]) / 1000.0
    else:
        feeder_km = 5.0
    alasan, gagal = [], []
    jalur_serat = (colo_m if colo_m is not None else feeder_km * 1000.0) + pjg_est
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
    if detour > prm["detour_maks"]:
        gagal.append(T("kabel baru harus memutar (%s jarak lurus, batas %s)",
                       "the new cable would go a long way round (%s the straight distance, limit %s)") % (
            kali(detour), kali(prm["detour_maks"])))
    if pjg > prm["cabang_maks_m"]:
        gagal.append(T("kabel baru terlalu panjang (%s, batas %s)", "new cable too long (%s, limit %s)") % (
            m(pjg), m(prm["cabang_maks_m"])))
    if colo_m is None:
        alasan.append(T("feeder ini belum terlihat tersambung ke POP di data: cek di lapangan",
                        "this feeder is not shown as connected to the POP in the data: check on site"))
    bud = link_budget(feeder_km + pjg / 1000.0, prm, splice=4 + len(set(r for r in rute["ref_kabel"])))
    if bud["margin_db"] < 0:
        gagal.append(T("redaman sinyal terlalu besar (%s, batas %s)", "signal loss too high (%s, limit %s)") % (
            db(bud["total_db"]), db(prm["kelas_olt_db"])))
    skor = c * (1.0 + (0.5 if st == "BELUM_TERVERIFIKASI" else 0) + (0.3 if colo_m is None else 0) +
                (1.0 if gagal else 0))
    llk = k["ll"]
    if len(llk) > 400:
        llk = llk[::int(math.ceil(len(llk) / 400.0))] + [llk[-1]]
    return {"ll_kabel": llk, "id": k["id"], "sumber": k["sumber"], "nama": k.get("nama") or k.get("traksi") or "", "model": k.get("model"),
            "owner": k.get("owner"), "product": k.get("product"), "core": k.get("core"), "spare": k.get("spare"),
            "kapasitas": st, "tube_bebas": bebas, "ket_kapasitas": teks, "label_colo": label_colo(k),
            "feeder": k.get("feeder"), "pop_folder": k.get("pop_folder"), "traksi": k.get("traksi"),
            "grup": k.get("grup"), "tap_simpul": v, "cos": None if cosv is None else round(cosv, 2),
            "sumber_arah": sumber_arah, "searah": searah, "lurus_m": round(lurus), "kabel_baru_m": round(pjg),
            "detour": round(detour, 2), "colo_m": None if colo_m is None else round(colo_m), "colo_xy": colo_xy,
            "jalur_serat_m": round(jalur_serat), "rute": rute, "budget": bud, "gagal": gagal, "catatan": alasan, "skor": skor,
            "lolos": not gagal and st == "LOLOS", "biaya": c}


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
            "margin_db": round(prm["kelas_olt_db"] - total, 2), "splice": splice}


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
    h["kandidat"].sort(key=lambda d: d["skor"])
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
    lolos = [k for k in h["kandidat"] if k["lolos"]]
    cek = [k for k in h["kandidat"] if not k["gagal"] and k["kapasitas"] == "BELUM_TERVERIFIKASI"]
    batas = INF
    if lolos and lolos[0]["kabel_baru_m"] < batas:
        h["keputusan"], h["terpilih"] = "COLO", lolos[0]
        k = lolos[0]
        h["alasan"].append(T("Pakai feeder %s (%s): masih ada tube kosong dan arahnya menuju FDT. Kabel baru dari titik "
                             "sambung (tap) ke FDT: %s.%s",
                             "Use feeder %s (%s): it has a free tube and runs toward the FDT. New cable from the tap "
                             "point to the FDT: %s.%s") % (
            k["nama"] or k["id"], k["label_colo"], m(k["kabel_baru_m"]),
            (T(" Sebagai pembanding, feeder baru dari POP: %s.", " For comparison, a new feeder from the POP: %s.")
             % m(fb["panjang_m"])) if fb else ""))
    elif cek and cek[0]["kabel_baru_m"] < batas:
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
        h["alasan"].append(T("Usulan: feeder baru dari %s sepanjang %s. Pastikan titik slack 144 tidak berimpit dengan "
                             "slack feeder lain.",
                             "Proposal: a new feeder from %s, %s long. Make sure its 144-fibre slack point does not "
                             "share a spot with another feeder's slack.") % (
            h["pop"]["nama"] if h["pop"] else "POP", m(fb["panjang_m"])))
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
