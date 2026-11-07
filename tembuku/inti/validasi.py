# -*- coding: utf-8 -*-
# Tembuku - pemeriksaan & koreksi input (pra-cek).
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Dua prinsip, dipisah tegas:

  TOLERAN pada variasi tulisan yang DIKENAL (typo nama folder, '96c'/'96 Core', 'Exsisting', kode FDT huruf kecil,
  'F2-T3', koordinat lat/lon tertukar ...): dibaca dengan arti yang benar, dan SETIAP koreksi dicatat di laporan
  (prinsip robustness yang dibatasi, RFC 9413 2023: toleransi diam-diam menumpuk kesalahan; jadi tidak ada koreksi
  yang tidak dilaporkan).

  BERHENTI SEJAK AWAL (fail-fast) bila input wajib tidak ada, tidak terbaca, ditolak pengaman, atau salah jenis:
  analisis tidak dijalankan dan pesan menyebut apa yang salah dan apa yang harus dilakukan.

Kategori temuan mengikuti unsur mutu data ISO 19157-1:2023 (ps. 8.3): kelengkapan (omisi/komisi), konsistensi logis
(konseptual, domain, format, topologis), akurasi posisi, kualitas tematik. Kemiripan teks HANYA untuk nama folder/
atribut (tanpa angka, >= 5 huruf, skor >= 0,80 dan unggul >= 0,05 atas kandidat kedua); nilai berangka dinormalisasi
deterministik, tidak pernah ditebak (difflib menyebut 0,6 hanya 'rule of thumb'; tidak ada ambang baku anti-koreksi-palsu).
Lat/lon tertukar dikoreksi hanya bila tak ambigu: rentang lintang (-11,0..6,1) dan bujur (95,0..141,0) Indonesia tidak
beririsan, dan KML wajib berurutan lon,lat (OGC KML 2.3 ps. 6.2) - setiap titik yang dibalik dilaporkan. Kemiripan teks: difflib.SequenceMatcher (Ratcliff/Obershelp), ambang 0,80 hanya terhadap kosakata
template compile; sebagian besar typo adalah satu kesalahan sisip/hapus/ganti/tukar (Damerau 1964)."""
import difflib
import os
import re

FATAL, PERBAIKI, PERINGATAN, INFO = "FATAL", "DIKOREKSI", "PERINGATAN", "INFO"

# ----------------------------------------------------------------------------- kosakata template Compile APD Feeder
KANON = [
    "Cable", "New Cable Aerial/Udara", "Collo Cable", "UG Utilities", "Manhole", "Handhole", "Hanger", "New Hanger",
    "Eksisting Hanger", "Closure", "New Closure", "Eksisting Closure", "OTB", "New OTB", "Eksisting OTB", "FDT",
    "New FDT", "Eksisting FDT", "OLT", "Keterangan Infra", "New Cable Galian", "Collo Tiang", "New Infra", "Boundary",
    "Tiang 6 Meter", "Tiang 7 Meter", "Tiang 9 Meter", "New Tiang 6 Meter", "New Tiang 7 Meter", "New Tiang 9 Meter",
    "Eksisting Tiang 6 Meter", "Eksisting Tiang 7 Meter", "Eksisting Tiang 9 Meter", "FDT 72", "POP",
]
CORE = (12, 24, 48, 72, 96, 144, 192, 288, 576)
GANTI = [  # variasi ejaan yang dikenal -> bentuk template (diterapkan sebelum pencocokan kemiripan)
    (r"\bex[sc]?[ie]?s?ting\b|\bexisting\b|\beksis?ting\b|\bexsisting\b|\bexisitng\b|\beksiting\b", "Eksisting"),
    (r"\b[ck]ol+o\b", "Collo"), (r"\bkabel\b", "Cable"), (r"\b[ck]ab+le?\b", "Cable"), (r"\bcabel\b", "Cable"),
    (r"\bclos[uo]?re?\b|\bclousure\b|\bclosur\b", "Closure"), (r"\bhan?g+er\b", "Hanger"),
    (r"\bfe+d+e*r\b|\bfedeer\b|\bfeedr\b", "Feeder"), (r"\bket(e)?rangan\b", "Keterangan"),
    (r"\binfr?a\b", "Infra"), (r"\btiang\b", "Tiang"), (r"\bmeter\b|\bmtr\b|\bm\b", "Meter"),
    (r"\bud[ae]ra\b", "Udara"), (r"\baerial\b|\baireal\b|\barial\b", "Aerial"),
]


class Temuan(object):
    def __init__(self):
        self.daftar = []
        self._sudah = set()

    def tambah(self, tingkat, kategori, pesan, berkas="", saran=""):
        k = (tingkat, pesan, berkas)
        if k in self._sudah:
            return
        self._sudah.add(k)
        self.daftar.append({"tingkat": tingkat, "kategori": kategori, "pesan": pesan, "berkas": berkas, "saran": saran})

    def fatal(self):
        return [t for t in self.daftar if t["tingkat"] == FATAL]

    def hitung(self):
        out = {FATAL: 0, PERBAIKI: 0, PERINGATAN: 0, INFO: 0}
        for t in self.daftar:
            out[t["tingkat"]] += 1
        return out

    def teks(self):
        return "\n".join("[%s] %s%s%s" % (t["tingkat"], ("%s: " % t["berkas"]) if t["berkas"] else "", t["pesan"],
                                          (" -> " + t["saran"]) if t["saran"] else "") for t in self.daftar)


def _rapikan(s):
    s = re.sub(r"[\s_]+", " ", (s or "").replace(" ", " ")).strip()
    for pola, ganti in GANTI:
        s = re.sub(pola, ganti, s, flags=re.I)
    return s


_KANON_UP = {k.upper(): k for k in KANON}


def kanon_folder(nama, temuan=None, berkas=""):
    """Nama folder -> nama template. Mengembalikan nama asli bila bukan kosakata template."""
    if not nama:
        return nama
    if nama in KANON:
        return nama
    r = _rapikan(nama)
    up = r.upper()
    hasil = None
    if up in _KANON_UP:
        hasil = _KANON_UP[up]
    else:
        m = re.match(r"^(NEW|EKSISTING)?\s*CABLE\s*(\d{2,3})\s*(?:C|CORE|D|F)?\s*(UG)?$", up)
        m2 = re.match(r"^(?:COLLO\s*POLE|COLLO\s*TIANG|COLO\s*POLE)\s*(\d{2,3})\s*(?:C|CORE)?$", up)
        m3 = re.match(r"^(NEW|EKSISTING)\s*(CLOSURE|OTB)\s*(\d{2,3})$", up)
        if m:
            c = koreksi_core(m.group(2), temuan, berkas, " (folder '%s')" % nama)
            if c:
                hasil = "%s Cable %dC%s" % ("New" if (m.group(1) or "NEW") == "NEW" else "Eksisting", c,
                                           " UG" if m.group(3) else "")
        elif m2 and koreksi_core(m2.group(1)):
            hasil = "Colo Pole %dC" % koreksi_core(m2.group(1), temuan, berkas, " (folder '%s')" % nama)
        elif m3 and koreksi_core(m3.group(3)):
            hasil = "%s %s %d" % (m3.group(1).title(), m3.group(2).title() if m3.group(2) != "OTB" else "OTB",
                                  koreksi_core(m3.group(3), temuan, berkas, " (folder '%s')" % nama))
        elif len(up) >= 5 and not re.search(r"\d", up):
            hasil = _mirip_unik(up, list(_KANON_UP))
            hasil = _KANON_UP[hasil] if hasil else None
    if hasil and hasil != nama and temuan is not None and _beda_bermakna(hasil, nama):
        temuan.tambah(PERBAIKI, "Konsistensi konseptual", "folder '%s' dibaca sebagai '%s'" % (nama, hasil), berkas,
                      "rapikan nama folder agar sama dengan template compile")
    return hasil or nama


def _mirip_unik(teks, kandidat, cutoff=0.8, selisih=0.05):
    """Kandidat termirip HANYA bila skornya >= cutoff DAN unggul jelas atas kandidat kedua (bukan seri).
    Hanya untuk teks tanpa angka: nilai berangka (kode FDT, ukuran kabel, splitter) tidak pernah ditebak secara fuzzy,
    karena 'FDT-01' vs 'FDT-07' atau '1:6' vs '1:16' bermiripan tinggi padahal beda makna (difflib ratio 0,83-0,86)."""
    skor = sorted(((difflib.SequenceMatcher(None, teks, k).ratio(), k) for k in kandidat), reverse=True)
    if not skor or skor[0][0] < cutoff:
        return None
    if len(skor) > 1 and skor[0][0] - skor[1][0] < selisih:
        return None
    return skor[0][1]


def _beda_bermakna(a, b):
    return re.sub(r"[\s_]+", " ", a).strip().upper() != re.sub(r"[\s_]+", " ", b).strip().upper()


# ----------------------------------------------------------------------------- traksi & feeder
RX_TRAKSI_LONGGAR = re.compile(
    r"^\s*F\s*[-_ ]?\s*(\d{1,2})\s*[-_ ]\s*T\s*[-_ ]?\s*(\d{1,2}(?:\s*-\s*T?\d{1,2})?)\s*[-_ ]*(\d{6,12})?\s*[-_ ]*"
    r"(A\s*P\s*D\s*[-_ ]*\w+\s*[-_ ]*K\s*M\s*Z)?\s*[-_ ]*(.*)$", re.I)
RX_FEEDER_LONGGAR = re.compile(r"^\s*F[e]{1,3}d{1,2}e?r\s*[-_ ]?\s*(\d{1,2})\s*$", re.I)


def baca_traksi(nama, temuan=None, berkas=""):
    """'F2_T3_2547740314_APD Feeder KMZ_area_tgl' dan variasinya -> dict(feeder, t, cluster, area) atau None."""
    m = RX_TRAKSI_LONGGAR.match(nama or "")
    if not m:
        return None
    kmz = m.group(4) or ""
    if not kmz and not m.group(3):
        return None                      # 'F2 T3' tanpa ID/APD terlalu umum untuk dianggap traksi
    kmz_up = re.sub(r"[\s_\-]+", " ", kmz.upper())
    if kmz and kmz_up not in ("APD FEEDER KMZ", "APD DISTRIBUSI KMZ"):
        b1 = _mirip_unik(kmz_up, ["APD FEEDER KMZ", "APD DISTRIBUSI KMZ"], cutoff=0.75)
        if not b1:
            return None
        best = [b1]
        if temuan is not None:
            temuan.tambah(PERBAIKI, "Konsistensi konseptual", "nama traksi '%s': '%s' dibaca '%s'" % (nama, kmz, best[0]),
                          berkas)
    t = re.sub(r"\s+", "", m.group(2)).upper().replace("T", "")
    rest = (m.group(5) or "").strip(" _-")
    tgl = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", rest)
    area = rest[:tgl.start()].strip(" _-") if tgl else rest
    baku = re.match(r"^F\d+_T[\d\-T]+_\d{6,12}_APD (Feeder|Distribusi) KMZ_", nama or "")
    if not baku and temuan is not None:
        temuan.tambah(PERBAIKI, "Konsistensi konseptual", "nama traksi tidak baku '%s' dikenali sebagai F%s_T%s"
                      % (nama, m.group(1), t), berkas, "format baku: F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<dd-mm-yyyy>")
    return {"feeder": int(m.group(1)), "t": t, "cluster": m.group(3), "area": area,
            "tanggal": tgl.group(0) if tgl else None}


def baca_feeder(nama, temuan=None, berkas=""):
    m = RX_FEEDER_LONGGAR.match(nama or "")
    if not m:
        return None
    if temuan is not None and not re.match(r"^Feeder \d+$", nama):
        temuan.tambah(PERBAIKI, "Konsistensi konseptual", "folder '%s' dibaca sebagai 'Feeder %s'" % (nama, m.group(1)),
                      berkas)
    return m.group(1)


# ----------------------------------------------------------------------------- nilai
def koreksi_core(s, temuan=None, berkas="", konteks=""):
    """'96', '96c', '96 Core', '96D' -> 96. Angka tak baku: digit tertukar ('69' -> 96) dikoreksi DENGAN catatan;
    selain itu None (tidak ditebak)."""
    m = re.search(r"(\d{1,3})", str(s or ""))
    if not m:
        return None
    v = int(m.group(1))
    if v in CORE:
        return v
    d = m.group(1)
    if len(d) >= 2:
        cocok = [c for c in CORE if sorted(str(c)) == sorted(d)]
        if len(cocok) == 1:          # hanya bila satu-satunya ukuran baku dengan digit yang sama
            if temuan is not None:
                temuan.tambah(PERINGATAN, "Konsistensi domain", "ukuran kabel '%s'%s di luar ukuran baku; dibaca %dC "
                              "(susunan digit sama) - KOREKSI BERISIKO" % (s, konteks, cocok[0]), berkas,
                              "mohon konfirmasi ukuran kabel dan perbaiki nama folder")
            return cocok[0]
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Konsistensi domain", "ukuran kabel '%s'%s tidak dikenal (baku: %s)" % (
            s, konteks, ", ".join(map(str, CORE))), berkas, "kapasitas kabel ini dianggap belum terverifikasi")
    return None


RX_FDT_BAKU = re.compile(r"^[A-Z]{2,4}\d-[A-Z]{2,4}\d{2}-H\d{2}$")


def koreksi_fdt(kode, temuan=None, berkas=""):
    """'bit1 stu01 h2' / 'BIT1_STU01_H02' / 'BIT1-STU01-H2' -> 'BIT1-STU01-H02'."""
    k0 = (kode or "").strip()
    k = re.sub(r"[\s_.]+", "-", k0.upper())
    k = re.sub(r"-+", "-", k).strip("-")
    m = re.match(r"^([A-Z]{2,4})(\d)-?([A-Z]{2,4})(\d{1,2})-?H(\d{1,2})$", k)
    if m:
        k = "%s%s-%s%02d-H%02d" % (m.group(1), m.group(2), m.group(3), int(m.group(4)), int(m.group(5)))
    if k != k0 and RX_FDT_BAKU.match(k) and temuan is not None:
        temuan.tambah(PERBAIKI, "Konsistensi domain", "kode FDT '%s' dibaca '%s'" % (k0, k), berkas)
    return k if RX_FDT_BAKU.match(k) else k0


RX_SPLIT_LONGGAR = re.compile(r"(\d{1,2})\s*[xX*×]\s*1\s*[xX*:×/]\s*(\d{1,2})")
RX_SPLIT_BALIK = re.compile(r"1\s*[:/]\s*(\d{1,2})\s*[xX*×]\s*(\d{1,2})")


def koreksi_splitter(s, temuan=None, berkas="", konteks=""):
    """'12x1x4', '12 X 1 : 4', '12*1/4', '1:4 x 12' -> (12, 4)."""
    s = str(s or "")
    m = RX_SPLIT_LONGGAR.search(s)
    n = r = None
    if m:
        n, r = int(m.group(1)), int(m.group(2))
    else:
        m = RX_SPLIT_BALIK.search(s)
        if m:
            n, r = int(m.group(2)), int(m.group(1))
    if n is None:
        if s.strip() and s.strip() not in ("-", "0") and temuan is not None:
            temuan.tambah(PERINGATAN, "Konsistensi domain", "SPLITTERS '%s'%s tidak terbaca" % (s, konteks), berkas,
                          "isi dengan format 12x1x4")
        return None, None
    if not re.match(r"^\d+x1x\d+$", s.strip()) and temuan is not None:
        temuan.tambah(PERBAIKI, "Konsistensi domain", "SPLITTERS '%s'%s dibaca %dx1x%d" % (s, konteks, n, r), berkas)
    if r not in (2, 4, 8, 16, 32) and temuan is not None:
        temuan.tambah(PERINGATAN, "Konsistensi domain", "rasio splitter 1:%d%s tidak lazim" % (r, konteks), berkas)
    return n, r


def angka_longgar(s, temuan=None, berkas="", konteks=""):
    """'24', '24 core', '24,0', ' 24 ' -> 24.0; '-', '', 'N/A' -> None (tidak ditebak)."""
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in ("-", "N/A", "NA", "NULL", "NONE", "#N/A"):
        return None
    try:
        v = float(t.replace(",", "."))
    except ValueError:
        v = None                    # bukan angka murni: coba bentuk '24 core' di bawah
    if v is not None:
        return v if v >= 0 else None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:core|c|cores|fo)?\s*$", t, re.I)
    if m:
        if temuan is not None:
            temuan.tambah(PERBAIKI, "Konsistensi domain", "nilai '%s'%s dibaca %s" % (t, konteks, m.group(1)), berkas)
        return float(m.group(1).replace(",", "."))
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Konsistensi domain", "nilai '%s'%s bukan angka" % (t, konteks), berkas)
    return None


def atribut(attrs, nama, temuan=None, berkas="", konteks=""):
    """Ambil atribut walau nama kolomnya bervariasi: 'SPLITTERS', 'Splitter ', 'splitters', 'PREMISE'."""
    if nama in attrs:
        return attrs[nama]
    kunci = re.sub(r"[^A-Z0-9]", "", nama.upper()).rstrip("S")
    for k, v in attrs.items():
        if re.sub(r"[^A-Z0-9]", "", (k or "").upper()).rstrip("S") == kunci:
            if temuan is not None:
                temuan.tambah(PERBAIKI, "Konsistensi konseptual", "atribut '%s'%s dibaca sebagai '%s'" % (k, konteks, nama),
                              berkas)
            return v
    return None


# ----------------------------------------------------------------------------- koordinat
INDONESIA = (94.0, -11.5, 141.5, 6.5)


def koreksi_titik(p, temuan=None, berkas="", konteks=""):
    """-> (lon, lat) terkoreksi atau None bila tidak dapat dipakai. Lat/lon tertukar dikoreksi dengan catatan."""
    x, y = p[0], p[1]
    if INDONESIA[0] <= x <= INDONESIA[2] and INDONESIA[1] <= y <= INDONESIA[3]:
        return (x, y)
    if INDONESIA[0] <= y <= INDONESIA[2] and INDONESIA[1] <= x <= INDONESIA[3]:
        if temuan is not None:
            temuan.tambah(PERBAIKI, "Akurasi posisi absolut", "koordinat%s tertukar (lat,lon; KML wajib lon,lat) dan "
                          "dibalik" % konteks, berkas, "perbaiki urutan koordinat di sumbernya")
        return (y, x)
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Akurasi posisi absolut", "koordinat%s (%.5f, %.5f) di luar Indonesia: objek diabaikan"
                      % (konteks, x, y), berkas, "periksa koordinat")
    return None


def koreksi_garis(ll, temuan=None, berkas="", konteks=""):
    out = []
    for p in ll:
        q = koreksi_titik(p, temuan, berkas, konteks)
        if q is not None and (not out or out[-1] != q):
            out.append(q)
    return out if len(out) >= 2 else None


# ----------------------------------------------------------------------------- pra-cek berkas
WAJIB_KET = {
    "JARINGAN": "KMZ Compile APD Feeder dan/atau KMZ inventaris kabel nasional (sumber feeder eksisting, slide 2)",
    "TARGET": "titik FDT target (KMZ Distribusi / Design Lite / cluster) atau klik FDT di peta",
}


def pra_cek_berkas(paths, temuan):
    """Cek keberadaan & keterbacaan berkas sebelum peran dikenali. -> daftar path yang boleh lanjut."""
    import hashlib
    ok, sidik = [], {}
    if not paths:
        temuan.tambah(FATAL, "Kelengkapan (omisi)", "tidak ada berkas KMZ/KML yang dipilih", "",
                      "pilih folder berisi KMZ atau pilih berkasnya satu per satu")
        return ok
    for p in paths:
        nama = os.path.basename(p)
        if not os.path.exists(p):
            saran = "periksa lokasi/nama berkas (mungkin dipindah, diganti nama, atau typo di jalur)"
            d = os.path.dirname(p)
            if os.path.isdir(d):
                ada = [f for f in os.listdir(d) if f.lower().endswith((".kmz", ".kml"))]
                mirip = difflib.get_close_matches(nama, ada, n=1, cutoff=0.6)
                if mirip:
                    saran = "mungkin maksud Anda '%s'?" % mirip[0]
            temuan.tambah(FATAL, "Kelengkapan (omisi)", "berkas tidak ditemukan: %s" % p, nama, saran)
            continue
        if os.path.isdir(p):
            continue
        if not nama.lower().endswith((".kmz", ".kml")):
            temuan.tambah(PERINGATAN, "Kelengkapan", "bukan KMZ/KML, dilewati", nama)
            continue
        if os.path.getsize(p) == 0:
            temuan.tambah(FATAL, "Konsistensi format", "berkas kosong (0 byte)", nama, "unduh/ekspor ulang berkas")
            continue
        try:
            with open(p, "rb") as fh:
                h = hashlib.sha256(fh.read(8 << 20)).hexdigest() + str(os.path.getsize(p))
        except OSError as e:
            temuan.tambah(FATAL, "Konsistensi format", "berkas tidak dapat dibuka: %s" % e, nama,
                          "tutup berkas di aplikasi lain (Google Earth/Excel) atau periksa izin akses")
            continue
        if h in sidik:
            temuan.tambah(INFO, "Kelengkapan", "isi sama dengan %s, dilewati (duplikat)" % sidik[h], nama)
            continue
        sidik[h] = nama
        ok.append(p)
    return ok


def versi_ganda(peran, baca_traksi_berkas, temuan):
    """Beberapa versi Compile APD Feeder kota yang sama (traksi >= 50 % sama): pakai yang terbaru (waktu ubah berkas),
    yang lain dilewati dengan catatan - mencegah kapasitas tube terhitung ganda."""
    comp = list(peran.get("COMPILE", []))
    if len(comp) < 2:
        return
    tr = {p: set(baca_traksi_berkas(p)) for p in comp}
    buang = set()
    for i, a in enumerate(comp):
        for b in comp[i + 1:]:
            if a in buang or b in buang or not tr[a] or not tr[b]:
                continue
            sama = len(tr[a] & tr[b]) / float(min(len(tr[a]), len(tr[b])))
            if sama >= 0.5:
                lama, baru = sorted((a, b), key=os.path.getmtime)
                buang.add(lama)
                temuan.tambah(PERBAIKI, "Kelengkapan (komisi)", "dua versi compile untuk area yang sama (%d %% traksi sama): "
                              "dipakai %s, dilewati %s" % (int(sama * 100), os.path.basename(baru),
                                                          os.path.basename(lama)), "",
                              "simpan hanya versi terbaru di folder data")
    peran["COMPILE"] = [p for p in comp if p not in buang]
    peran.setdefault("LAIN_VERSI", []).extend(sorted(buang))


def cek_peran(peran, temuan, ada_target_manual=False):
    """Peran wajib: minimal satu sumber jaringan; target FDT (kecuali mode klik peta)."""
    if not peran.get("COMPILE") and not peran.get("NASIONAL"):
        temuan.tambah(FATAL, "Kelengkapan (omisi)", "sumber feeder eksisting tidak ada", "",
                      "tambahkan " + WAJIB_KET["JARINGAN"])
    if not peran.get("TARGET") and not ada_target_manual:
        temuan.tambah(FATAL, "Kelengkapan (omisi)", "titik FDT target tidak ditemukan di berkas mana pun", "",
                      "tambahkan " + WAJIB_KET["TARGET"])
    if not peran.get("NASIONAL"):
        temuan.tambah(PERINGATAN, "Kelengkapan", "KMZ inventaris kabel nasional tidak dipilih: kabel FTTH eksisting di luar "
                      "compile tidak ikut dianalisis", "", "tambahkan KMZ kabel nasional pulau yang sesuai")
    for p in peran.get("LAIN", []):
        temuan.tambah(PERINGATAN, "Kelengkapan (komisi)", "peran berkas tidak dikenali (bukan kabel nasional/Compile/FDT/POP), "
                      "dilewati", os.path.basename(p), "periksa apakah berkas ini salah pilih")
