# -*- coding: utf-8 -*-
# Tembuku - pengenal sumber data & pembaca Compile APD Feeder.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Peran berkas dikenali dari ISI (atribut/folder), nama berkas hanya petunjuk tambahan:

  NASIONAL  : placemark garis dengan atribut MODEL / NUM_SPARE_ / Owner (KMZ inventaris kabel nasional)
  COMPILE   : folder 'F<n>_T<k>_..._APD Feeder KMZ_...' di bawah 'Feeder <n>' (KMZ Compile APD Feeder)
  TARGET    : titik FDT (folder FDT atau kode FDT 'ABC1-XYZ01-H01') di KMZ Distribusi / Design Lite / cluster
  POP       : titik POP/OLT (KMZ All POP)

Struktur Compile APD Feeder (dibaca dari data Bitung & Tomohon, 4-5 Nov 2026):
  <kota> POP <n> / Feeder <n> / F<n>_T<k>_<ID cluster>_APD Feeder KMZ_<area>_<tgl> / {Cable, Hanger, Closure, OTB, FDT,
  OLT, Keterangan Infra}. Kabel baru di 'Cable/New Cable Aerial/Udara/New Cable <core>C', colo di 'Cable/Collo Cable'.
Semua nama folder, kode FDT, ukuran kabel, splitter dan koordinat dibaca lewat validasi.py (toleran typo, dicatat)."""
import os
import re

from . import atribut, baca, kml_aman, kabel
from . import validasi as V
from .teks import T, gabung

NAMA_PERAN = {"NASIONAL": T("inventaris kabel", "cable inventory"),
              "COMPILE": T("compile desain feeder", "feeder design compilation"),
              "TARGET": T("titik FDT", "FDT points"), "POP": T("daftar POP", "POP list"),
              "AUDIT": T("catatan tube feeder", "feeder tube record"), "LAIN": T("lainnya", "other")}

RX_POPF = re.compile(r"\bPOP\s*\d*\b", re.I)
RX_SITE = re.compile(r"(^|_|\s)site[_\s]?id$", re.I)     # atribut ID lokasi (umum di KMZ POP/OLT)
PETUNJUK_NASIONAL = ["ALL CABLE", "CABLE INVENTORY", "INVENTARIS KABEL"]
ATRIBUT_POP = []


def pakai_istilah(d):
    """Petunjuk nama berkas & atribut POP dari profil istilah organisasi (tanpa nama merek di kode)."""
    PETUNJUK_NASIONAL[:] = [str(x).upper() for x in (d.get("petunjuk_berkas_nasional") or [])]
    ATRIBUT_POP[:] = [str(x) for x in (d.get("atribut_pop") or [])]


def _tanda_pop(a):
    return any(k in a for k in ATRIBUT_POP) or any(RX_SITE.search(k) for k in a)


def _tanda_pop_luas(pm):
    """Titik POP/OLT/STO dari isi: atribut bermakna lokasi POP, nama atau folder yang menyebut POP/OLT/STO."""
    a, nm = pm["attrs"], (pm["name"] or "").upper()
    folder = " / ".join(pm["path"][-2:]).upper()
    if _tanda_pop(a) or atribut.ada(a, "pop"):
        return True
    if atribut.RX_KATA_FDT.search(nm) or atribut.RX_KATA_AKSESORI.search(nm):
        return False
    return bool(atribut.RX_KATA_POP.search(nm) or RX_POPF.search(pm["name"] or "") or
                any(f.upper().strip() in ("POP", "OLT", "ALL POP", "STO", "LIST POP", "DAFTAR POP", "SITE POP")
                    for f in pm["path"][-2:]) or (atribut.RX_KATA_POP.search(folder) and not
                                                    atribut.RX_KATA_FDT.search(folder)))


def _tanda_fdt(pm):
    """Titik FDT/ODC dari isi: kode berpola FDT, kata FDT/ODC di nama atau folder, atau atribut kode FDT/splitter."""
    nm = (pm["name"] or "").strip()
    up = nm.upper()
    if atribut.RX_KATA_AKSESORI.search(up) and not atribut.RX_KATA_FDT.search(up):
        return False
    if _turunan_fdt(nm):
        return False
    folder = " / ".join(pm["path"][-2:]).upper()
    return bool(_seperti_fdt(nm) or atribut.RX_KATA_FDT.search(up) or atribut.ada(pm["attrs"], "kode_fdt") or
                atribut.ada(pm["attrs"], "splitter") or (atribut.RX_KATA_FDT.search(folder) and
                                                          not atribut.RX_KATA_AKSESORI.search(folder)))
RX_FDT = re.compile(r"^[A-Z]{2,4}\d?-[A-Z]{2,4}\d{1,3}-H\d{1,3}$")
RX_FDT_LONGGAR = re.compile(r"^[A-Za-z]{2,4}\d[\s_\-.]*[A-Za-z]{2,4}\d{1,2}[\s_\-.]*[Hh]\d{1,2}$")
# '<ID>_APD Feeder KMZ_<area>_<tgl>' dan juga '<ID>_APD Feeder_<area>_<tgl>' (tanpa KMZ, dipakai desainer Bengkulu):
# tanpa ini nama area menjadi 'APD Feeder_<area>' dan nama folder hasil berulang ('APD Feeder KMZ_APD Feeder_...')
RX_CLUSTER = re.compile(r"(\d{9,12})_APD[\s_]+(?:Distribusi|Feeder|Distribution)(?:[\s_]+KMZ)?_(.+?)"
                        r"(?:_\d{2}-\d{2}-\d{4}.*)?(?:\.kmz)?$", re.I)
RX_TGL = re.compile(r"_(\d{2}-\d{2}-\d{4})")


RX_TURUNAN_FDT = re.compile(r"^[A-Za-z]{2,4}\d?[\s_\-.]*[A-Za-z]{2,4}\d{1,3}[\s_\-.]*[Hh]\d{1,3}[\s_\-./]+\S")


def _turunan_fdt(nama):
    """Nama yang DIAWALI kode FDT lalu masih bersambung (mis. 'GSK1-CUL01-H03-D01-01'): itu kabel/FAT/titik distribusi
    milik FDT tersebut, BUKAN titik FDT-nya. Tidak pernah dipakai sebagai lokasi FDT."""
    return bool(RX_TURUNAN_FDT.match((nama or "").strip()))


def _seperti_fdt(nama):
    return bool(RX_FDT.match(nama or "") or RX_FDT_LONGGAR.match((nama or "").strip()))


TANDA_TEMBUKU = "Dibuat oleh Tembuku"


def keluaran_tembuku(path):
    """True bila berkas adalah KMZ/KML hasil Tembuku sendiri (keterangan dokumen memuat tanda pembuat). Hasil lama di
    folder data tidak boleh ikut terbaca sebagai compile/FDT - itu membuat kapasitas dan nomor F/T tercemar."""
    try:
        if baca.jenis(path) not in ("KMZ", "KML"):
            return False
        src = kml_aman.buka(path)
        try:
            head = src.read(8192)
        finally:
            src.close()
        return TANDA_TEMBUKU.encode("utf-8") in head
    except Exception:
        return False


def intip(path, n=1500):
    """Kenali peran berkas dari ISI objeknya (nama berkas hanya petunjuk kecil). -> (peran, skor, bukti).

    Tanda yang dihitung (contoh di sampai n objek pertama, cukup untuk berkas raksasa sekalipun):
      inventaris kabel : garis dengan ukuran core (atribut, model 'n/t' atau teks '96C') dan core cadangan/terpakai,
                         biasanya juga pemilik, produk atau status;
      compile desain   : folder traksi berpola F<n>_T<k>, atau 'unit desain' = folder yang berisi titik FDT dan garis
                         kabel sekaligus, di berkas yang juga memuat POP/OLT atau kata feeder (bukan distribusi);
      titik FDT        : titik berkode FDT/ODC, di folder FDT/ODC, atau beratribut kode FDT/splitter;
      daftar POP       : titik bernama/berfolder POP/OLT/STO atau beratribut site/OLT/hostname."""
    f = dict.fromkeys(("garis", "titik", "garis_core", "garis_spare", "garis_atr", "fdt", "pop", "traksi", "fat",
                       "feeder_kata"), 0)
    prefiks = {}
    k = 0
    for pm in baca.placemarks(path):
        k += 1
        a, nm, pth = pm["attrs"], pm["name"] or "", pm["path"]
        g0 = pm["geoms"][0][0]
        up_path = " / ".join(pth).upper()
        if any(V.baca_traksi(x) for x in pth):
            f["traksi"] += 1
        if "FEEDER" in up_path or "OLT" in up_path:
            f["feeder_kata"] += 1
        if g0 == "LineString":
            f["garis"] += 1
            core = atribut.core_dari(a, nm, pth[-1] if pth else "")
            if core:
                f["garis_core"] += 1
            if "NUM_SPARE_" in a or atribut.spare_dari(a) is not None:
                f["garis_spare"] += 1
            if atribut.ada(a, "owner") or atribut.ada(a, "produk") or atribut.ada(a, "status") or "MODEL" in a:
                f["garis_atr"] += 1
            ciri = "C" if (core or "CABLE" in up_path or "KABEL" in up_path) else None
        else:
            f["titik"] += 1
            ciri = None
            if _tanda_pop_luas(pm):
                f["pop"] += 1
            elif _tanda_fdt(pm):
                f["fdt"] += 1
                ciri = "F"
            elif re.search(r"(^|[^A-Z])(FAT|ODP|HP|HOMEPASS)([^A-Z]|$)", (nm + " / " + up_path).upper()):
                f["fat"] += 1
        if ciri:
            for i in range(1, len(pth) + 1):
                prefiks.setdefault(tuple(pth[:i]), set()).add(ciri)
        if k >= n:
            break
    if k == 0:
        return "KOSONG", {}, ""
    dua = {p for p, c in prefiks.items() if c == {"C", "F"}}
    unit = [p for p in dua if not any(q != p and q[:len(p)] == p for q in dua)]
    f["unit"] = len(unit)
    skor = {"NASIONAL": 0.0, "COMPILE": 0.0, "TARGET": 0.0, "POP": 0.0}
    skor["NASIONAL"] = 2.0 * f["garis_spare"] + 0.5 * min(f["garis_core"], f["garis_atr"]) + 0.2 * f["garis_atr"]
    distribusi = f["fat"] > max(3, f["fdt"])          # banyak FAT/ODP/homepass: berkas desain distribusi (target)
    if f["traksi"] or (f["unit"] and not distribusi and (f["feeder_kata"] or f["pop"])):
        skor["COMPILE"] = 1.0 * f["traksi"] + 20.0 * f["unit"] + (5.0 if f["pop"] else 0.0)
        skor["NASIONAL"] *= 0.2
    skor["TARGET"] = 1.0 * f["fdt"] + (2.0 if distribusi and f["fdt"] else 0.0)
    skor["POP"] = 1.5 * f["pop"] if f["pop"] >= max(1, f["fdt"]) and f["garis"] <= f["titik"] else 0.5 * f["pop"]
    if f["fdt"] and f["fdt"] >= 0.5 * f["titik"] and f["garis"] <= f["fdt"]:
        skor["TARGET"] += 3          # berkas (hampir) hanya berisi titik FDT: daftar rencana, walau cuma 1 titik
    if f["pop"] and f["fdt"] == 0 and f["garis"] == 0 and f["pop"] >= 0.5 * f["titik"]:
        skor["POP"] += 3             # daftar POP/OLT murni
    nama = os.path.basename(path).upper()
    if "NASIONAL" in nama or any(p in nama for p in PETUNJUK_NASIONAL):
        skor["NASIONAL"] += 2
    if "COMPILE" in nama or re.search(r"FEEDER\s*ALL", nama):
        skor["COMPILE"] += 2
    if "POP" in nama and "FEEDER" not in nama:
        skor["POP"] += 2
    if "DISTRIBUSI" in nama or "DESIGN LITE" in nama or "DESIGN_LITE" in nama:
        skor["TARGET"] += 2
    if skor["COMPILE"] > 0:
        skor["TARGET"] = 0           # FDT di compile = FDT yang sudah didesain feeder-nya
    peran = max(skor, key=lambda x: skor[x])
    if skor[peran] <= 2:             # hanya petunjuk nama berkas, isi tidak cocok dengan peran apa pun
        peran = "LAIN"
    return peran, skor, _bukti(peran, f, k)


def _bukti(peran, f, k):
    """Alasan pengenalan dalam bahasa awam (dua bahasa)."""
    if peran == "NASIONAL":
        return T("%d dari %d objek pertama adalah garis kabel; %d punya ukuran core dan %d punya data core cadangan",
                 "%d of the first %d objects are cable lines; %d have a fibre count and %d have spare-fibre data") % (
            f["garis"], k, f["garis_core"], f["garis_spare"])
    if peran == "COMPILE":
        if f["traksi"]:
            return T("objek tersusun dalam folder traksi F/T (%d objek) berisi titik FDT dan garis kabel",
                     "objects are grouped in F/T route folders (%d objects) holding FDT points and cable lines") % f["traksi"]
        return T("%d folder berisi titik FDT dan garis kabel sekaligus, dengan POP/OLT atau feeder di berkas yang sama",
                 "%d folders hold both FDT points and cable lines, with POP/OLT or feeders in the same file") % f["unit"]
    if peran == "TARGET":
        return T("%d titik dikenali sebagai FDT/ODC (dari kode, nama, folder atau atribut splitter)",
                 "%d points recognised as FDT/ODC (from code, name, folder or splitter field)") % f["fdt"]
    if peran == "POP":
        return T("%d titik dikenali sebagai POP/OLT/STO", "%d points recognised as POP/OLT/STO") % f["pop"]
    return T("isinya tidak cocok dengan jenis data yang dipakai Tembuku (%d garis, %d titik)",
             "its content does not match any data type Tembuku uses (%d lines, %d points)") % (f["garis"], f["titik"])


def _fdt_rec(pm, ll, temuan, base):
    kt = " FDT %s" % pm["name"]
    spl, rat = V.koreksi_splitter(V.atribut(pm["attrs"], "SPLITTERS", temuan, base, kt) or "", temuan, base, kt)
    return {"kode": V.koreksi_fdt(pm["name"], temuan, base), "ll": ll, "splitter": spl, "rasio": rat,
            "premises": V.angka_longgar(V.atribut(pm["attrs"], "PREMISES", temuan, base, kt), temuan, base,
                                        " PREMISES %s" % pm["name"])}


def traksi_berkas(path):
    """Kode traksi (F<n>_T<k>_<ID>) di satu KMZ compile - untuk mengenali versi ganda."""
    out = set()
    for pm in baca.placemarks(path):
        for f in pm["path"]:
            t = V.baca_traksi(f)
            if t:
                out.add("F%s_T%s_%s" % (t["feeder"], t["t"], t["cluster"] or ""))
    return out


RX_KATA_COLO = re.compile(r"(^|[^A-Z])(COLO|COLLO|SEWA|LEASE|LEASED|EXISTING CABLE|KABEL EKSISTING)([^A-Z]|$)")
RX_KATA_UG = re.compile(r"(^|[^A-Z])(UG|GALIAN|UNDERGROUND|DUCT|TANAM|DUCTING)([^A-Z]|$)")
RX_KATA_BARU = re.compile(r"(^|[^A-Z])(NEW|BARU|RENCANA|PLAN|PLANNED|PROPOSED|USULAN|DESIGN)([^A-Z]|$)")
RX_NOMOR_FEEDER = re.compile(r"(?:^|[^A-Z])(?:FEEDER|FDR|PENYULANG|F)\s*[-_ ]?\s*(\d{1,2})(?:[^\d]|$)", re.I)
RX_KELOMPOK = re.compile(r"(^|[^A-Z])(FEEDER|PENYULANG|FDR|POP|OLT|STO|AREA|KOTA|CLUSTER|WILAYAH)([^A-Z]|$)", re.I)
RX_NOMOR_T = re.compile(r"(?:^|[^A-Z])(?:T|TRAKSI|TRK|RUAS|SEG|SEGMENT)\s*[-_ ]?\s*(\d{1,2})(?:[^\d]|$)", re.I)


def _unit_struktur(path):
    """Compile tanpa folder traksi berpola: unit desain dikenali dari STRUKTUR isinya.

    Unit = folder yang memuat titik FDT dan garis kabel, dan yang di dalamnya kabel dan FDT tersimpan terpisah
    (sub-folder/objek yang hanya berisi kabel DAN sub-folder/objek yang hanya berisi FDT) - pola umum template desain
    (unit / {Kabel..., FDT...}). Folder induk (mis. 'Feeder 1') yang hanya berisi unit-unit tidak memenuhi syarat ini.
    Unit di dalam unit = ruas lanjutan (FDT saudara), sama seperti sub-folder traksi berpola.
    -> {prefiks_folder: info traksi}; nomor feeder/traksi dari nama folder bila ada, selain itu berurutan."""
    sub, langsung, urutan = {}, {}, []
    for pm in baca.placemarks(path):
        pth, g0 = tuple(pm["path"]), pm["geoms"][0][0]
        up = " / ".join(pth).upper()
        if g0 == "LineString":
            ciri = "C" if (atribut.core_dari(pm["attrs"], pm["name"], pth[-1] if pth else "") or "CABLE" in up or
                           "KABEL" in up) else None
        else:
            ciri = "F" if _tanda_fdt(pm) and not _tanda_pop_luas(pm) else None
        if not ciri:
            continue
        langsung.setdefault(pth, set()).add(ciri)
        for i in range(1, len(pth) + 1):
            if pth[:i] not in sub:
                urutan.append(pth[:i])
            sub.setdefault(pth[:i], set()).add(ciri)
    anak = {}
    for p in urutan:
        if len(p) > 1:
            anak.setdefault(p[:-1], []).append(p)
    dua = [p for p in urutan if sub[p] == {"C", "F"}]

    def anak_dua(p):
        return [q for q in anak.get(p, []) if sub[q] == {"C", "F"}]

    def kelompok(p):
        """Tingkat pengelompokan (mis. 'Feeder 1', 'POP 2', akar dokumen): berisi >= 2 unit, atau bernama feeder/POP
        dan hanya membungkus satu folder lain yang berisi FDT dan kabel."""
        n = len(anak_dua(p))
        return n >= 2 or (n == 1 and (len(p) <= 2 or RX_KELOMPOK.search(p[-1] or "")))
    unit = []
    for p in dua:
        induk = p[:-1]
        if kelompok(p) or any(u == p[:len(u)] for u in unit):
            continue
        if not induk or induk not in sub or kelompok(induk):
            unit.append(p)
    if not unit:                                    # satu unit saja di berkas: folder FDT+kabel terdalam
        unit = [p for p in dua if not anak_dua(p)][:1]
    out, per_feeder = {}, {}
    for u in unit:
        fdr = None
        for nama in reversed(u):
            m = RX_NOMOR_FEEDER.search(nama)
            if m:
                fdr = int(m.group(1))
                break
        fdr = fdr or 1
        m = RX_NOMOR_T.search(u[-1])
        per_feeder[fdr] = per_feeder.get(fdr, 0) + 1
        t = m.group(1) if m else str(per_feeder[fdr])
        out[u] = {"feeder": fdr, "t": t, "cluster": None, "area": u[-1], "tanggal": None, "struktur": True,
                  "kode": " / ".join(u[-2:]) if len(u) >= 2 else u[-1]}
    return out


RX_NET_CABLE = re.compile(r"^NET[\s._]*CABLES?$")
RX_KET_INFRA = re.compile(r"^KET(ERANGAN)?[\s._]*INFRA$")
RX_NAMA_COLO = re.compile(r"^\s*COLL?O\s*CAB(LE|EL)\b")
RX_CORE_NAMA = re.compile(r"^\s*(\d{2,3})\s*[FCDfcd]\b")


def _jenis_kabel_umum(pth, nama):
    """Jenis garis di compile non-template dari kata kunci folder dan nama (Indonesia/Inggris)."""
    teks = (" / ".join(pth) + " / " + (nama or "")).upper()
    if "TIANG" in teks or "POLE" in teks or "INFRA" in teks:        # jalur tiang (mis. 'Colo Pole 96C'), bukan kabel
        return "INFRA"
    if RX_KATA_COLO.search(teks):
        return "COLO_CABLE"
    if RX_KATA_UG.search(teks):
        return "UG"
    if RX_KATA_BARU.search(teks) or kabel.core_compile(pth[-1] if pth else "", nama):
        return "NEW_CABLE"
    return "INFRA"


RX_EKST_PETA = re.compile(r"\.(kmz|kml|zip|geojson|json)$", re.I)


def _folder_pop(p, path_asli, info):
    """Folder POP sebuah objek compile = folder bernama POP yang TERDEKAT ke folder traksi (di atasnya), bukan nama
    dokumen/berkas (mis. 'BENGKULU POP 4.kmz' sebagai nama Document di atas folder 'BENGKULU POP 4'). Nama berkas
    hanya dipakai bila tidak ada folder POP lain, dan ekstensinya dibuang, agar identitas POP sama di semua wilayah."""
    batas = info[0][0] if info else len(p)
    calon = [(j, f) for j, f in enumerate(p[:batas]) if RX_POPF.search(f) and not V.baca_traksi(f) and not V.baca_feeder(f)]
    if not calon:
        calon = [(j, f) for j, f in enumerate(p) if RX_POPF.search(f) and not V.baca_traksi(f) and not V.baca_feeder(f)]
    if not calon:
        return ""
    nama = calon[-1][1]
    if len(calon) > 1 and RX_EKST_PETA.search(nama):      # nama dokumen di bawah? ambil yang bukan nama berkas
        nama = next((f for _j, f in reversed(calon) if not RX_EKST_PETA.search(f)), nama)
    return RX_EKST_PETA.sub("", nama).strip()


def kunci_pop(nama):
    """Bentuk baku nama POP untuk pencocokan antar sumber: huruf besar, tanpa ekstensi berkas dan tanda baca."""
    s = RX_EKST_PETA.sub("", str(nama or "").strip())
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def baca_compile(path, temuan=None):
    """-> dict(pops, traksi{kunci: {...}}, kabel[...], fdt[...]) dari satu KMZ compile desain feeder.
    Folder traksi berpola F<n>_T<k> dipakai bila ada; bila tidak ada sama sekali, unit desain dikenali dari struktur
    isinya (_unit_struktur) sehingga compile dari template operator lain tetap terbaca."""
    temuan = temuan if temuan is not None else V.Temuan()
    base = os.path.basename(path)
    pops, traksi, kab, fdts = {}, {}, [], []
    n_pm = 0
    struktur = None
    if not traksi_berkas(path):
        struktur = _unit_struktur(path)
        if struktur:
            temuan.tambah(V.INFO, "Nama folder", T("compile ini tidak memakai pola folder F<n>_T<k>; %d unit desain "
                                                   "dikenali dari isinya (folder berisi FDT dan kabel). Nomor F/T diambil "
                                                   "dari nama folder bila ada, selain itu diberi berurutan",
                                                   "this compilation does not use F<n>_T<k> folders; %d design units "
                                                   "were recognised from their content (folders holding an FDT and "
                                                   "cables). F/T numbers come from folder names where present, "
                                                   "otherwise they are numbered in order") % len(struktur), base,
                          T("periksa nomor F/T di hasil", "check the F/T numbers in the results"))
    n_drop = 0
    for pm in baca.placemarks(path):
        n_pm += 1
        if any(str(f).strip().upper() == "DROP" for f in pm["path"]):      # aturan: folder bernama Drop diabaikan
            n_drop += 1
            continue
        p = [V.kanon_folder(f, temuan, base) for f in pm["path"]]
        info = [(j, V.baca_traksi(f, temuan, base)) for j, f in enumerate(p)]
        info = [(j, t) for j, t in info if t]
        if not info and struktur:
            cocok = sorted((u for u in struktur if tuple(pm["path"][:len(u)]) == u), key=len)
            info = [(len(u) - 1, struktur[u]) for u in cocok]     # terluar dulu: unit di dalam unit = ruas lanjutan
        popf = _folder_pop(p, pm["path"], info)
        fdr = next((V.baca_feeder(f, temuan, base) for f in p if V.baca_feeder(f)), None)
        g0, cs = pm["geoms"][0]
        leaf = p[-1] if p else ""
        if g0 == "Point":
            q = V.koreksi_titik(cs[0], temuan, base, " %s" % pm["name"])
            if q is None:
                continue
            cs = [q]
        else:
            cs = V.koreksi_garis(cs, temuan, base, " %s" % pm["name"])
            if cs is None:
                temuan.tambah(INFO_, "Kelengkapan", T("garis '%s' punya kurang dari 2 titik yang sah, dilewati",
                                                      "line '%s' has fewer than 2 valid points, skipped") % pm["name"], base)
                continue
        if g0 == "Point" and (leaf.upper() in ("OLT", "POP") or _tanda_pop(pm["attrs"]) or
                              (struktur and _tanda_pop_luas(pm))):
            pops.setdefault(pm["name"].strip().upper(), {"nama": pm["name"].strip(), "ll": cs[0], "attrs": pm["attrs"]})
            continue
        if not info:
            continue
        j0, t0 = info[0]
        j, _t = info[-1]                 # traksi TERDALAM: sub-folder F.._T.. = FDT colo saudara
        induk = t0.get("kode") or pm["path"][j0]
        if fdr is None:
            fdr = str(t0["feeder"])
        key = (base, popf, fdr, induk)
        t = traksi.setdefault(key, {"kode": induk, "info": t0, "pop_folder": popf, "feeder": fdr, "berkas": base,
                                    "fdt": [], "kabel": [], "colo": [], "closure": [], "slack": [], "lain": []})
        if "tube" not in t["info"]:
            t["info"]["tube"] = V.nomor_tube(t0.get("t", ""))      # nomor T folder = nomor tube kabel induk 144F
        sub = j != j0
        if g0 == "Point" and not _turunan_fdt(pm["name"]) and (
                any("FDT" in f.upper() for f in p[j + 1:]) or _seperti_fdt(pm["name"]) or
                (t0.get("struktur") and _tanda_fdt(pm))):
            rec = _fdt_rec(pm, cs[0], temuan, base)
            rec.update({"traksi": induk, "feeder": fdr, "pop_folder": popf, "colo_saudara": sub,
                        "status": "Eksisting" if "Eksisting FDT" in p else "New", "attrs": dict(pm["attrs"])})
            t["fdt"].append(rec)
            fdts.append(rec)
        elif g0 == "LineString":
            up = leaf.upper()
            jenis = ("COLO_CABLE" if up in ("COLLO CABLE", "COLO CABLE") else
                     "NEW_CABLE" if up.startswith("NEW CABLE") and not up.endswith(" UG") and "GALIAN" not in up
                     and "AERIAL" not in up else "UG" if up.endswith(" UG") else "INFRA")
            if t0.get("struktur"):
                jenis = _jenis_kabel_umum(pm["path"][j0 + 1:], pm["name"])
            lama = None
            if RX_NET_CABLE.match(up):            # susunan lama: Net_Cables = kabel baru, bernama '<core>F <panjang>'
                jenis = "NEW_CABLE"
                lama = RX_CORE_NAMA.match(pm["name"] or "")
            elif RX_KET_INFRA.match(up) and RX_NAMA_COLO.match((pm["name"] or "").upper()):
                jenis = "COLO_CABLE"              # susunan lama: garis 'Colo Cable' disimpan di Ket.Infra
            core = None
            if lama and int(lama.group(1)) in (12, 24, 48, 72, 96, 144, 192, 288):
                core = int(lama.group(1))
            elif jenis == "NEW_CABLE":
                core = V.koreksi_core(leaf, temuan if not RX_NET_CABLE.match(up) else None, base, " (folder %s)" % leaf)
                if core is None:
                    core = V.koreksi_core(pm["name"], None)
            else:
                core = kabel.core_compile(leaf, pm["name"])
            rec = {"id": "C%d" % (len(kab) + 1), "ll": cs, "core": core, "jenis": jenis, "nama": pm["name"],
                   "traksi": induk, "feeder": fdr, "pop_folder": popf, "berkas": base, "sumber": "COMPILE",
                   "warna": pm["warna"], "folder": leaf}
            kab.append(rec)
            (t["colo"] if jenis == "COLO_CABLE" else t["kabel"]).append(rec)
        elif g0 == "Point" and ("CLOSURE" in leaf.upper() or "Eksisting Closure" in p or
                                re.search(r"(^|[^A-Z])(CLOSURE|CL)([^A-Z]|$)", (pm["name"] or "").upper())):
            t["closure"].append({"nama": pm["name"], "ll": cs[0], "eksisting": "Eksisting Closure" in p or
                                 bool(re.search(r"\b(EXT|EKS|EXISTING|EKSISTING)\b", (pm["name"] or "").upper())),
                                 "core": V.koreksi_core(pm["name"], None) or V.koreksi_core(leaf, None)})
        elif g0 == "Point" and re.search(r"SLACK|HANGER|SPARE", (leaf + " " + (pm["name"] or "")).upper()):
            # titik slack/hanger di sepanjang kabel: calon titik sambung (aturan: closure baru tepat di koordinat slack)
            t["slack"].append({"nama": pm["name"], "ll": cs[0], "eksisting": "Eksisting" in leaf})
        else:
            t["lain"].append({"nama": pm["name"], "ll": cs[0], "folder": leaf})
    if n_pm == 0:
        temuan.tambah(V.FATAL, "Kelengkapan", T("KMZ compile tidak berisi objek apa pun", "the compilation KMZ contains "
                                                "no objects"), base,
                      T("ekspor ulang KMZ dari aplikasi pembuatnya", "export the KMZ again from the program that made it"))
    if n_drop:
        temuan.tambah(V.INFO, "Isi data", T("%d objek di dalam folder bernama 'Drop' diabaikan (aturan engineering)",
                                            "%d objects inside folders named 'Drop' were ignored (engineering rule)")
                      % n_drop, base)
    _cek_konsistensi(traksi, temuan, base)
    return {"pops": list(pops.values()), "traksi": traksi, "kabel": kab, "fdt": fdts, "berkas": base}


INFO_ = V.INFO


def _cek_konsistensi(traksi, temuan, base):
    """Konsistensi logis antar-objek compile (ISO 19157: logical consistency)."""
    lokasi = {}
    for key, t in traksi.items():
        own = [f for f in t["fdt"] if not f["colo_saudara"]]
        if not own:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", T("traksi %s tidak punya titik FDT", "route folder %s has no FDT "
                                                         "point") % t["kode"][:40], base,
                          T("tambahkan FDT di folder FDT / New FDT", "add the FDT in the FDT / New FDT folder"))
        if not t["kabel"] and not t["colo"]:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", T("traksi %s tidak punya kabel", "route folder %s has no cable")
                          % t["kode"][:40], base, T("periksa isi folder ini", "check what is in this folder"))
        for k in t["kabel"]:
            if k["jenis"] == "NEW_CABLE" and not k["core"]:
                temuan.tambah(V.PERINGATAN, "Isi data", T("kabel '%s' di %s tidak punya ukuran core",
                                                          "cable '%s' in %s has no fibre count") % (
                    k["nama"], t["kode"][:30]), base, T("sisa tube kabel ini dianggap belum pasti",
                                                        "the free tubes of this cable are treated as unconfirmed"))
        # FDT milik traksi berbeda dengan FDT yang disebut di sub-folder (contoh data riil: F1_T9 POP 2 Bitung)
        sub = set(f["kode"] for f in t["fdt"] if f["colo_saudara"])
        if own and sub and not (set(f["kode"] for f in own) & sub):
            temuan.tambah(V.PERINGATAN, "Kesesuaian data", T("traksi %s: FDT di folder FDT (%s) berbeda dengan FDT di "
                                                             "sub-folder (%s)", "route folder %s: the FDT in the FDT "
                                                             "folder (%s) differs from the FDT in the sub-folder (%s)")
                          % (t["kode"][:40], ", ".join(sorted(set(f["kode"] for f in own))), ", ".join(sorted(sub))),
                          base, T("periksa FDT mana yang benar", "check which FDT is right"))
        for f in t["fdt"]:
            lokasi.setdefault(f["kode"], []).append(f["ll"])
    from . import geo
    for kode, lls in lokasi.items():
        jauh = max((geo.haversine(lls[0], q) for q in lls[1:]), default=0)
        if jauh > 30:
            temuan.tambah(V.PERINGATAN, "Koordinat", T("FDT %s tercatat di beberapa tempat yang berjarak %.0f m",
                                                       "FDT %s is recorded in several places up to %.0f m apart") % (
                kode, jauh), base, T("samakan koordinat FDT", "use one location for the FDT"))


def baca_target(path, temuan=None):
    """Titik FDT target dari KMZ Distribusi / Design Lite / cluster. Satu kode FDT = satu target (duplikat digabung)."""
    temuan = temuan if temuan is not None else V.Temuan()
    out = {}
    base = os.path.basename(path)
    semua = [pm for pm in baca.placemarks(path) if pm["geoms"][0][0] == "Point"]
    # Titik yang NAMANYA persis kode FDT adalah lokasi FDT yang sah. Bila berkas memilikinya, titik lain yang hanya
    # 'mirip' (lewat folder/atribut) tidak boleh menggantikan atau menggeser lokasinya.
    ada_persis = any(_seperti_fdt(pm["name"].strip()) for pm in semua)
    turunan = 0
    for pm in semua:
        g0, cs = pm["geoms"][0]
        nm = pm["name"].strip()
        if _turunan_fdt(nm):
            turunan += 1
            continue
        if ada_persis and not _seperti_fdt(nm):
            continue
        p = [V.kanon_folder(f, None) for f in pm["path"]]
        di_fdt = any("FDT" in f.upper() for f in p[-2:])
        if not (_seperti_fdt(nm) or di_fdt or _tanda_fdt(pm)) or _tanda_pop_luas(pm):
            continue
        kode_atr = atribut.nilai(pm["attrs"], "kode_fdt")
        if (not nm or not (_seperti_fdt(nm) or atribut.RX_KATA_FDT.search(nm.upper()))) and kode_atr:
            pm = dict(pm, name=str(kode_atr).strip())      # nama titik kosong/umum: pakai kolom kode FDT/ODC
            nm = pm["name"]
        if not nm or nm.upper().startswith(("CLOSURE", "SLACK", "OTB", "POLE", "TIANG", "FAT", "ODP")):
            continue
        q = V.koreksi_titik(cs[0], temuan, base, " FDT %s" % nm)
        if q is None:
            continue
        rec = _fdt_rec(pm, q, temuan, base)
        clus = area = tgl = None
        for f in [base] + pm["path"]:
            m = RX_CLUSTER.search(f)
            if m:
                clus, area = m.group(1), m.group(2).strip()
                mt = RX_TGL.search(f)
                tgl = mt.group(1) if mt else None
        if not clus:                       # nama berkas '<ID cluster>_<nama area>.kmz' (tanpa kata APD)
            m = re.match(r"^(\d{9,12})_(.+?)(?:_\d{2}-\d{2}-\d{4})?\.[A-Za-z]{3,7}$", base)
            if m:
                clus, area = m.group(1), m.group(2).strip()
        rec.update({"_lat": atribut.nilai(pm["attrs"], "lat"), "_lon": atribut.nilai(pm["attrs"], "lon"),
                    "cluster": clus, "area": area, "tanggal": tgl, "berkas": base,
                    "status": "Eksisting" if "Eksisting FDT" in p else "New", "attrs": dict(pm["attrs"])})
        lama = out.get(rec["kode"].upper())
        if lama is None:
            out[rec["kode"].upper()] = rec
        else:
            from . import geo
            d = geo.haversine(lama["ll"], rec["ll"])
            if d > 30:
                temuan.tambah(V.PERINGATAN, "Koordinat", T("FDT %s muncul dua kali, berjarak %.0f m; yang pertama dipakai",
                                                           "FDT %s appears twice, %.0f m apart; the first one is used")
                              % (rec["kode"], d), base, T("hapus yang dobel atau perbaiki kodenya",
                                                          "remove the duplicate or fix its code"))
            if rec.get("splitter") and not lama.get("splitter"):
                lama["splitter"], lama["rasio"] = rec["splitter"], rec["rasio"]
    for rec in out.values():
        # lokasi FDT = titik di berkas, apa adanya. Kolom LAT/LONG yang berbeda hanya dilaporkan, tidak dipakai.
        la, lo = atribut.angka(rec.pop("_lat", None)), atribut.angka(rec.pop("_lon", None))
        if la is not None and lo is not None and abs(la) <= 90 and abs(lo) <= 180:
            from . import geo
            d = geo.haversine(rec["ll"], (lo, la))
            if d > 30:
                temuan.tambah(V.PERINGATAN, "Koordinat",
                              T("FDT %s: kolom LAT/LONG di datanya menunjuk tempat lain (%.0f m dari titiknya). Tembuku "
                                "memakai titik di peta dan tidak memindahkannya",
                                "FDT %s: its LAT/LONG fields point somewhere else (%.0f m from the point). Tembuku uses "
                                "the point on the map and does not move it") % (rec["kode"], d), base,
                              T("pastikan titik FDT sudah di tempat yang benar", "make sure the FDT point is in the "
                                                                              "right place"))
    if turunan and out:
        temuan.tambah(V.INFO, "Isi data", T("%d titik bernama kode FDT + lanjutan (mis. -D01-01) adalah bagian distribusi, "
                                            "bukan FDT, jadi tidak dipakai sebagai lokasi FDT",
                                            "%d points named FDT code + suffix (e.g. -D01-01) belong to distribution, "
                                            "not the FDT, so they are not used as the FDT location") % turunan, base)
    if not out:
        temuan.tambah(V.PERINGATAN, "Kelengkapan", T("tidak ada titik FDT di berkas ini", "no FDT point in this file"),
                      base)
    return list(out.values())


def baca_pop(path, temuan=None, hanya_bertanda=False):
    """Titik POP/OLT/STO. Di berkas daftar POP: bila sebagian titik bertanda POP (nama/folder/atribut), hanya titik itu
    yang dipakai; bila tidak ada tanda sama sekali, semua titik dianggap POP. hanya_bertanda=True untuk berkas lain
    (mis. berkas titik FDT yang juga memuat lokasi POP)."""
    temuan = temuan if temuan is not None else V.Temuan()
    semua, bertanda = [], []
    base = os.path.basename(path)
    for pm in baca.placemarks(path):
        g0, cs = pm["geoms"][0]
        if g0 != "Point":
            continue
        tanda = _tanda_pop_luas(pm)
        if hanya_bertanda and not tanda:
            continue
        q = V.koreksi_titik(cs[0], temuan, base, " POP %s" % pm["name"])
        if q is None:
            continue
        nama = pm["name"].strip() or str(atribut.nilai(pm["attrs"], "pop") or "POP")
        rec = {"nama": nama, "ll": q, "attrs": pm["attrs"]}
        semua.append(rec)
        if tanda:
            bertanda.append(rec)
    return bertanda or ([] if hanya_bertanda else semua)


def baca_audit(path):
    """Tabel catatan tube per feeder (Excel/CSV dengan kolom 'Feeder' dan 'Tube Terpakai', opsional 'POP').
    -> [(nama POP, nomor feeder, {nomor T terpakai})] atau None bila bukan tabel semacam itu."""
    j = baca.jenis(path)
    try:
        baris = baca._baris_xlsx(path) if j == "XLSX" else (baca._baris_csv(path) if j in ("CSV", "TABEL") else None)
    except Exception:           # tabel rusak/terkunci: bukan catatan tube
        return None
    baris = list(baris) if baris is not None else []
    if not baris:
        return None
    kop = [atribut.norm(x) for x in baris[0]]
    i_f = next((i for i, k in enumerate(kop) if k in ("FEEDER", "NOFEEDER", "NOMORFEEDER")), None)
    i_t = next((i for i, k in enumerate(kop) if k in ("TUBETERPAKAI", "TUBEUSED", "USEDTUBE", "USEDTUBES", "TUBEDIPAKAI")), None)
    i_p = next((i for i, k in enumerate(kop) if k in ("POP", "NAMAPOP", "POPNAME", "OLT")), None)
    if i_f is None or i_t is None:
        return None
    out = []
    for r in baris[1:]:
        if len(r) <= max(i_f, i_t):
            continue
        m = re.search(r"\d+", str(r[i_f]))
        if not m:
            continue
        out.append((str(r[i_p]).strip() if i_p is not None and len(r) > i_p else "", int(m.group(0)),
                    V.nomor_tube(str(r[i_t]))))
    return out or None


def _relevan(p):
    """Berkas yang mungkin berisi data peta Tembuku (dikenali dari isi). Tabel tanpa kolom koordinat = tidak relevan."""
    j = baca.jenis(p)
    if j == "XLSX":
        try:
            baris = baca._baris_xlsx(p)
            return bool(baris) and baca._kolom_koordinat([str(x) for x in baris[0]]) is not None
        except Exception:       # Excel rusak/terkunci: bukan data peta
            return False
    return j is not None


def kumpulkan(paths, temuan=None, bukti=None, folder_kerja=None):
    """Kelompokkan berkas menurut peran yang dikenali dari isinya. -> {peran: [path]}.
    bukti (dict, opsional) diisi alasan pengenalan per berkas; ZIP berisi banyak berkas dibuka satu per satu."""
    temuan = temuan if temuan is not None else V.Temuan()
    bukti = bukti if bukti is not None else {}
    peran = {"NASIONAL": [], "COMPILE": [], "TARGET": [], "POP": [], "AUDIT": [], "LAIN": []}
    daftar = []
    for p in paths:
        if os.path.isfile(p) and baca.jenis(p) == "ZIP":
            try:
                isi = baca.buka_zip(p, folder_kerja)
            except (kml_aman.BerkasDitolak, OSError, ValueError) as e:
                temuan.tambah(V.FATAL, "Berkas", T("ZIP tidak bisa dibuka: %s", "the ZIP cannot be opened: %s") % e,
                              os.path.basename(p), T("periksa apakah ZIP rusak", "check whether the ZIP is damaged"))
                continue
            temuan.tambah(V.INFO, "Kelengkapan", T("ZIP dibuka: %d berkas data di dalamnya ikut diperiksa",
                                                   "ZIP opened: %d data files inside are checked") % len(isi),
                          os.path.basename(p))
            daftar += isi
        else:
            daftar.append(p)
    for p in V.pra_cek_berkas(daftar, temuan):
        audit = baca_audit(p) if baca.jenis(p) in ("XLSX", "CSV", "TABEL") else None
        if audit:
            peran["AUDIT"].append(p)
            bukti[p] = T("tabel dengan kolom Feeder dan Tube Terpakai (%d feeder)",
                         "table with Feeder and Used Tube columns (%d feeders)") % len(audit)
            continue
        if not _relevan(p):
            temuan.tambah(V.PERINGATAN, "Kelengkapan", T("bukan data peta yang dikenali (KMZ, KML, GeoJSON, CSV/Excel "
                                                         "berkoordinat, Shapefile, GeoPackage), dilewati",
                                                         "not a recognised map data file (KMZ, KML, GeoJSON, CSV/Excel "
                                                         "with coordinates, Shapefile, GeoPackage), skipped"),
                          os.path.basename(p))
            continue
        if keluaran_tembuku(p):
            peran["LAIN"].append(p)
            V.TANPA_PERINGATAN.add(p)
            bukti[p] = T("KMZ hasil Tembuku sebelumnya; tidak dibaca sebagai data masukan",
                         "a previous Tembuku result KMZ; not read as input data")
            temuan.tambah(V.INFO, "Kelengkapan", T("KMZ hasil Tembuku sebelumnya, dilewati agar tidak terhitung sebagai "
                                                   "feeder atau FDT", "a previous Tembuku result KMZ, skipped so it is "
                                                   "not counted as a feeder or FDT"), os.path.basename(p))
            continue
        try:
            r, sk, alasan = intip(p)
        except kml_aman.BerkasDitolak as e:
            temuan.tambah(V.FATAL, "Berkas", T("berkas ditolak: %s", "file refused: %s") % e,
                          os.path.basename(p), T("ekspor ulang berkas dari aplikasi pembuatnya",
                                                 "export the file again from the program that made it"))
            continue
        except Exception as e:      # berkas rusak: berhenti dengan pesan jelas, bukan crash
            temuan.tambah(V.FATAL, "Berkas", T("berkas tidak bisa dibaca (%s)", "the file cannot be read (%s)") %
                          str(e)[:120], os.path.basename(p),
                          T("periksa apakah berkas rusak atau terpotong saat diunduh",
                            "check whether the file is damaged or was cut short while downloading"))
            continue
        if r == "KOSONG":
            temuan.tambah(V.FATAL, "Kelengkapan", T("berkas tidak berisi objek (titik/garis) apa pun",
                                                    "the file contains no objects (points or lines)"),
                          os.path.basename(p), T("periksa apakah berkasnya salah", "check whether it is the wrong file"))
            continue
        peran[r].append(p)
        bukti[p] = alasan
        urut = sorted(sk.values(), reverse=True)
        if r != "LAIN" and len(urut) > 1 and urut[1] > 2 and urut[0] < 2 * urut[1]:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", T("isi berkas mirip beberapa jenis (%s); dibaca sebagai %s",
                                                         "the file looks like several types (%s); read as %s") % (
                gabung(", ", [NAMA_PERAN.get(kv[0], kv[0]) for kv in sk.items() if kv[1] > 2]), NAMA_PERAN.get(r, r)),
                os.path.basename(p), T("jika salah, pilih jenis yang benar di kolom 'Read as'",
                                       "if this is wrong, choose the right type in the 'Read as' column"))
    V.versi_ganda(peran, traksi_berkas, temuan)
    return peran


def cari_berkas(folder, rekursif=True):
    """Berkas data di folder, dikenali dari ISI: ekstensi yang dikenal diperiksa isinya, berkas tanpa ekstensi atau
    berekstensi lain ikut bila isinya KMZ/KML/GeoJSON. Dokumen biasa (PPTX, DOCX, PDF, gambar) dilewati."""
    out = []
    lewati = (".pptx", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".exe", ".dll", ".dbf", ".shx",
              ".prj", ".cpg", ".qix", ".sbn", ".sbx", ".qmd", ".xml", ".html", ".htm", ".py", ".qgs", ".qgz")
    ogr, _o = baca._ogr()
    for d, dirs, files in os.walk(folder):
        dirs[:] = [x for x in dirs if not x.upper().startswith((".", "_TEMBUKU", "TEMBUKU_HASIL", "TEMBUKU_"))]
        for f in sorted(files):
            if f.upper().startswith("TEMBUKU_") or f.upper().endswith("_ANALISIS.KMZ"):
                continue
            p = os.path.join(d, f)
            low = f.lower()
            if low.endswith(baca.EKST_OGR) and ogr is None:
                continue
            if low.endswith(baca.EKST_DATA) or (not low.endswith(lewati) and baca.jenis(p) in ("KMZ", "KML", "GEOJSON")):
                if _relevan(p) or (baca.jenis(p) in ("XLSX", "CSV") and baca_audit(p)):
                    out.append(p)
        if not rekursif:
            break
    return out
