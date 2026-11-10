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

from .teks import T

FATAL, PERBAIKI, PERINGATAN, INFO = "FATAL", "DIKOREKSI", "PERINGATAN", "INFO"
NAMA_TINGKAT = {FATAL: "TIDAK BISA JALAN", PERBAIKI: "DIKOREKSI OTOMATIS", PERINGATAN: "PERLU DICEK", INFO: "CATATAN"}

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
        return "\n".join("[%s] %s%s%s" % (NAMA_TINGKAT.get(t["tingkat"], t["tingkat"]), ("%s: " % t["berkas"]) if t["berkas"] else "", t["pesan"],
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
        temuan.tambah(PERBAIKI, "Nama folder", T("folder '%s' dibaca sebagai '%s'", "folder '%s' read as '%s'") % (
            nama, hasil), berkas, T("samakan nama folder dengan contoh compile", "rename the folder to match the "
                                    "compilation layout"))
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
            temuan.tambah(PERBAIKI, "Nama folder", T("nama traksi '%s': '%s' dibaca '%s'",
                                                     "route folder '%s': '%s' read as '%s'") % (nama, kmz, best[0]), berkas)
    t = re.sub(r"\s+", "", m.group(2)).upper().replace("T", "")
    rest = (m.group(5) or "").strip(" _-")
    rest = re.sub(r"^APD\s*(Feeder|Distribusi|Distribution)\s*[-_ ]*", "", rest, flags=re.I)   # gaya 'APD Feeder_<area>'
    tgl = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", rest)
    area = rest[:tgl.start()].strip(" _-") if tgl else rest
    baku = re.match(r"^F\d+_T[\d\-T,]+_\d{6,12}_APD (Feeder|Distribusi)( KMZ)?_", nama or "")
    if not baku and temuan is not None:
        temuan.tambah(PERBAIKI, "Nama folder", T("nama traksi '%s' tidak mengikuti pola baku; dikenali sebagai F%s_T%s",
                                                 "route folder '%s' does not follow the usual pattern; recognised as "
                                                 "F%s_T%s") % (nama, m.group(1), t), berkas,
                      T("pola baku: F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<dd-mm-yyyy>",
                        "usual pattern: F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<dd-mm-yyyy>"))
    return {"feeder": int(m.group(1)), "t": t, "cluster": m.group(3), "area": area,
            "tanggal": tgl.group(0) if tgl else None}


def baca_feeder(nama, temuan=None, berkas=""):
    m = RX_FEEDER_LONGGAR.match(nama or "")
    if not m:
        return None
    if temuan is not None and not re.match(r"^Feeder \d+$", nama):
        temuan.tambah(PERBAIKI, "Nama folder", T("folder '%s' dibaca sebagai 'Feeder %s'", "folder '%s' read as "
                                                 "'Feeder %s'") % (nama, m.group(1)), berkas)
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
                temuan.tambah(PERINGATAN, "Isi data", T("ukuran kabel '%s'%s bukan ukuran baku; dibaca %d core karena "
                                                        "angkanya sama tetapi urutannya tertukar - mohon dicek",
                                                        "cable size '%s'%s is not a standard size; read as %d fibres "
                                                        "because the digits match in a different order - please check")
                              % (s, konteks, cocok[0]), berkas,
                              T("pastikan ukuran kabel yang benar dan perbaiki nama folder",
                                "confirm the real cable size and fix the folder name"))
            return cocok[0]
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Isi data", T("ukuran kabel '%s'%s tidak dikenal (ukuran baku: %s core)",
                                                "cable size '%s'%s not recognised (standard sizes: %s fibres)") % (
            s, konteks, ", ".join(map(str, CORE))), berkas,
            T("sisa tube kabel ini dianggap belum pasti", "the free tubes of this cable are treated as unconfirmed"))
    return None


