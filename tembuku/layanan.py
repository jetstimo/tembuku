# -*- coding: utf-8 -*-
# Tembuku - layanan: pra-cek, muat data, analisis banyak FDT, simpan hasil.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Tidak bergantung pada widget QGIS: dipakai dialog, alat klik-peta, algoritma Processing dan uji otomatis.
Akses internet (hanya jalan OSM) disuntikkan sebagai fungsi 'ambil(url, data) -> bytes' agar memakai proxy QGIS."""
import csv
import datetime
import json
import math
import os
import re
import time

from . import _log
from .inti import geo, indeks, laporan, mesin, osm, profil, sumber, tulis_kmz
from .inti import validasi as V
from .inti.teks import T

UBIN = 0.05              # derajat (~5,5 km): satu permintaan Overpass per ubin, disimpan 90 hari
UMUR_CACHE_HARI = 90
OVERPASS = "https://overpass-api.de/api/interpreter"   # server publik FOSSGIS; organisasi dapat memakai server sendiri
COBA_UBIN = 3                 # percobaan per permintaan (server publik sering 429/502/504 saat sibuk)
JEDA_COBA = (30, 60)          # detik sebelum percobaan ke-2/ke-3 setelah HTTP 429/406: kebijakan server publik meminta
                              # jeda >= 30 detik (Overpass API usage policy, 2026)
JEDA_SIBUK = (5, 15)          # 502/503/504/timeout: server sibuk sesaat


def jenis_galat(e):
    """'BATAS' (429/406, server meminta jeda), 'SIBUK' (5xx/timeout) atau 'LURING' (tidak ada koneksi: jangan menunggu)."""
    t = str(e).lower()
    if any(k in t for k in ("429", "406", "too many", "not acceptable", "rate limit")):
        return "BATAS"
    if any(k in t for k in ("502", "503", "504", "bad gateway", "unavailable", "gateway time", "timed out",
                            "timeout", "busy")):
        return "SIBUK"
    return "LURING"


def folder_ikon_data(paths, naik=2):
    """Cari folder ikon milik tim di sekitar berkas data (mis. "ICON APD FTTH" di samping folder COMPILE FEEDER):
    folder berkas dan hingga `naik` tingkat di atasnya, hanya subfolder langsung yang namanya memuat "icon"/"ikon"."""
    out, lihat = [], set()
    for p in paths or []:
        d = os.path.dirname(os.path.abspath(p)) if os.path.isfile(p) else os.path.abspath(p)
        for _ in range(naik + 1):
            if d in lihat:
                break
            lihat.add(d)
            try:
                for f in sorted(os.listdir(d)):
                    q = os.path.join(d, f)
                    if re.search(r"icon|ikon", f, re.I) and os.path.isdir(q) and q not in out:
                        out.append(q)
            except OSError:
                pass
            atas = os.path.dirname(d)
            if atas == d:
                break
            d = atas
    return out


def baca_ikon(folder_cache, maks=512 * 1024, paths=None):
    """Ikon organisasi (opsional): berkas PNG di <folder Tembuku>/ikon, Documents/Tembuku/ikon, atau folder ikon tim di
    sekitar berkas data (mis. "ICON APD FTTH"). Hanya PNG asli (dicek dari tanda berkas) dan berukuran wajar; tidak ikut
    di plugin, tetap di komputer pengguna. Bila nama berkas sama, yang lebih dulu ditemukan dipakai."""
    out = {}
    for d in [os.path.join(folder_cache or "", "ikon"), os.path.join(os.path.expanduser("~"), "Documents", "Tembuku", "ikon")] \
            + folder_ikon_data(paths):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if f.lower().endswith(".png") and f not in out and os.path.isfile(p) and os.path.getsize(p) <= maks:
                with open(p, "rb") as fh:
                    isi = fh.read()
                if isi[:8] == b"\x89PNG\r\n\x1a\n":
                    out[f] = isi
    return out


def lokasi_istilah(folder_cache):
    """Profil istilah organisasi (opsional, di luar plugin): label & petunjuk khusus perusahaan tidak dikirim bersama
    kode. Urutan: folder profil QGIS -> Dokumen pengguna. Berkas pertama yang ada dipakai."""
    return [os.path.join(folder_cache or "", "istilah.json"),
            os.path.join(os.path.expanduser("~"), "Documents", "Tembuku", "istilah.json")]


class Dibatalkan(Exception):
    pass


class Sesi(object):
    def __init__(self, paths, folder_cache, prm=None, pakai_osm=True, ambil=None, progres=None, batal=None,
                 jalan_lokal=None, istilah=None):
        self.paths = list(paths)
        self.cache = folder_cache
        self.prm = profil.baru(prm or {})
        self.pakai_osm = pakai_osm and ambil is not None
        self.ambil = ambil
        self._prog = progres
        self._batal = batal
        self.jalan_lokal = jalan_lokal          # daftar {kelas, ll} dari layer jalan pengguna (opsional)
        self.temuan = V.Temuan()
        self.peran = {}
        self.data = None
        self.target = []
        self.hasil = []
        self._jalan_gagal = False
        self.uji = False
        self.folder_hasil = None        # folder hasil: desain Tembuku sebelumnya di sini ikut dihitung (tube terpakai)
        self.nilai_uji = []
        self._ubin = {}
        self._ubin_gagal = []
        self.overpass = OVERPASS
        self.peta_laporan = None        # {nama, url, atrib}: peta resolusi tinggi milik pengguna, hanya bila diizinkan
        self.istilah = profil.istilah(lokasi_istilah(folder_cache) if istilah is None else istilah)
        if self.istilah.get("_galat"):
            self.temuan.tambah(V.PERINGATAN, "Pengaturan", T("berkas label perusahaan tidak bisa dibaca (%s); label bawaan "
                                                             "dipakai", "the company label file cannot be read (%s); the "
                                                             "built-in labels are used") % self.istilah["_galat"][:160],
                               "istilah.json", T("periksa penulisan JSON di istilah.json",
                                                 "check the JSON in istilah.json"))
        self.ikon_lokal = baca_ikon(folder_cache, paths=self.paths)
        mesin.pakai_istilah(self.istilah)
        sumber.pakai_istilah(self.istilah)

    # ------------------------------------------------------------------ util
    def progres(self, teks, persen=None):
        if self._prog:
            self._prog(teks, persen)
        if self._batal and self._batal():
            raise Dibatalkan()

    # ------------------------------------------------------------------ 1. pra-cek (cepat, tanpa indeks)
    def pra_cek(self, target_manual=False):
        self.bukti = {}
        self.peran = sumber.kumpulkan(self.paths, self.temuan, self.bukti, os.path.join(self.cache, "zip"))
        V.cek_peran(self.peran, self.temuan, target_manual)
        return self.temuan

    # ------------------------------------------------------------------ 2. muat
    def muat(self):
        comps = []
        for p in self.peran.get("COMPILE", []):
            self.progres("Reading compile %s" % os.path.basename(p), 3)
            comps.append(sumber.baca_compile(p, self.temuan))
        pops = []
        for p in self.peran.get("POP", []):
            pops.extend(sumber.baca_pop(p, self.temuan))
        for p in self.peran.get("TARGET", []):          # berkas titik FDT yang juga memuat lokasi POP/OLT/STO
            tambahan = sumber.baca_pop(p, self.temuan, hanya_bertanda=True)
            if tambahan:
                pops.extend(tambahan)
                self.temuan.tambah(V.INFO, "Kelengkapan", T("%d titik POP/OLT/STO di berkas ini ikut dipakai sebagai POP",
                                                            "%d POP/OLT/STO points in this file are also used as POPs")
                                   % len(tambahan), os.path.basename(p))
        self.jalur_distribusi, self.tiang_distribusi = [], []
        for p in self.peran.get("TARGET", []):
            try:
                g, t = sumber.baca_jalur_distribusi(p)
                self.jalur_distribusi += g
                self.tiang_distribusi += t
            except Exception as e:      # pelengkap label infra: desain tetap jalan
                _log.note(e, "jalur distribusi")
        self.target = []
        sudah = set()
        for p in self.peran.get("TARGET", []):
            for f in sumber.baca_target(p, self.temuan):
                if f["kode"].upper() in sudah:
                    self.temuan.tambah(V.INFO, "Kelengkapan", T("FDT %s ada di lebih dari satu berkas; dipakai sekali",
                                                                "FDT %s is in more than one file; it is used once")
                                       % f["kode"], os.path.basename(p))
                    continue
                sudah.add(f["kode"].upper())
                self.target.append(f)
        sudah_compile = {f["kode"].upper() for c in comps for f in c["fdt"]}
        for f in self.target:
            if f["kode"].upper() in sudah_compile:
                f["sudah_di_compile"] = True
                from .inti import geo as _geo
                jauh = min(_geo.haversine(f["ll"], g["ll"]) for c in comps for g in c["fdt"]
                           if g["kode"].upper() == f["kode"].upper())
                if jauh > 30:
                    self.temuan.tambah(V.PERINGATAN, "Koordinat",
                                       T("FDT %s di berkas Anda berjarak %.0f m dari FDT berkode sama di compile. Tembuku "
                                         "memakai titik di berkas Anda apa adanya (tidak dipindah)",
                                         "FDT %s in your file is %.0f m from the FDT with the same code in the "
                                         "compilation. Tembuku uses the point in your file as it is (not moved)")
                                       % (f["kode"], jauh), f.get("berkas", ""),
                                       T("pastikan titik mana yang benar", "check which point is right"))
                # desain lama FDT ini disembunyikan saat FDT ini dianalisis: tanpa itu Tembuku menumpang kabel
                # desainnya sendiri (kabel baru 0 m) dan tube lamanya terhitung terpakai
                milik = sorted({g["traksi"] for c in comps for g in c["fdt"]
                                if g["kode"].upper() == f["kode"].upper() and not g.get("colo_saudara")
                                and g.get("traksi")})
                f["_kecuali"] = set(milik)
                self.temuan.tambah(V.INFO, "Kesesuaian data", T("FDT %s sudah ada di compile desain feeder (folder %s). "
                                                                "Desain lama itu disembunyikan selama FDT ini dirancang "
                                                                "ulang, jadi hasilnya pembanding yang setara",
                                                                "FDT %s is already in the feeder design compilation "
                                                                "(folder %s). That earlier design is hidden while this FDT "
                                                                "is designed again, so the result is a fair comparison")
                                   % (f["kode"], ", ".join(x[:40] for x in milik) or "-"))
        # area kerja = sekitar FDT target, compile dan POP: hanya area ini yang diindeks dari KMZ kabel nasional
        titik = [f["ll"] for f in self.target]
        for c in comps:
            titik += [f["ll"] for f in c["fdt"]] + [p["ll"] for p in c["pops"]]
            titik += [k["ll"][0] for k in c["kabel"]] + [k["ll"][-1] for k in c["kabel"]]
        # daftar POP bisa mencakup seluruh negeri: hanya POP dalam ~60 km dari FDT/compile yang ikut menentukan area
        # kerja, supaya inventaris daerah lain tidak ikut diindeks (bila tidak ada FDT/compile, semua POP dipakai)
        if titik:
            sel0 = indeks.sel_dari_titik(titik)
            titik += [p["ll"] for p in pops if indeks.sel_dari_titik([p["ll"]], 0) & sel0]
        else:
            titik = [p["ll"] for p in pops]
        self.sel_kerja = indeks.sel_dari_titik(titik) if titik else None
        ix = []
        nb = len(self.peran.get("NASIONAL", []))
        for i, p in enumerate(self.peran.get("NASIONAL", [])):
            base = 10 + 55 * i / max(nb, 1)
            self.progres("Preparing the cable index of %s for the work area" % os.path.basename(p), base)
            ix.append(indeks.IndeksKabel.siapkan(
                p, os.path.join(self.cache, "indeks"), sel_perlu=self.sel_kerja,
                progres=lambda t, pc, base=base: self.progres(t, base + 55.0 / max(nb, 1) * (pc or 0) / 100.0),
                batal=self._batal))
        self.data = mesin.Data(ix, comps, pops, jalan=self._jalan if (self.pakai_osm or self.jalan_lokal) else None)
        for nm, nk in self.data.pop_dugaan:
            self.temuan.tambah(V.PERINGATAN, "Kelengkapan",
                               T("folder POP '%s' tidak punya titik POP/OLT di data; lokasi POP diambil dari pangkal %d "
                                 "kabel 144C feeder-nya",
                                 "POP folder '%s' has no POP/OLT point in the data; the POP location is taken from the "
                                 "start of its %d feeder 144C cables") % (nm, nk), "",
                               T("tambahkan titik POP ini di folder OLT compile atau di KMZ daftar POP",
                                 "add this POP point to the OLT folder of the compilation or to the POP list KMZ"))
        for p in self.peran.get("AUDIT", []):
            self.data.audit += sumber.baca_audit(p) or []
        if not self.data.pops:
            self.temuan.tambah(V.PERINGATAN, "Kelengkapan", T("tidak ada titik POP/OLT (dari compile atau KMZ daftar "
                                                              "POP): arah feeder dan pilihan feeder baru tidak bisa dihitung",
                                                              "no POP/OLT point (from the compilation or a POP list KMZ): "
                                                              "the feeder direction and the new-feeder option cannot be "
                                                              "worked out"), "",
                               T("tambahkan KMZ daftar POP, atau KMZ compile yang memuat folder OLT",
                                 "add the POP list KMZ, or a compilation KMZ that has an OLT folder"))
        return self.data

    def pastikan_area(self, titik):
        """Klik peta di luar area kerja: tambahkan area itu ke indeks kabel nasional (beberapa detik)."""
        sel = indeks.sel_dari_titik(titik)
        for ix in self.data.indeks:
            ix.pastikan(sel, lambda t, pc: self.progres(t, pc), self._batal)

    # ------------------------------------------------------------------ jalan OSM
    def _jalan(self, bb):
        out = []
        if self.jalan_lokal:
            out.extend(j for j in self.jalan_lokal if _kena(j["ll"], bb))
            if out:
                return out
        if not self.pakai_osm or self._jalan_gagal:
            return out
        folder = os.path.join(self.cache, "osm")
        os.makedirs(folder, exist_ok=True)
        for ix in range(int(math.floor(bb[0] / UBIN)), int(math.floor(bb[2] / UBIN)) + 1):
            for iy in range(int(math.floor(bb[1] / UBIN)), int(math.floor(bb[3] / UBIN)) + 1):
                if self._jalan_gagal:           # server dianggap luring: jangan menunggu ubin berikutnya
                    return out
                key = (ix, iy)
                if key not in self._ubin:
                    self._ubin[key] = self._ubin_osm(folder, ix, iy)
                out.extend(self._ubin[key])
        return out

    def _ubin_cache(self, folder, ix, iy):
        fn = os.path.join(folder, "jalan_%d_%d.json" % (ix, iy))
        if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < UMUR_CACHE_HARI * 86400:
            try:
                with open(fn, encoding="utf-8") as fh:
                    return [{"kelas": k, "ll": [tuple(p) for p in ll]} for k, ll in json.load(fh)]
            except (OSError, ValueError):
                return None
        return None

    def _tulis_ubin(self, folder, ix, iy, jl):
        fn = os.path.join(folder, "jalan_%d_%d.json" % (ix, iy))
        tmp = fn + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([[j["kelas"], [[round(p[0], 7), round(p[1], 7)] for p in j["ll"]]] for j in jl], fh)
        os.replace(tmp, fn)

    def siapkan_jalan(self, targets):
        """Unduh SEKALIGUS semua ubin jalan yang dibutuhkan FDT-FDT ini: ubin yang belum ada di cache digabung menjadi
        persegi <= 4x4 ubin (~22 km), satu permintaan Overpass per persegi, lalu dipecah lagi ke cache per ubin.
        Bitung + Tomohon: 16 permintaan -> beberapa saja (antrean server publik adalah penyebab utama lambat)."""
        if not self.pakai_osm or self.jalan_lokal or self.data is None:
            return
        folder = os.path.join(self.cache, "osm")
        os.makedirs(folder, exist_ok=True)
        perlu = set()
        for f in targets:
            pop = mesin.pilih_pop(f["ll"], self.data, maks_m=self.prm["pop_maks_m"])
            bb = mesin.bbox_jalan(f["ll"], pop, self.prm)
            for ix in range(int(math.floor(bb[0] / UBIN)), int(math.floor(bb[2] / UBIN)) + 1):
                for iy in range(int(math.floor(bb[1] / UBIN)), int(math.floor(bb[3] / UBIN)) + 1):
                    perlu.add((ix, iy))
        kurang = sorted(k for k in perlu if k not in self._ubin and self._ubin_cache(folder, *k) is None)
        if not kurang:
            return
        kotak = _kelompok(kurang, 4)
        for i, (ix0, iy0, ix1, iy1) in enumerate(kotak):
            if self._jalan_gagal:
                return
            bb = (ix0 * UBIN, iy0 * UBIN, (ix1 + 1) * UBIN, (iy1 + 1) * UBIN)
            jl = self._unduh(bb, "area %d/%d (%d ubin)" % (i + 1, len(kotak), (ix1 - ix0 + 1) * (iy1 - iy0 + 1)))
            if jl is None:
                continue
            per = {(ix, iy): [] for ix in range(ix0, ix1 + 1) for iy in range(iy0, iy1 + 1)}
            for j in jl:
                xs = [p[0] for p in j["ll"]]
                ys = [p[1] for p in j["ll"]]
                for ix in range(max(ix0, int(math.floor(min(xs) / UBIN))), min(ix1, int(math.floor(max(xs) / UBIN))) + 1):
                    for iy in range(max(iy0, int(math.floor(min(ys) / UBIN))), min(iy1, int(math.floor(max(ys) / UBIN))) + 1):
                        per[(ix, iy)].append(j)
            for k, v in per.items():
                self._tulis_ubin(folder, k[0], k[1], v)
                self._ubin[k] = v

    def _unduh(self, bb, label):
        """Satu permintaan Overpass dengan percobaan ulang sesuai jenis galat. -> daftar jalan atau None bila gagal.
        Tanpa koneksi: langsung berhenti (tidak menunggu); 429/406: jeda 30-60 detik; 5xx/timeout: jeda 5-15 detik."""
        galat = None
        jeda = JEDA_SIBUK
        for coba in range(COBA_UBIN):
            if coba:
                self.progres("OpenStreetMap server busy, retrying %s (%d/%d)" % (label, coba + 1, COBA_UBIN))
                for _ in range(jeda[coba - 1]):
                    time.sleep(1)
                    self.progres("Waiting for the OpenStreetMap server (as its usage policy asks)")
            else:
                self.progres("Downloading the road map (OpenStreetMap) %s" % label)
            try:
                isi = ("data=" + _urlq(osm.query(bb))).encode("ascii")
                return osm.parse_overpass(self.ambil(self.overpass or OVERPASS, isi))
            except Dibatalkan:
                raise
            except Exception as e:
                galat = e
                jenis = jenis_galat(e)
                if jenis == "LURING":
                    self._jalan_gagal = True        # tidak ada koneksi: area lain juga tidak akan berhasil sekarang
                    break
                jeda = JEDA_COBA if jenis == "BATAS" else JEDA_SIBUK
        self._ubin_gagal.append(bb)
        if len(self._ubin_gagal) >= 3 and not any(self._ubin.values()):
            self._jalan_gagal = True
        self.temuan.tambah(V.PERINGATAN, "Kelengkapan", T("peta jalan OpenStreetMap %s (%.2f, %.2f) tidak terunduh (%s): "
                                                          "di area itu, bagian tanpa kabel yang ada digambar sebagai garis "
                                                          "bantu lurus", "the OpenStreetMap road map %s (%.2f, %.2f) could "
                                                          "not be downloaded (%s): in that area, parts without existing "
                                                          "cable are drawn as straight helper lines") % (
                               label, bb[1], bb[0], {"LURING": T("tidak ada koneksi internet", "no internet connection"),
                                                     "BATAS": T("server membatasi permintaan", "the server is limiting "
                                                                "requests"),
                                                     "SIBUK": T("server sedang sibuk", "the server is busy")}[
                                   jenis_galat(galat)]), "",
                           T("jalankan ulang nanti (area yang gagal dicoba lagi otomatis), atau pakai layer jalan sendiri "
                             "di bagian Advanced", "run again later (failed areas are retried automatically), or use "
                             "your own road layer in the Advanced section"))
        return None

    def _ubin_osm(self, folder, ix, iy):
        jl = self._ubin_cache(folder, ix, iy)
        if jl is not None:
            return jl
        bb = (ix * UBIN, iy * UBIN, (ix + 1) * UBIN, (iy + 1) * UBIN)
        jl = self._unduh(bb, "ubin %d,%d" % (ix, iy))
        if jl is None:
            return []
        self._tulis_ubin(folder, ix, iy, jl)
        return jl

    # ------------------------------------------------------------------ 3. analisis
    def siapkan_uji(self):
        """Mode uji akurasi: FDT target = FDT yang sudah didesain di compile (lihat uji_akurasi.py)."""
        from . import uji_akurasi
        self.target = uji_akurasi.soal(self.data.compiles)
        self.uji = True
        return self.target

    def analisis(self, targets=None):
        targets = self.target if targets is None else targets
        self.hasil = []
        self.nilai_uji = []
        if not self.uji:
            self._pakai_hasil_lama(targets)
        self._lupakan_usulan(targets)
        self.siapkan_jalan(targets)
        try:
            self.periksa_gambar(targets)
        except Exception as e:      # pemeriksaan gambar pelengkap: desain tetap jalan
            _log.note(e, "periksa gambar")
        n = len(targets)
        self._kec_batch = set()     # desain lama FDT yang dirancang ulang di proses ini (tetap tersembunyi sampai selesai)
        grup = self._siapkan_proyek(targets)
        for i, f in enumerate(targets):
            self.progres("Designing FDT %s (%d/%d)" % (f["kode"], i + 1, n), 70 + 25.0 * i / max(n, 1))
            try:
                if not f.get("_uji"):
                    self._kec_batch |= set(f.get("_kecuali") or ())
                self.data.kecuali = set(f["_uji"]["kecuali"]) if f.get("_uji") else set(self._kec_batch)
                self.hasil.append(mesin.analisis(f, self.data, self.prm))
                try:        # label infra saja (keputusan dan biaya tidak berubah)
                    mesin.label_infra_akhir(self.hasil[-1], getattr(self, "jalur_distribusi", None) or [],
                                            getattr(self, "tiang_distribusi", None) or [], self.prm)
                except Exception as e:
                    _log.note(e, "label infra")
                if not f.get("_uji"):
                    # FDT berikutnya dalam proses yang sama melihat tube & kabel yang baru diusulkan (tidak dobel)
                    try:
                        mesin.komit(self.hasil[-1], self.data, self.prm)
                    except Exception as e:
                        self.temuan.tambah(V.INFO, "Proses", T("usulan FDT %s tidak bisa dicatat ke buku tube (%s)",
                                                               "the proposal for FDT %s could not be added to the tube "
                                                               "book (%s)") % (f["kode"], str(e)[:100]))
                    self._catat_feeder_proyek(f, self.hasil[-1], grup)
                if f.get("_uji"):
                    from . import uji_akurasi
                    self.nilai_uji.append(uji_akurasi.nilai(self.hasil[-1]))
            except Dibatalkan:
                raise
            except Exception as e:  # satu FDT gagal tidak menghentikan FDT lain
                self.temuan.tambah(V.PERINGATAN, "Proses", T("FDT %s gagal dianalisis (%s); FDT ini ditandai 'Perlu "
                                                             "dirancang manual'", "FDT %s could not be analysed (%s); it "
                                                             "is marked 'Needs manual design'") % (f["kode"], str(e)[:150]),
                                   "", T("rancang FDT ini secara manual dan kirim log ke pembuat",
                                         "design this FDT by hand and send the log to the author"))
                self.hasil.append(mesin.hasil_gagal(f, self.data, self.prm, str(e)[:150]))
        self.data.kecuali = set()
        return self.hasil

    def _lupakan_usulan(self, targets):
        """FDT yang dirancang (ulang) tidak boleh melihat usulannya sendiri dari proses sebelumnya di sesi ini (kabel
        virtual _TEMBUKU_BATCH, tube yang dicatat, FDT tambahan di traksi yang dipetik) - tanpa ini proses kedua
        menyambung ke kabel usulannya sendiri (uji geser 23-11-2026: kabel baru 5 m, nomor tube terus naik). Usulan FDT
        lain tetap terlihat, jadi FDT yang dirancang satu per satu tetap tidak berebut tube."""
        if self.data is None:
            return
        kode = {str(f.get("kode") or "").upper() for f in targets}
        for c in self.data.compiles:
            c.pop("_peta_traksi", None)
            for t in c.get("traksi", {}).values():
                if t.get("_tambahan"):
                    t["_tambahan"] = [x for x in t["_tambahan"] if str(x).upper() not in kode]
            if c.get("berkas") != "_TEMBUKU_BATCH":
                continue
            c["traksi"] = {k: t for k, t in c["traksi"].items()
                           if not any(str(f.get("kode") or "").upper() in kode for f in t.get("fdt", ()))}
            c["kabel"] = [k for k in c["kabel"] if str(k.get("fdt_proyek") or "").upper() not in kode]
            c["fdt"] = [f for f in c["fdt"] if str(f.get("kode") or "").upper() not in kode]
            c.pop("_peta_traksi", None)
        self.data._ledger.clear()

    def periksa_gambar(self, targets, maks_pesan=25):
        """1.6.0: periksa bentuk gambar setiap kabel compile dan inventaris di area kerja (POP sampai FDT). Kabel yang
        janggal TIDAK ditolak (tube-nya tetap nyata); dilaporkan di pemeriksaan input dan dicatat di data.gambar_rusak
        agar hasil FDT yang memakainya diberi peringatan. Lihat inti/cek_gambar.py untuk kebijakan dan ambangnya."""
        from .inti import cek_gambar as CG
        self.data.gambar_rusak = {}
        kec, self.data.kecuali = self.data.kecuali, set()
        kabel, jalan, bbs = {}, {}, []
        try:
            for f in targets:
                pop = mesin.pilih_pop(f["ll"], self.data, maks_m=self.prm["pop_maks_m"])
                bb = mesin.bbox_jalan(f["ll"], pop, self.prm)
                if any(b[0] <= bb[0] and b[1] <= bb[1] and b[2] >= bb[2] and b[3] >= bb[3] for b in bbs):
                    continue
                bbs.append(bb)
                for k in self.data.kabel_compile(bb) + self.data.koridor_compile(bb) + self.data.kabel_nasional(bb):
                    kabel.setdefault(k["id"], k)
                if self.data.jalan is not None:
                    try:
                        for j in self.data.jalan(bb) or []:
                            jalan[id(j)] = j
                    except Exception as e:      # tanpa jalan: garis lurus tetap diperiksa tanpa pengecualian jalan
                        _log.note(e, "periksa gambar jalan")
        finally:
            self.data.kecuali = kec
        dj = CG.JalanDekat(list(jalan.values()))
        dj = dj if dj else None
        temu, sudah = [], set()
        for k in kabel.values():
            masalah = CG.periksa(k.get("ll") or [], dj)
            if masalah:
                self.data.gambar_rusak[k["id"]] = masalah
                # satu tempat cukup dilaporkan sekali: garis yang sama sering tersimpan beberapa kali (New Cable, Colo
                # Cable, Infra satu traksi) atau dipakai bersama beberapa traksi di satu jalur tiang
                kunci = tuple((x["jenis"], round(x["ll"][0], 4), round(x["ll"][1], 4)) for x in masalah)
                if kunci in sudah:
                    continue
                sudah.add(kunci)
                temu.append((k, masalah))
        if not temu:
            return
        n_c = sum(1 for k, _m in temu if k.get("sumber") == "COMPILE")
        def berat(m):
            return max((x["m"] * (10 if x["jenis"] == "LOMPAT" else 3 if x["jenis"] == "LURUS" else 1)) for x in m)
        temu.sort(key=lambda km: (km[0].get("sumber") != "COMPILE", -berat(km[1])))
        for k, masalah in temu[:maks_pesan]:
            compile_ = k.get("sumber") == "COMPILE"
            nama = (k.get("traksi") or k.get("feeder") or k["id"]) if compile_ else (k.get("nama") or k["id"])
            berkas = os.path.basename(str((k.get("grup") or [""])[0])) if compile_ else T("inventaris kabel", "cable inventory")
            serius = any(x["jenis"] == "LOMPAT" or (x["jenis"] == "LURUS" and compile_) for x in masalah)
            rinci = "; ".join("%s, %s m, di %.6f, %.6f" % (CG.NAMA[x["jenis"]], "{:,}".format(x["m"]).replace(",", "."),
                                                           x["ll"][1], x["ll"][0]) for x in masalah)
            rinci_en = "; ".join("%s, %s m, at %.6f, %.6f" % (CG.NAMA_EN[x["jenis"]], "{:,}".format(x["m"]), x["ll"][1],
                                                             x["ll"][0]) for x in masalah)
            self.temuan.tambah(V.PERINGATAN if serius else V.INFO, "Gambar kabel",
                               T("Kabel %s %s: %s.", "%s cable %s: %s.") % (
                                   T("compile", "compilation") if compile_ else T("inventaris", "inventory"), nama,
                                   T(rinci, rinci_en)), berkas,
                               T("kabelnya tetap dipakai; kalau sempat, rapikan gambar aslinya (koordinat bisa ditempel "
                                 "di pencarian Google Earth)", "the cable is still used; when you can, tidy the original "
                                 "drawing (paste the coordinates into Google Earth search)"))
        self.temuan.tambah(V.PERINGATAN if n_c else V.INFO, "Gambar kabel", T(
            "Ada %d kabel di sekitar FDT yang gambarnya kurang rapi (%d di compile, %d di inventaris)%s. Semuanya tetap "
            "dipakai. Kalau dipakai FDT, Tembuku menggambarnya ulang mengikuti jalan dan memberi tahu bila panjang "
            "sebenarnya mengubah ukuran kabel atau redaman.", "%d cables around the FDTs are drawn poorly (%d in the "
            "compilation, %d in the inventory)%s. All are still used. When an FDT uses one, Tembuku redraws it along the "
            "road and tells you if the real length changes the cable size or the signal budget.") % (
            len(temu), n_c, len(temu) - n_c, (T("; %d yang paling perlu dicek ditampilkan",
                                                "; the %d that most need a look are shown") % maks_pesan)
            if len(temu) > maks_pesan else ""))

    def _siapkan_proyek(self, targets):
        """Arahan atasan 18-11-2026 (kasus Rajawali): FDT dalam satu berkas target yang berdekatan = satu proyek. Tiap FDT
        diberi _proyek_sisa = jumlah FDT proyek yang belum dirancang (termasuk dirinya), sehingga feeder existing hanya
        dipakai bila tube kosongnya cukup untuk seluruh proyek. Urutan FDT tidak diubah. -> {id(f): daftar FDT proyek}."""
        for f in targets:
            f.pop("_proyek_sisa", None)
            f.pop("_proyek_feeder", None)
            f.pop("_proyek_id", None)
        grup = {}
        if self.uji or not self.prm.get("proyek_satu_feeder", True):
            return grup
        maks = float(self.prm.get("proyek_jarak_maks_m", 2000))
        per_berkas = {}
        for f in targets:
            if f.get("_uji") or not f.get("ll"):
                continue
            per_berkas.setdefault(os.path.normcase(str(f.get("berkas") or "")), []).append(f)
        for daftar in per_berkas.values():
            # rantai jarak (single linkage): FDT yang saling berdekatan <= maks menjadi satu proyek
            sisa = list(daftar)
            while sisa:
                kel = [sisa.pop(0)]
                tambah = True
                while tambah:
                    tambah = False
                    for g in list(sisa):
                        if any(geo.haversine(g["ll"], x["ll"]) <= maks for x in kel):
                            kel.append(g)
                            sisa.remove(g)
                            tambah = True
                kel.sort(key=daftar.index)
                for j, f in enumerate(kel):
                    if len(kel) > 1:
                        f["_proyek_sisa"] = len(kel) - j
                        f["_proyek_id"] = kel[0]["kode"]     # satu proyek = satu berkas hasil (tulis_kmz.kelompok_proyek)
                    grup[id(f)] = kel
        return grup

    @staticmethod
    def _catat_feeder_proyek(f, h, grup):
        """Feeder yang dipakai FDT pertama sebuah proyek menjadi pilihan utama FDT proyek berikutnya."""
        kel = grup.get(id(f)) or []
        if len(kel) < 2 or h.get("keputusan") not in ("COLO", "COLO_CEK", "FEEDER_BARU"):
            return
        n = h.get("penomoran") or {}
        if not n.get("feeder"):
            return
        pin = {"feeder": int(n["feeder"]), "pop_folder": n.get("pop_folder") or "", "kode": f.get("kode")}
        for g in kel[kel.index(f) + 1:]:
            g.setdefault("_proyek_feeder", pin)

    def _pakai_hasil_lama(self, targets):
        """KMZ desain Tembuku dari proses sebelumnya di folder hasil = tube dan kabel yang sudah diusulkan. Dibaca seperti
        traksi compile supaya FDT yang dijalankan satu per satu tidak mendapat tube yang sama. KMZ milik FDT yang sedang
        dirancang ulang tidak dipakai (desain lamanya diganti)."""
        if self.data is None:
            return
        self.data.compiles = [c for c in self.data.compiles if not str(c.get("berkas", "")).startswith("_TEMBUKU_LAMA")]
        folder = self.folder_hasil
        if not folder or not os.path.isdir(folder):
            return
        kode_target = {str(f.get("kode") or "").upper() for f in targets}
        masukan = {os.path.normcase(os.path.abspath(p)) for p in self.paths}
        dipakai = []
        for nm in sorted(os.listdir(folder)):
            p = os.path.join(folder, nm)
            u = nm.upper()
            if not u.endswith(".KMZ") or u.startswith("TEMBUKU_") or u.endswith("_ANALISIS.KMZ") or \
                    u.endswith(" - HASIL.KMZ") or " - HASIL " in u or \
                    os.path.normcase(os.path.abspath(p)) in masukan or not sumber.keluaran_tembuku(p):
                continue
            try:
                c = sumber.baca_compile(p, V.Temuan())
            except (OSError, ValueError, KeyError, TypeError) as e:
                # KMZ lama yang rusak tidak menghentikan proses, tetapi dicatat (tidak ditelan diam-diam)
                self.temuan.tambah(V.INFO, "Kelengkapan", T("desain Tembuku sebelumnya tidak bisa dibaca (%s), dilewati",
                                                            "an earlier Tembuku design cannot be read (%s), skipped")
                                   % str(e)[:100], nm, "")
                continue
            if not c.get("traksi") or any(str(f.get("kode") or "").upper() in kode_target for f in c.get("fdt", [])):
                continue
            c["berkas"] = "_TEMBUKU_LAMA " + nm
            for t in c["traksi"].values():
                t["berkas"] = c["berkas"]
            for k in c.get("kabel", []):
                k["berkas"] = c["berkas"]
            self.data.compiles.insert(0, c)
            dipakai.append(nm)
        if dipakai:
            self.data._ledger.clear()
            self.temuan.tambah(V.INFO, "Kelengkapan", T("%d desain Tembuku sebelumnya di folder hasil ikut dihitung (tube dan "
                                                        "kabelnya dianggap sudah dipakai): %s",
                                                        "%d earlier Tembuku designs in the output folder are counted (their "
                                                        "tubes and cables are taken as used): %s")
                               % (len(dipakai), ", ".join(x[:60] for x in dipakai[:5])), "",
                               T("tempel desain itu ke compile, atau hapus KMZ-nya bila desain itu dibatalkan",
                                 "paste those designs into the compilation, or delete their KMZ if they were dropped"))

    def analisis_titik(self, lon, lat, kode=None):
        self.pastikan_area([(lon, lat)])
        self.siapkan_jalan([{"ll": (lon, lat)}])
        f = {"kode": kode or "FDT-KLIK", "ll": (lon, lat), "splitter": None, "rasio": None, "premises": None,
             "cluster": None, "area": kode or "KLIK PETA", "status": "New", "berkas": "klik peta"}
        return mesin.analisis(f, self.data, self.prm)

    # ------------------------------------------------------------------ 4. simpan
    def jalan_laporan(self, hasil, radius=0.015, maks_titik=150000):
        """Jalan di sekitar tiap FDT untuk latar peta laporan (vektor OSM, tanpa unduhan baru; bukan citra satelit
        pihak ketiga). Hanya dari cache yang sudah dipakai analisis; dibulatkan ~1 m dan dibatasi agar HTML ringan."""
        sumber = list(self.jalan_lokal or [])
        for v in self._ubin.values():
            sumber.extend(v or [])
        if not sumber:
            return []
        kotak = [(f[0] - radius, f[1] - radius, f[0] + radius, f[1] + radius) for f in (h["fdt"]["ll"] for h in hasil)]
        out, lihat, n = [], set(), 0
        for j in sumber:
            ll = j["ll"]
            if not any(_kena(ll, bb) for bb in kotak):
                continue
            garis = [[round(p[1], 5), round(p[0], 5)] for p in ll]
            kunci = (tuple(garis[0]), tuple(garis[-1]), len(garis))
            if kunci in lihat:
                continue
            lihat.add(kunci)
            n += len(garis)
            if n > maks_titik:
                break
            out.append(garis)
        return out

    def _peta_tube(self, hasil):
        """Dasbor laporan: isi tube T1-T12 setiap feeder di POP yang dipakai proses ini.
        -> [{pop, feeder, tube: {T: 'lama' | kode FDT proses ini}}]. Tube yang tidak disebut = kosong."""
        if self.data is None:
            return []
        baru = {}
        for h in hasil:
            n = h.get("penomoran") or {}
            if h.get("keputusan") in ("COLO", "COLO_CEK", "COLO_MANUAL", "FEEDER_BARU") and h.get("pop") and n.get("feeder"):
                baru[(h["pop"]["nama"], int(n["feeder"]), int(n["t"]))] = h["fdt"]["kode"]
        out = []
        for pop in sorted({p for p, _f, _t in baru}):
            led = self.data.ledger(pop) or {}
            fes = sorted({f for f in led if isinstance(f, int)} | {f for p, f, _t in baru if p == pop})
            for fe in fes:
                isi = {int(t): "lama" for t in (led.get(fe) or {}).get("tube", ()) if str(t).isdigit()}
                for (p, f, t), kode in baru.items():
                    if p == pop and f == fe:
                        isi[t] = kode
                out.append({"pop": pop, "feeder": fe, "tube": {str(t): v for t, v in sorted(isi.items())}})
        return out

    def simpan(self, folder_keluar, hasil=None, alat="Tembuku"):
        hasil = self.hasil if hasil is None else hasil
        os.makedirs(folder_keluar, exist_ok=True)
        tgl = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")      # detik: dua proses dalam satu menit tidak saling menimpa
        out = {"kmz": [], "analisis": [], "html": None, "semua": None, "temuan": None}
        self.progres("Writing the KMZ files and the report", 96)
        terpakai = set()
        tgl_nama = datetime.date.today().strftime("%d-%m-%Y")
        # 1.6.1: FDT satu proyek (berkas, POP dan feeder sama) = SATU berkas desain dengan satu traksi gabungan
        grupe = tulis_kmz.kelompok_proyek(hasil, self.prm)
        kmz_h = {}
        for grp in grupe:
            dasar = _nama_desain(grp[0], tgl_nama)
            nm, i = dasar + ".kmz", 2
            while nm.lower() in terpakai:           # nama kembar: jangan menimpa KMZ sebelumnya
                nm = "%s_%d.kmz" % (dasar, i)
                i += 1
            terpakai.add(nm.lower())
            p = tulis_kmz.tulis(grp, os.path.join(folder_keluar, nm), self.prm, nm[:-4], ikon_lokal=self.ikon_lokal)
            for h in grp:
                kmz_h[id(h)] = p
            if self.prm.get("tulis_kmz_analisis", False):
                na = nm[:-4] + "_ANALISIS.kmz"
                out["analisis"].append(tulis_kmz.tulis(grp, os.path.join(folder_keluar, na), self.prm, na[:-4],
                                                      ikon_lokal=self.ikon_lokal, analisis=True))
        out["kmz"] = [kmz_h[id(h)] for h in hasil]      # sejajar dengan hasil (FDT satu proyek berbagi berkas)
        if len(hasil) > 1:
            out["semua"] = tulis_kmz.tulis(hasil, os.path.join(folder_keluar, "TEMBUKU_SEMUA_%s.kmz" % tgl), self.prm,
                                           "Tembuku - semua FDT %s" % tgl, ikon_lokal=self.ikon_lokal)
        # seperti hasil desainer: KMZ APD Distribusi masukan dengan folder Feeder terisi (bila FDT berasal dari KMZ
        # distribusi yang punya folder Feeder template); nama = nama dokumen distribusi + ' - HASIL.kmz'
        out["distribusi"] = []
        sumber_target = {os.path.basename(p): p for p in self.peran.get("TARGET", [])}
        for grp in grupe:
            h = grp[0]
            asal = sumber_target.get(h["fdt"].get("berkas") or "")
            if not asal or h["keputusan"] == "PERLU_MANUAL":
                continue
            sebarkas = sum(1 for g in grupe if g[0]["fdt"].get("berkas") == h["fdt"].get("berkas")) > 1
            if not tulis_kmz.bisa_isi_distribusi(asal):
                # FDT dari berkas titik FDT saja (belum ada desain distribusi): file HASIL = desain feeder proyek ini,
                # supaya setiap proyek selalu punya satu file '- HASIL.kmz' yang diserahkan
                dasar = re.sub(r"\s*\(\d+\)$", "", os.path.splitext(os.path.basename(asal))[0]).strip()
                nm = dasar + " - HASIL.kmz"
                if nm.lower() in terpakai or sebarkas:
                    nm = dasar + " %s - HASIL.kmz" % _aman(h["fdt"]["kode"])
                terpakai.add(nm.lower())
                try:
                    out["distribusi"].append(tulis_kmz.tulis(grp, os.path.join(folder_keluar, nm), self.prm, nm[:-4],
                                                             ikon_lokal=self.ikon_lokal))
                except OSError as e:
                    self.temuan.tambah(V.PERINGATAN, "Hasil", T("KMZ HASIL tidak bisa ditulis (%s)",
                                                               "the HASIL KMZ could not be written (%s)") % str(e)[:120],
                                       os.path.basename(asal), "")
                continue
            nm = tulis_kmz.nama_hasil_distribusi(asal)
            if nm.lower() in terpakai or sebarkas or os.path.normcase(os.path.join(folder_keluar, nm)) in \
                    {os.path.normcase(p) for p in self.paths}:
                nm = nm[:-4] + " %s.kmz" % _aman(h["fdt"]["kode"])
            terpakai.add(nm.lower())
            try:
                out["distribusi"].append(tulis_kmz.tulis_distribusi(grp, asal, os.path.join(folder_keluar, nm),
                                                                    self.prm, ikon_lokal=self.ikon_lokal))
            except (OSError, ValueError, KeyError, UnicodeDecodeError) as e:
                self.temuan.tambah(V.PERINGATAN, "Hasil", T("KMZ distribusi berisi feeder tidak bisa ditulis (%s)",
                                                           "the distribution KMZ with the feeder could not be written (%s)")
                                   % str(e)[:120], os.path.basename(asal), "")
        if len(hasil) > 1 and self.prm.get("tulis_kmz_analisis", False):
            out["analisis"].append(tulis_kmz.tulis(
                hasil, os.path.join(folder_keluar, "TEMBUKU_SEMUA_%s_ANALISIS.kmz" % tgl), self.prm,
                "Tembuku - bahan tinjauan semua FDT %s" % tgl, ikon_lokal=self.ikon_lokal, analisis=True))
        salah = []
        for pth in list(dict.fromkeys(out["kmz"])) + ([out["semua"]] if out["semua"] else []):
            salah += ["%s: %s" % (os.path.basename(pth), m) for m in tulis_kmz.periksa_template(pth)]
        for h, pth in zip(hasil, out["kmz"]):
            di_kmz = tulis_kmz.lokasi_fdt(pth).get(tulis_kmz.escape(h["fdt"]["kode"]), [])
            asal = (float(h["fdt"]["ll"][0]), float(h["fdt"]["ll"][1]))
            if di_kmz != [asal]:
                salah.append("%s: lokasi FDT di KMZ tidak sama dengan data masukan" % h["fdt"]["kode"])
        if salah:
            self.temuan.tambah(V.PERINGATAN, "Kesesuaian template", T("susunan folder KMZ hasil berbeda dari template "
                                                                      "Feeder: %s", "the folder layout of the result KMZ "
                                                                      "differs from the Feeder template: %s")
                               % "; ".join(salah[:3]), "", T("laporkan ke pembuat Tembuku", "report this to the Tembuku author"))
        else:
            self.temuan.tambah(V.INFO, "Kesesuaian template", T("%d KMZ hasil sudah diperiksa ulang: susunan folder Feeder "
                                                                "lengkap dan urut seperti template, ikon tertanam, lokasi "
                                                                "FDT sama dengan data masukan",
                                                                "%d result KMZ files were re-checked: the Feeder folders "
                                                                "are complete and in template order, icons are embedded, "
                                                                "and FDT locations equal the input data")
                               % (len(out["kmz"]) + (1 if out["semua"] else 0)))
        uji = None
        if self.nilai_uji:
            from . import uji_akurasi
            uji = {"ringkasan": uji_akurasi.ringkasan(self.nilai_uji), "baris": self.nilai_uji}
            nb = [x["fdt"] for x in self.nilai_uji if x.get("sudah_dibangun")]
            if nb:
                self.temuan.tambah(V.INFO, "Uji akurasi",
                                   T("%d FDT tidak bisa diuji adil: desainer membuat feeder baru, dan feeder itu kini sudah "
                                     "ada di inventaris kabel (lewat tepat di FDT), sehingga Tembuku memakainya. Ini bukan "
                                     "kesalahan: %s",
                                     "%d FDTs cannot be tested fairly: the designer built a new feeder, and that feeder is "
                                     "now in the cable inventory (passing right at the FDT), so Tembuku uses it. This is "
                                     "not an error: %s") % (len(nb), ", ".join(nb[:8])))
            out["uji"] = os.path.join(folder_keluar, "TEMBUKU_UJI_AKURASI_%s.csv" % tgl)
            with open(out["uji"], "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                kol = [("fdt", "FDT"), ("traksi", "Traksi"), ("berkas", "Berkas"), ("desainer", "Keputusan desainer"),
                       ("tembuku", "Keputusan Tembuku"), ("cocok", "Keputusan sama"),
                       ("folder_desainer", "Folder desainer"), ("folder_tembuku", "Folder Tembuku"),
                       ("folder_cocok", "Folder sama"), ("tap_meleset_m", "Selisih titik sambung (m)"),
                       ("baru_desainer_m", "Kabel baru desainer (m)"), ("baru_tembuku_m", "Kabel baru Tembuku (m)"),
                       ("jalur_sesuai_pct", "Jalur sama (%)"), ("garis_bantu_m", "Garis bantu (m)"),
                       ("batas", "Perlu ditinjau")]
                w.writerow([j for _k, j in kol])

                def sel(k, v):
                    if k in ("desainer", "tembuku"):
                        return str(mesin.nama_keputusan(v)) if v else ""
                    if isinstance(v, bool):
                        return "ya" if v else "tidak"
                    return "" if v is None else v
                for x in self.nilai_uji:
                    w.writerow([sel(k, x.get(k)) for k, _j in kol])
        meta = {"waktu": laporan.tanggal(), "alat": alat, "temuan": self.temuan.daftar, "uji": uji,
                "jalan": self.jalan_laporan(hasil),
                "peta_ekstra": self.peta_laporan or [],
                "berkas": {str(sumber.NAMA_PERAN.get(k, "versi lama yang dilewati" if k == "LAIN_VERSI" else k)):
                           [os.path.basename(p) for p in v] for k, v in self.peran.items() if v},
                "bukti": {os.path.basename(p): str(a) for p, a in (getattr(self, "bukti", None) or {}).items() if a},
                "parameter": {profil.LABEL_ID.get(k, k): [self.prm[k], profil.JENIS_ID.get(v[1], v[1]), v[2]]
                              for k, v in profil.BAWAAN.items()}}
        try:
            meta["tube"] = self._peta_tube(hasil)
        except Exception as e:     # dasbor tube hanya pelengkap: laporan tetap ditulis
            _log.note(e, "peta tube")
        out["html"] = laporan.tulis(hasil, os.path.join(folder_keluar, "TEMBUKU_LAPORAN_%s.html" % tgl), meta)
        out["csv"] = os.path.join(folder_keluar, "TEMBUKU_RINGKASAN_%s.csv" % tgl)
        with open(out["csv"], "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["FDT", "Keputusan", "Perlu ditinjau", "Folder compile (F/T)", "Feeder yang dipakai", "Jenis colo",
                        "Sisa tube", "Kabel baru (m)", "Garis bantu yang harus digambar ulang (m)",
                        "Feeder baru dari POP (m)", "Jalur lewat feeder dibanding feeder baru (x)", "Redaman sinyal (dB)",
                        "POP", "Alasan", "Peringatan", "Berkas KMZ desain", "Tube (kelompok)", "Titik sambung di"])
            for h, pth in zip(hasil, out["kmz"]):
                k = h.get("terpilih") or {}
                fb = h.get("feeder_baru") or {}
                rute = k.get("rute") or (fb if h["keputusan"] == "FEEDER_BARU" else {})
                n = h["penomoran"]
                w.writerow([h["fdt"]["kode"], str(mesin.nama_keputusan(h["keputusan"])),
                            "ya - hampir seimbang" if h.get("batas") else "",
                            "F%d_T%d" % (n["feeder"], n["t"]), k.get("nama", ""), k.get("label_colo", ""),
                            k.get("ket_kapasitas", ""), k.get("kabel_baru_m", round(fb.get("panjang_m", 0)) if
                                                               h["keputusan"] == "FEEDER_BARU" else ""),
                            round(rute.get("bantu_m", 0)) if rute else "", round(fb["panjang_m"]) if fb else "",
                            k.get("rasio_jalur", ""), (k.get("budget") or {}).get("total_db", ""),
                            h["pop"]["nama"] if h["pop"] else "", " | ".join(h["alasan"]), " | ".join(h["peringatan"]),
                            os.path.basename(pth),
                            ("T%s (%s)" % (n["t"], n.get("kelompok") or "-")) if n.get("t") else "",
                            str(mesin.label_tap(k["tap_slack"])) if k.get("tap_slack")
                            else ("titik baru di tengah kabel (pastikan ada cadangan kabel)" if k else "")])
        # buku tube per feeder (audit): tube terpakai & kosong per kelompok, dari hierarki folder compile + hasil ini
        out["tube"] = os.path.join(folder_keluar, "TEMBUKU_BUKU_TUBE_%s.csv" % tgl)
        with open(out["tube"], "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["POP", "Feeder", "Jumlah FDT", "Tube terpakai", "Kosong kelompok 96F", "Kosong kelompok 48F",
                        "Status", "Usulan Tembuku pada proses ini"])
            g96, g48 = mesin.kelompok_tube(self.prm)
            usul = {}
            for h in hasil:
                n = h["penomoran"]
                if h["keputusan"] != "PERLU_MANUAL" and h.get("pop"):
                    # kunci = POP pemilik folder feeder (sama dengan buku tube mesin), bukan nama titik POP terdekat
                    np_ = self.data.nama_pop(n.get("pop_folder") or h["pop"]["nama"])
                    usul.setdefault((sumber.kunci_pop(np_), int(n["feeder"])), []).append(
                        "%s -> T%s" % (h["fdt"]["kode"], n["t"]))
            # semua POP yang punya feeder di compile (nama folder POP boleh berbeda dari nama titik POP) + titik POP
            nama_pop, lihat = [], set()
            for c in self.data.compiles:
                for (_b, popf, _f, _k) in c["traksi"]:
                    nm = self.data.nama_pop(popf, c)
                    if sumber.kunci_pop(nm) not in lihat:
                        lihat.add(sumber.kunci_pop(nm))
                        nama_pop.append(nm)
            for p in self.data.pops:
                if sumber.kunci_pop(p["nama"]) not in lihat:
                    lihat.add(sumber.kunci_pop(p["nama"]))
                    nama_pop.append(p["nama"])
            kec_lama = self.data.kecuali
            self.data.kecuali = set(getattr(self, "_kec_batch", None) or ())   # desain lama yang dirancang ulang: tidak dobel
            try:
                for nm in nama_pop:
                    led = self.data.ledger(nm)
                    kp = sumber.kunci_pop(nm)
                    for fe in sorted(set(led) | set(f for (pp, f) in usul if pp == kp)):
                        e = led.get(fe, {"tube": set(), "fdt": set()})
                        k96, k48 = sorted(g96 - e["tube"]), sorted(g48 - e["tube"])
                        w.writerow([nm, fe, len(e["fdt"]), mesin._teks_tube(e["tube"]), mesin._teks_tube(k96),
                                    mesin._teks_tube(k48), "PENUH" if not k96 and not k48 else "masih ada tube kosong",
                                    "; ".join(usul.get((kp, fe), []))])
            finally:
                self.data.kecuali = kec_lama
        out["temuan"] = os.path.join(folder_keluar, "TEMBUKU_PEMERIKSAAN_INPUT_%s.txt" % tgl)
        with open(out["temuan"], "w", encoding="utf-8") as fh:
            fh.write("Tembuku - pemeriksaan input %s\n\n%s\n" % (meta["waktu"], self.temuan.teks() or "Tidak ada temuan."))
        return out


NAMA_BERKAS = {"COLO": "PAKAI_FEEDER", "COLO_CEK": "CEK_TUBE", "COLO_MANUAL": "PILIHAN_DESAINER",
               "FEEDER_BARU": "FEEDER_BARU", "PERLU_MANUAL": "MANUAL"}


def _kelompok(ubin, maks):
    """Ubin (ix, iy) -> persegi (ix0, iy0, ix1, iy1) yang menutup semua ubin, tiap persegi <= maks x maks ubin.
    Rakus: mulai dari ubin kiri-bawah yang belum tertutup, perluas selama persegi masih berisi ubin yang diminta."""
    sisa = set(ubin)
    out = []
    while sisa:
        ix0, iy0 = min(sisa)
        ix1, iy1 = ix0, iy0
        while ix1 - ix0 + 1 < maks and any((ix1 + 1, y) in sisa for y in range(iy0, iy1 + 1)):
            ix1 += 1
        while iy1 - iy0 + 1 < maks and any((x, iy1 + 1) in sisa for x in range(ix0, ix1 + 1)):
            iy1 += 1
        out.append((ix0, iy0, ix1, iy1))
        sisa -= {(x, y) for x in range(ix0, ix1 + 1) for y in range(iy0, iy1 + 1)}
    return out


def _kena(ll, bb):
    xs = [p[0] for p in ll]
    ys = [p[1] for p in ll]
    return max(xs) >= bb[0] and min(xs) <= bb[2] and max(ys) >= bb[1] and min(ys) <= bb[3]


def _nama_desain(h, tgl):
    """Nama berkas KMZ desain mengikuti pola berkas desain feeder yang dipakai compile:
    '<ID cluster>_APD Feeder KMZ_<nama area>_<dd-mm-yyyy>' (nama folder traksi tanpa awalan F/T). Bila ID cluster atau
    nama area tidak ada di data, dipakai kode FDT: 'TEMBUKU_<kode FDT>_<keputusan>'."""
    f = h["fdt"]
    if f.get("cluster") and f.get("area"):
        nama = "%s_APD Feeder KMZ_%s_%s" % (f["cluster"], f["area"], tgl)
        nama = "".join("_" if ch in '\\/:*?"<>|' or ord(ch) < 32 else ch for ch in nama).strip(" .")
        return nama[:120]
    return "TEMBUKU_%s_%s" % (_aman(f["kode"]), NAMA_BERKAS.get(h["keputusan"], h["keputusan"]))


def _aman(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)[:60]


def _urlq(s):
    from urllib.parse import quote
    return quote(s, safe="")
