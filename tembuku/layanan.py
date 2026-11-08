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
import time

from .inti import indeks, laporan, mesin, osm, profil, sumber, tulis_kmz
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
                self.temuan.tambah(V.INFO, "Kesesuaian data", T("FDT %s sudah ada di compile desain feeder (sudah punya "
                                                                "feeder); tetap dianalisis sebagai pembanding",
                                                                "FDT %s is already in the feeder design compilation (it "
                                                                "already has a feeder); it is still analysed for "
                                                                "comparison") % f["kode"])
        # area kerja = sekitar FDT target, compile dan POP: hanya area ini yang diindeks dari KMZ kabel nasional
        titik = [f["ll"] for f in self.target] + [p["ll"] for p in pops]
        for c in comps:
            titik += [f["ll"] for f in c["fdt"]] + [p["ll"] for p in c["pops"]]
            titik += [k["ll"][0] for k in c["kabel"]] + [k["ll"][-1] for k in c["kabel"]]
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
        self.siapkan_jalan(targets)
        n = len(targets)
        for i, f in enumerate(targets):
            self.progres("Designing FDT %s (%d/%d)" % (f["kode"], i + 1, n), 70 + 25.0 * i / max(n, 1))
            try:
                self.data.kecuali = set(f["_uji"]["kecuali"]) if f.get("_uji") else set()
                self.hasil.append(mesin.analisis(f, self.data, self.prm))
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

    def simpan(self, folder_keluar, hasil=None, alat="Tembuku"):
        hasil = self.hasil if hasil is None else hasil
        os.makedirs(folder_keluar, exist_ok=True)
        tgl = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out = {"kmz": [], "html": None, "semua": None, "temuan": None}
        self.progres("Writing the KMZ files and the report", 96)
        for h in hasil:
            nm = "TEMBUKU_%s_%s.kmz" % (_aman(h["fdt"]["kode"]), NAMA_BERKAS.get(h["keputusan"], h["keputusan"]))
            out["kmz"].append(tulis_kmz.tulis([h], os.path.join(folder_keluar, nm), self.prm, nm[:-4]))
        if len(hasil) > 1:
            out["semua"] = tulis_kmz.tulis(hasil, os.path.join(folder_keluar, "TEMBUKU_SEMUA_%s.kmz" % tgl), self.prm,
                                           "Tembuku - semua FDT %s" % tgl)
        uji = None
        if self.nilai_uji:
            from . import uji_akurasi
            uji = {"ringkasan": uji_akurasi.ringkasan(self.nilai_uji), "baris": self.nilai_uji}
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
        out["html"] = laporan.tulis(hasil, os.path.join(folder_keluar, "TEMBUKU_LAPORAN_%s.html" % tgl), meta)
        out["csv"] = os.path.join(folder_keluar, "TEMBUKU_RINGKASAN_%s.csv" % tgl)
        with open(out["csv"], "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["FDT", "Keputusan", "Perlu ditinjau", "Folder compile (F/T)", "Feeder yang dipakai", "Jenis colo",
                        "Sisa tube", "Kabel baru (m)", "Garis bantu yang harus digambar ulang (m)",
                        "Feeder baru dari POP (m)", "Jalur lewat feeder dibanding feeder baru (x)", "Redaman sinyal (dB)",
                        "POP", "Alasan", "Peringatan"])
            for h in hasil:
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
                            h["pop"]["nama"] if h["pop"] else "", " | ".join(h["alasan"]), " | ".join(h["peringatan"])])
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


def _aman(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)[:60]


def _urlq(s):
    from urllib.parse import quote
    return quote(s, safe="")