def nomor_tube(teks):
    """'T1, T2,T3' / '7-8' / 'T1-T2' / '4' -> {nomor T}. Rentang diurai; angka di luar 1..48 diabaikan."""
    out = set()
    for a, b in re.findall(r"(\d{1,2})(?:\s*-\s*T?(\d{1,2}))?", str(teks or "").upper()):
        a = int(a)
        b = int(b) if b else a
        if 1 <= a <= b <= 48:
            out.update(range(a, b + 1))
    return out


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
        temuan.tambah(PERBAIKI, "Isi data", T("kode FDT '%s' dibaca '%s'", "FDT code '%s' read as '%s'") % (k0, k),
                      berkas)
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
            temuan.tambah(PERINGATAN, "Isi data", T("jumlah splitter '%s'%s tidak terbaca",
                                                    "splitter count '%s'%s could not be read") % (s, konteks), berkas,
                          T("tulis dengan format seperti 12x1x4", "write it like 12x1x4"))
        return None, None
    if not re.match(r"^\d+x1x\d+$", s.strip()) and temuan is not None:
        temuan.tambah(PERBAIKI, "Isi data", T("jumlah splitter '%s'%s dibaca %dx1x%d", "splitter count '%s'%s read as "
                                              "%dx1x%d") % (s, konteks, n, r), berkas)
    if r not in (2, 4, 8, 16, 32) and temuan is not None:
        temuan.tambah(PERINGATAN, "Isi data", T("splitter 1:%d%s tidak lazim", "splitter 1:%d%s is unusual") % (
            r, konteks), berkas, T("periksa nilai splitter", "check the splitter value"))
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
            temuan.tambah(PERBAIKI, "Isi data", T("nilai '%s'%s dibaca %s", "value '%s'%s read as %s") % (
                t, konteks, m.group(1)), berkas)
        return float(m.group(1).replace(",", "."))
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Isi data", T("nilai '%s'%s bukan angka", "value '%s'%s is not a number") % (
            t, konteks), berkas, T("isi dengan angka", "enter a number"))
    return None


def atribut(attrs, nama, temuan=None, berkas="", konteks=""):
    """Ambil atribut walau nama kolomnya bervariasi: 'SPLITTERS', 'Splitter ', 'splitters', 'PREMISE'."""
    if nama in attrs:
        return attrs[nama]
    kunci = re.sub(r"[^A-Z0-9]", "", nama.upper()).rstrip("S")
    for k, v in attrs.items():
        if re.sub(r"[^A-Z0-9]", "", (k or "").upper()).rstrip("S") == kunci:
            if temuan is not None:
                temuan.tambah(PERBAIKI, "Isi data", T("kolom '%s'%s dibaca sebagai '%s'", "field '%s'%s read as '%s'") % (
                    k, konteks, nama), berkas)
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
            temuan.tambah(PERBAIKI, "Koordinat", T("koordinat%s tertukar (lintang dan bujur terbalik) dan sudah dibalik",
                                                   "coordinates%s swapped (latitude and longitude reversed) and turned "
                                                   "back") % konteks, berkas,
                          T("perbaiki urutan koordinat di berkas aslinya", "fix the coordinate order in the source file"))
        return (y, x)
    if temuan is not None:
        temuan.tambah(PERINGATAN, "Koordinat", T("koordinat%s (%.5f, %.5f) di luar wilayah Indonesia: objek ini tidak "
                                                 "dipakai", "coordinates%s (%.5f, %.5f) are outside Indonesia: this "
                                                 "object is skipped") % (konteks, x, y), berkas,
                      T("periksa koordinatnya", "check its coordinates"))
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
    "JARINGAN": T("KMZ compile desain feeder dan/atau KMZ inventaris kabel (sumber feeder yang sudah ada)",
                  "the feeder design compilation KMZ and/or the cable inventory KMZ (where existing feeders come from)"),
    "TARGET": T("KMZ berisi titik FDT yang akan dirancang (KMZ distribusi atau desain), atau klik lokasi FDT di peta",
                "a KMZ with the FDT points to design (distribution or design KMZ), or click the FDT on the map"),
}


