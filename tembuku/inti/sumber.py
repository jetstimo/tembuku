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

from . import kml_aman, kabel
from . import validasi as V

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
RX_FDT = re.compile(r"^[A-Z]{2,4}\d?-[A-Z]{2,4}\d{1,3}-H\d{1,3}$")
RX_FDT_LONGGAR = re.compile(r"^[A-Za-z]{2,4}\d[\s_\-.]*[A-Za-z]{2,4}\d{1,2}[\s_\-.]*[Hh]\d{1,2}$")
RX_CLUSTER = re.compile(r"(\d{9,12})_APD\s+(?:Distribusi|Feeder|Distribution)\s+KMZ_(.+?)(?:_\d{2}-\d{2}-\d{4}.*)?"
                        r"(?:\.kmz)?$", re.I)
RX_TGL = re.compile(r"_(\d{2}-\d{2}-\d{4})")


def _seperti_fdt(nama):
    return bool(RX_FDT.match(nama or "") or RX_FDT_LONGGAR.match((nama or "").strip()))


def intip(path, n=400):
    """Kenali peran berkas dari n placemark pertama (cepat, tidak membaca seluruh berkas)."""
    skor = {"NASIONAL": 0, "COMPILE": 0, "TARGET": 0, "POP": 0}
    nama = os.path.basename(path).upper()
    k = 0
    for pm in kml_aman.placemarks(path):
        k += 1
        a = pm["attrs"]
        if "NUM_SPARE_" in a or ("MODEL" in a and "Owner" in a):
            skor["NASIONAL"] += 1
        if any(V.baca_traksi(f) for f in pm["path"]):
            skor["COMPILE"] += 1
        if pm["geoms"][0][0] == "Point":
            if _seperti_fdt(pm["name"]) or any("FDT" in f.upper() for f in pm["path"][-2:]):
                skor["TARGET"] += 1
            if _tanda_pop(a) or RX_POPF.search(pm["name"]) or any(
                    f.upper() in ("POP", "OLT", "ALL POP") for f in pm["path"][-2:]):
                skor["POP"] += 1
        if k >= n:
            break
    if k == 0:
        return "KOSONG", skor
    if "NASIONAL" in nama or any(p in nama for p in PETUNJUK_NASIONAL):
        skor["NASIONAL"] += 50
    if "COMPILE" in nama or re.search(r"FEEDER\s*ALL", nama):
        skor["COMPILE"] += 50
    if "POP" in nama and "FEEDER" not in nama:
        skor["POP"] += 20
    if "DISTRIBUSI" in nama or "DESIGN LITE" in nama or "DESIGN_LITE" in nama:
        skor["TARGET"] += 20
    if skor["COMPILE"] > 0:
        skor["TARGET"] = 0           # FDT di compile = FDT yang sudah didesain feeder-nya
    peran = max(skor, key=lambda x: skor[x])
    return (peran if skor[peran] > 0 else "LAIN"), skor


def _fdt_rec(pm, ll, temuan, base):
    kt = " FDT %s" % pm["name"]
    spl, rat = V.koreksi_splitter(V.atribut(pm["attrs"], "SPLITTERS", temuan, base, kt) or "", temuan, base, kt)
    return {"kode": V.koreksi_fdt(pm["name"], temuan, base), "ll": ll, "splitter": spl, "rasio": rat,
            "premises": V.angka_longgar(V.atribut(pm["attrs"], "PREMISES", temuan, base, kt), temuan, base,
                                        " PREMISES %s" % pm["name"])}


def traksi_berkas(path):
    """Kode traksi (F<n>_T<k>_<ID>) di satu KMZ compile - untuk mengenali versi ganda."""
    out = set()
    for pm in kml_aman.placemarks(path):
        for f in pm["path"]:
            t = V.baca_traksi(f)
            if t:
                out.add("F%s_T%s_%s" % (t["feeder"], t["t"], t["cluster"] or ""))
    return out