def pra_cek_berkas(paths, temuan):
    """Cek keberadaan & keterbacaan berkas sebelum peran dikenali. -> daftar path yang boleh lanjut."""
    import hashlib
    ok, sidik = [], {}
    if not paths:
        temuan.tambah(FATAL, "Kelengkapan", T("belum ada berkas KMZ/KML yang dipilih", "no KMZ/KML file chosen yet"), "",
                      T("pilih folder berisi KMZ, atau pilih berkasnya satu per satu",
                        "choose the folder with your KMZ files, or pick the files one by one"))
        return ok
    for p in paths:
        nama = os.path.basename(p)
        if not os.path.exists(p):
            saran = T("periksa lokasi dan nama berkas (mungkin dipindah, diganti nama, atau salah ketik)",
                      "check where the file is and its name (it may have been moved, renamed or mistyped)")
            d = os.path.dirname(p)
            if os.path.isdir(d):
                ada = [f for f in os.listdir(d) if f.lower().endswith((".kmz", ".kml"))]
                mirip = difflib.get_close_matches(nama, ada, n=1, cutoff=0.6)
                if mirip:
                    saran = T("mungkin maksud Anda '%s'?", "did you mean '%s'?") % mirip[0]
            temuan.tambah(FATAL, "Kelengkapan", T("berkas tidak ditemukan: %s", "file not found: %s") % p, nama, saran)
            continue
        if os.path.isdir(p):
            continue
        if os.path.getsize(p) == 0:
            temuan.tambah(FATAL, "Berkas", T("berkas kosong (0 byte)", "the file is empty (0 bytes)"), nama,
                          T("unduh atau ekspor ulang berkasnya", "download or export the file again"))
            continue
        try:
            with open(p, "rb") as fh:
                h = hashlib.sha256(fh.read(8 << 20)).hexdigest() + str(os.path.getsize(p))
        except OSError as e:
            temuan.tambah(FATAL, "Berkas", T("berkas tidak bisa dibuka: %s", "the file cannot be opened: %s") % e, nama,
                          T("tutup berkas di aplikasi lain (mis. Google Earth) atau periksa izin aksesnya",
                            "close the file in other programs (e.g. Google Earth) or check its permissions"))
            continue
        from . import baca
        if baca.jenis(p) is None and baca.rusak(p):
            temuan.tambah(FATAL, "Berkas", T("berkas rusak atau tidak utuh, isinya tidak bisa dibaca",
                                             "the file is damaged or incomplete; its content cannot be read"), nama,
                          T("unduh atau ekspor ulang berkasnya, lalu pilih lagi (atau hapus dari daftar bila tidak dipakai)",
                            "download or export the file again and pick it again (or remove it from the list if not needed)"))
            continue
        if baca.jenis(p) is None:
            temuan.tambah(PERINGATAN, "Kelengkapan", T("bukan data peta yang dikenali (KMZ, KML, GeoJSON, CSV/Excel "
                                                       "berkoordinat, Shapefile, GeoPackage), dilewati",
                                                       "not a recognised map data file (KMZ, KML, GeoJSON, CSV/Excel "
                                                       "with coordinates, Shapefile, GeoPackage), skipped"), nama)
            continue
        if h in sidik:
            temuan.tambah(INFO, "Kelengkapan", T("isinya sama dengan %s, dilewati (duplikat)",
                                                 "same content as %s, skipped (duplicate)") % sidik[h], nama)
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
                temuan.tambah(PERBAIKI, "Kelengkapan", T("ada dua versi compile untuk area yang sama (%d%% traksi sama): "
                                                         "dipakai yang terbaru, %s; dilewati %s",
                                                         "two versions of the compilation for the same area (%d%% of "
                                                         "routes identical): the newest, %s, is used; %s is skipped")
                              % (int(sama * 100), os.path.basename(baru), os.path.basename(lama)), "",
                              T("simpan hanya versi terbaru di folder data", "keep only the newest version in the "
                                "data folder"))
    peran["COMPILE"] = [p for p in comp if p not in buang]
    peran.setdefault("LAIN_VERSI", []).extend(sorted(buang))


def cek_peran(peran, temuan, ada_target_manual=False):
    """Peran wajib: minimal satu sumber jaringan; target FDT (kecuali mode klik peta)."""
    if not peran.get("COMPILE") and not peran.get("NASIONAL"):
        temuan.tambah(FATAL, "Kelengkapan", T("belum ada data feeder yang sudah ada", "no data about existing feeders"),
                      "", T("tambahkan ", "add ") + WAJIB_KET["JARINGAN"])
    if not peran.get("TARGET") and not ada_target_manual:
        temuan.tambah(FATAL, "Kelengkapan", T("titik FDT yang akan dirancang tidak ditemukan di berkas mana pun",
                                              "no FDT points to design were found in any file"), "",
                      T("tambahkan ", "add ") + WAJIB_KET["TARGET"])
    if not peran.get("NASIONAL"):
        temuan.tambah(PERINGATAN, "Kelengkapan", T("KMZ inventaris kabel tidak dipilih: feeder yang sudah ada di luar "
                                                   "compile tidak ikut diperiksa",
                                                   "no cable inventory KMZ chosen: existing feeders outside the "
                                                   "compilation are not checked"), "",
                      T("tambahkan KMZ inventaris kabel untuk wilayah ini", "add the cable inventory KMZ for this "
                        "region"))
    for p in peran.get("LAIN", []):
        temuan.tambah(PERINGATAN, "Kelengkapan", T("jenis isi berkas tidak dikenali (bukan inventaris kabel, compile, "
                                                   "titik FDT atau daftar POP), dilewati",
                                                   "the file content is not recognised (not a cable inventory, "
                                                   "compilation, FDT points or POP list), skipped"),
                      os.path.basename(p), T("periksa apakah berkas ini salah pilih; jenisnya bisa dipilih di kolom "
                                             "'Read as'", "check whether this file was chosen by mistake; you can set "
                                             "its type in the 'Read as' column"))