def baca_compile(path, temuan=None):
    """-> dict(pops, traksi{kunci: {...}}, kabel[...], fdt[...]) dari satu KMZ Compile APD Feeder."""
    temuan = temuan if temuan is not None else V.Temuan()
    base = os.path.basename(path)
    pops, traksi, kab, fdts = {}, {}, [], []
    n_pm = 0
    for pm in kml_aman.placemarks(path):
        n_pm += 1
        p = [V.kanon_folder(f, temuan, base) for f in pm["path"]]
        info = [(j, V.baca_traksi(f, temuan, base)) for j, f in enumerate(p)]
        info = [(j, t) for j, t in info if t]
        popf = next((f for f in p if RX_POPF.search(f) and not V.baca_traksi(f) and not V.baca_feeder(f)), "")
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
                temuan.tambah(INFO_, "Kelengkapan", "garis '%s' kurang dari 2 titik sah, dilewati" % pm["name"], base)
                continue
        if g0 == "Point" and (leaf.upper() in ("OLT", "POP") or _tanda_pop(pm["attrs"])):
            pops.setdefault(pm["name"].strip().upper(), {"nama": pm["name"].strip(), "ll": cs[0], "attrs": pm["attrs"]})
            continue
        if not info:
            continue
        j0, t0 = info[0]
        j, _t = info[-1]                 # traksi TERDALAM: sub-folder F.._T.. = FDT colo saudara
        induk = pm["path"][j0]
        if fdr is None:
            fdr = str(t0["feeder"])
        key = (base, popf, fdr, induk)
        t = traksi.setdefault(key, {"kode": induk, "info": t0, "pop_folder": popf, "feeder": fdr, "berkas": base,
                                    "fdt": [], "kabel": [], "colo": [], "closure": [], "lain": []})
        sub = j != j0
        if g0 == "Point" and (any("FDT" in f.upper() for f in p[j + 1:]) or _seperti_fdt(pm["name"])):
            rec = _fdt_rec(pm, cs[0], temuan, base)
            rec.update({"traksi": induk, "feeder": fdr, "pop_folder": popf, "colo_saudara": sub,
                        "status": "Eksisting" if "Eksisting FDT" in p else "New"})
            t["fdt"].append(rec)
            fdts.append(rec)
        elif g0 == "LineString":
            up = leaf.upper()
            jenis = ("COLO_CABLE" if up in ("COLLO CABLE", "COLO CABLE") else
                     "NEW_CABLE" if up.startswith("NEW CABLE") and not up.endswith(" UG") and "GALIAN" not in up
                     and "AERIAL" not in up else "UG" if up.endswith(" UG") else "INFRA")
            core = None
            if jenis == "NEW_CABLE":
                core = V.koreksi_core(leaf, temuan, base, " (folder %s)" % leaf)
                if core is None:
                    core = V.koreksi_core(pm["name"], None)
            else:
                core = kabel.core_compile(leaf, pm["name"])
            rec = {"id": "C%d" % (len(kab) + 1), "ll": cs, "core": core, "jenis": jenis, "nama": pm["name"],
                   "traksi": induk, "feeder": fdr, "pop_folder": popf, "berkas": base, "sumber": "COMPILE",
                   "warna": pm["warna"], "folder": leaf}
            kab.append(rec)
            (t["colo"] if jenis == "COLO_CABLE" else t["kabel"]).append(rec)
        elif g0 == "Point" and ("CLOSURE" in leaf.upper() or "Eksisting Closure" in p):
            t["closure"].append({"nama": pm["name"], "ll": cs[0], "eksisting": "Eksisting Closure" in p})
        else:
            t["lain"].append({"nama": pm["name"], "ll": cs[0], "folder": leaf})
    if n_pm == 0:
        temuan.tambah(V.FATAL, "Kelengkapan", "KMZ compile tidak berisi objek", base, "ekspor ulang dari aplikasi pembuat KMZ")
    _cek_konsistensi(traksi, temuan, base)
    return {"pops": list(pops.values()), "traksi": traksi, "kabel": kab, "fdt": fdts, "berkas": base}


INFO_ = V.INFO


def _cek_konsistensi(traksi, temuan, base):
    """Konsistensi logis antar-objek compile (ISO 19157: logical consistency)."""
    lokasi = {}
    for key, t in traksi.items():
        own = [f for f in t["fdt"] if not f["colo_saudara"]]
        if not own:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", "traksi %s tidak punya titik FDT" % t["kode"][:40], base,
                          "tambahkan FDT di folder FDT/New FDT")
        if not t["kabel"] and not t["colo"]:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", "traksi %s tidak punya kabel" % t["kode"][:40], base)
        for k in t["kabel"]:
            if k["jenis"] == "NEW_CABLE" and not k["core"]:
                temuan.tambah(V.PERINGATAN, "Konsistensi domain", "kabel '%s' di %s tanpa ukuran core" % (
                    k["nama"], t["kode"][:30]), base, "kapasitas kabel ini dianggap belum terverifikasi")
        # FDT milik traksi berbeda dengan FDT yang disebut di sub-folder (contoh data riil: F1_T9 POP 2 Bitung)
        sub = set(f["kode"] for f in t["fdt"] if f["colo_saudara"])
        if own and sub and not (set(f["kode"] for f in own) & sub):
            temuan.tambah(V.PERINGATAN, "Konsistensi logis", "traksi %s: FDT di folder FDT (%s) berbeda dari FDT di "
                          "sub-folder (%s)" % (t["kode"][:40], ", ".join(sorted(set(f["kode"] for f in own))),
                                               ", ".join(sorted(sub))), base, "periksa FDT mana yang benar")
        for f in t["fdt"]:
            lokasi.setdefault(f["kode"], []).append(f["ll"])
    from . import geo
    for kode, lls in lokasi.items():
        jauh = max((geo.haversine(lls[0], q) for q in lls[1:]), default=0)
        if jauh > 30:
            temuan.tambah(V.PERINGATAN, "Akurasi posisi absolut", "FDT %s tercatat di beberapa lokasi berjarak %.0f m" % (
                kode, jauh), base, "samakan koordinat FDT")


def baca_target(path, temuan=None):
    """Titik FDT target dari KMZ Distribusi / Design Lite / cluster. Satu kode FDT = satu target (duplikat digabung)."""
    temuan = temuan if temuan is not None else V.Temuan()
    out = {}
    base = os.path.basename(path)
    for pm in kml_aman.placemarks(path):
        g0, cs = pm["geoms"][0]
        if g0 != "Point":
            continue
        nm = pm["name"].strip()
        p = [V.kanon_folder(f, None) for f in pm["path"]]
        di_fdt = any("FDT" in f.upper() for f in p[-2:])
        if not (_seperti_fdt(nm) or di_fdt):
            continue
        if not nm or nm.upper().startswith(("CLOSURE", "SLACK", "OTB", "POLE", "TIANG", "FAT")):
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
        rec.update({"cluster": clus, "area": area, "tanggal": tgl, "berkas": base,
                    "status": "Eksisting" if "Eksisting FDT" in p else "New"})
        lama = out.get(rec["kode"].upper())
        if lama is None:
            out[rec["kode"].upper()] = rec
        else:
            from . import geo
            d = geo.haversine(lama["ll"], rec["ll"])
            if d > 30:
                temuan.tambah(V.PERINGATAN, "Akurasi posisi absolut", "FDT %s muncul dua kali berjarak %.0f m; yang pertama "
                              "dipakai" % (rec["kode"], d), base, "hapus duplikat atau perbaiki kode")
            if rec.get("splitter") and not lama.get("splitter"):
                lama["splitter"], lama["rasio"] = rec["splitter"], rec["rasio"]
    if not out:
        temuan.tambah(V.PERINGATAN, "Kelengkapan", "tidak ada titik FDT di berkas ini", base)
    return list(out.values())


def baca_pop(path, temuan=None):
    temuan = temuan if temuan is not None else V.Temuan()
    out = []
    base = os.path.basename(path)
    for pm in kml_aman.placemarks(path):
        g0, cs = pm["geoms"][0]
        if g0 == "Point":
            q = V.koreksi_titik(cs[0], temuan, base, " POP %s" % pm["name"])
            if q is not None:
                out.append({"nama": pm["name"].strip() or "POP", "ll": q, "attrs": pm["attrs"]})
    return out


def kumpulkan(paths, temuan=None):
    """Kelompokkan berkas menurut peran. -> {peran: [path]}"""
    temuan = temuan if temuan is not None else V.Temuan()
    peran = {"NASIONAL": [], "COMPILE": [], "TARGET": [], "POP": [], "LAIN": []}
    for p in V.pra_cek_berkas(paths, temuan):
        try:
            r, sk = intip(p)
        except kml_aman.BerkasDitolak as e:
            temuan.tambah(V.FATAL, "Konsistensi format", "berkas ditolak demi keamanan: %s" % e, os.path.basename(p),
                          "ekspor ulang KMZ dari aplikasi pembuat / inventaris kabel nasional")
            continue
        except Exception as e:      # berkas rusak: berhenti dengan pesan jelas, bukan crash
            temuan.tambah(V.FATAL, "Konsistensi format", "berkas tidak dapat dibaca (%s)" % str(e)[:120],
                          os.path.basename(p), "periksa apakah berkas rusak/terpotong saat diunduh")
            continue
        if r == "KOSONG":
            temuan.tambah(V.FATAL, "Kelengkapan", "berkas tidak berisi objek (placemark)", os.path.basename(p),
                          "periksa apakah salah berkas")
            continue
        peran[r].append(p)
        urut = sorted(sk.values(), reverse=True)
        if r != "LAIN" and len(urut) > 1 and urut[1] > 0 and urut[0] < 2 * urut[1] and urut[0] < 50:
            temuan.tambah(V.PERINGATAN, "Kelengkapan", "peran berkas tidak tegas (%s), dibaca sebagai %s" % (
                ", ".join("%s %d" % kv for kv in sk.items() if kv[1]), r), os.path.basename(p))
    V.versi_ganda(peran, traksi_berkas, temuan)
    return peran


def cari_berkas(folder, rekursif=True):
    out = []
    for d, dirs, files in os.walk(folder):
        dirs[:] = [x for x in dirs if not x.startswith((".", "_TEMBUKU", "TEMBUKU_HASIL"))]
        for f in sorted(files):
            if f.lower().endswith((".kmz", ".kml")) and not f.upper().startswith("TEMBUKU_"):
                out.append(os.path.join(d, f))
        if not rekursif:
            break
    return out
