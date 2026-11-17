# -*- coding: utf-8 -*-
# Tembuku - penulis KMZ format Compile APD Feeder.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""KMZ hasil mengikuti template Compile APD Feeder organisasi (hierarki folder contoh Bitung/Tomohon 2026) agar dapat langsung
ditempel ke compile (slide 7/11): POP / Feeder N / F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<tgl> / Cable, Tiang, Hanger,
Closure, OTB, FDT, OLT, Keterangan Infra. Warna kabel = slide 16 'Format Warna Kabel' (KML aabbggrr).
KMZ: doc.kml entri pertama, DEFLATE, UTF-8 tanpa BOM; semua teks di-escape (tidak ada HTML/JS dari input)."""
import datetime
import os
import re
import zipfile

from . import geo, ikon, mesin, osm


CORE = (12, 24, 48, 96, 144, 288)


def escape(s):
    """Escape teks XML (pengganti xml.sax.saxutils.escape tanpa impor modul XML yang diblokir pemindai)."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# Warna kabel = style Template APD KMZ FTTH Feeder (KML aabbggrr), dicocokkan dengan compile nyata:
# 12C ff55ff, 24C ffaa00, 48C aa5500, 96C ffff00 (RGB); 144C memakai nilai KML 'ffff0000' seperti di template dan
# compile; 288C tidak punya warna eksplisit di template (tampil putih bawaan) - tidak dibuat warna baru.
WARNA_CORE = {12: "ffff55ff", 24: "ff00aaff", 48: "ff0055aa", 96: "ff00ffff", 144: "ffff0000", 288: "ffffffff"}
LEBAR_KABEL = 3
# Susunan folder Feeder persis template (nama & urutan); dipakai penulis dan pemeriksa hasil.
TEMPLATE_FEEDER = (
    "Cable", "Cable/New Cable Aerial/Udara") + tuple("Cable/New Cable Aerial/Udara/New Cable %dC" % c for c in CORE) + (
    "Cable/Collo Cable", "Cable/UG Utilities", "Cable/UG Utilities/Manhole", "Cable/UG Utilities/Handhole",
    "Tiang 6 Meter", "Tiang 6 Meter/New Tiang 6 Meter", "Tiang 6 Meter/Eksisting Tiang 6 Meter",
    "Tiang 7 Meter", "Tiang 7 Meter/New Tiang 7 Meter", "Tiang 7 Meter/Eksisting Tiang 7 Meter",
    "Tiang 9 Meter", "Tiang 9 Meter/New Tiang 9 Meter", "Tiang 9 Meter/Eksisting Tiang 9 Meter",
    "Hanger", "Hanger/New Hanger", "Hanger/Eksisting Hanger",
    "Closure", "Closure/New Closure") + tuple("Closure/New Closure/New Closure %d" % c for c in CORE) + (
    "Closure/Eksisting Closure", "OTB", "OTB/New OTB") + tuple("OTB/New OTB/New OTB %d" % c for c in CORE) + (
    "OTB/Eksisting OTB", "FDT", "FDT/Eksisting FDT", "FDT/New FDT", "OLT", "Keterangan Infra",
    "Keterangan Infra/New Cable Galian") + tuple("Keterangan Infra/New Cable Galian/New Cable %dC UG" % c for c in CORE) + (
    "Keterangan Infra/Collo Tiang",) + tuple("Keterangan Infra/Collo Tiang/Colo Pole %dC" % c for c in CORE)
FOLDER_NEW_INFRA = "Keterangan Infra/New Infra"     # di luar template, tetapi dipakai desainer (19 dari 46 traksi)
# Ikon milik pengguna (opsional, dari folder 'ikon'; tidak ikut di plugin). Dikenali dari kata di nama berkasnya, apa pun
# imbuhannya, lalu ditanam ke KMZ dengan nama netral: jenis -> (pola nama berkas, nama di KMZ, skala template).
IKON_LOKAL = {"fdt": (r"^FDT\b", "fdt_lokal.png", 0.5), "pop": (r"^OLT\b|^POP\b", "olt_lokal.png", 1.2),
              "closure": (r"^(CLOSURE|CL)[ _-]*96\b", "closure_96_lokal.png", 0.8),
              "closure_kecil": (r"^(CLOSURE|CL)[ _-]*48\b", "closure_48_lokal.png", 0.8),
              "closure_288": (r"^(CLOSURE|CL)[ _-]*288\b", "closure_288_lokal.png", 0.8),
              "otb": (r"^OTB\b", "otb_lokal.png", 0.8), "slack": (r"^(SPARE|SLACK)\b", "slack_lokal.png", 0.8),
              "tiang6": (r"^6M\b", "tiang6_lokal.png", 0.5),
              # template APD: New Tiang 9m = ICONFTTH-9m.png; pola dicoba berurutan (yang pertama cocok dipakai)
              "tiang7": ((r"^ICONFTTH[ -]*7M\b", r"^7M\b", r"^POLE 7\b"), "tiang7_lokal.png", 0.5),
              "tiang9": ((r"^ICONFTTH[ -]*9M\b", r"^9M\b", r"^POLE 9\b"), "tiang9_lokal.png", 0.5)}


def pilih_ikon(lokal):
    """{nama berkas: bytes} -> {jenis: (nama netral di KMZ, skala, bytes)} untuk ikon pengguna yang dikenali."""
    import re
    out = {}
    for jenis, (pola, netral, skala) in IKON_LOKAL.items():
        for p in (pola if isinstance(pola, tuple) else (pola,)):
            nama = next((n for n in sorted(lokal or {}) if re.search(p, os.path.splitext(n)[0].upper().replace("_", " "))),
                        None)
            if nama:
                # nama berkas ikon asli pengguna dipakai di KMZ (seperti hasil desainer: files/Closure 96.png)
                asli = re.sub(r"[^\w .()-]", "_", os.path.basename(nama)) or netral
                out[jenis] = (asli, skala, lokal[nama])
                break
    return out


SKALA = {"fdt": 0.5, "pop": 1.2, "closure": 0.8, "otb": 0.8, "slack": 0.8, "tap": 1.1, "tiang": 0.5}
WARNA_INFRA = {"TIANG_NASIONAL": "b3ffff00", "TIANG_COMPILE": "b3ffaa55", "NEW_INFRA": "b300ff55",
               "GARIS_BANTU": "ff0000ff", "COLO_CABLE": "b37fffff"}
IKON = {k: "files/%s.png" % k for k in ikon.BENTUK}
WARNA_IKON = {"slack": "ff00ffff", "closure": "ff00aaff", "otb": "ffff8800", "fdt": "ff00ffff",
              "pop": "ff0000ff", "tap": "ffff00ff", "tiang": "ff00ff55"}
# Ikon standar Google Earth menurut template APD (Resume Template APD Feeder 29-12-2025): New Hanger 'forbidden' skala
# 0,8 (juga dipakai 321 dari 321 titik hanger di 4 compile) dan OLT 'homegardenbusiness' skala 1,2.
IKON_APD = {"hanger": ("http://maps.google.com/mapfiles/kml/shapes/forbidden.png", 0.8),
            "olt": ("http://maps.google.com/mapfiles/kml/shapes/homegardenbusiness.png", 1.2)}
WARNA_EKSISTING = "ff00ffff"            # objek eksisting di compile diberi warna ikon ini (closure, FDT)


def _c(ll):
    return " ".join("%.7f,%.7f,0" % (p[0], p[1]) for p in ll)


def _c_persis(p):
    """Koordinat titik apa adanya (presisi penuh): lokasi FDT/POP dari data tidak digeser sedikit pun."""
    return "%s,%s,0" % (repr(float(p[0])), repr(float(p[1])))


class _W(object):
    def __init__(self):
        self.o = []
        self.lokal = {}          # jenis ikon -> id style ikon pengguna (bila pengguna menyediakannya)
        self.ikon_pakai = {}

    def ik(self, jenis, core=None, eks=False):
        """Style ikon seperti di compile desainer: hanger 'forbidden', OLT 'ranger_station'; closure/FDT/OTB/tiang memakai
        ikon organisasi bila ada (closure mengikuti kapasitas seperti template), selain itu ikon bawaan Tembuku.
        eks=True: varian objek eksisting (warna ikon seperti di compile)."""
        if jenis in ("slack", "hanger"):
            return "apd_hanger"
        if jenis == "pop":
            return "apd_olt"
        st = None
        if jenis == "closure" and core:      # template: 12-48 'Closure 48', 96-144 'Closure 96', 288 'CL_288'
            j = "closure_288" if core >= 288 else ("closure_kecil" if core <= 48 else "closure")
            st = self.lokal.get(j)
        if st is None and jenis.startswith("tiang"):
            st = self.lokal.get(jenis, "ikon_tiang")
        if st is None:
            st = self.lokal.get(jenis, "ikon_" + jenis)
        return st + "_eks" if eks and st.startswith("lokal_") else st

    def a(self, s):
        self.o.append(s)

    def folder(self, nama, isi):
        self.a("<Folder><name>%s</name>" % escape(nama))
        isi()
        self.a("</Folder>")

    def garis(self, nama, ll, style, desc="", data=None, final=False):
        if not final:
            ll = _bersihkan_ll(ll)  # pemeriksaan terakhir: tanpa taji/bolak-balik, ujung tetap
        ed = ""
        if data:
            ed = "<ExtendedData>%s</ExtendedData>" % "".join(
                '<Data name="%s"><value>%s</value></Data>' % (escape(str(k)), escape(str(v))) for k, v in data.items())
        self.a("<Placemark><name>%s</name>%s<styleUrl>#%s</styleUrl>%s<LineString><tessellate>1</tessellate>"
               "<coordinates>%s</coordinates></LineString></Placemark>"
               % (escape(nama), "<description>%s</description>" % escape(desc) if desc else "", style, ed, _c(ll)))

    def titik(self, nama, p, style, desc="", data=None, persis=False):
        ed = ""
        if data:
            ed = "<ExtendedData>%s</ExtendedData>" % "".join(
                '<Data name="%s"><value>%s</value></Data>' % (escape(str(k)), escape(str(v))) for k, v in data.items())
        self.a("<Placemark><name>%s</name>%s<styleUrl>#%s</styleUrl>%s<Point><coordinates>%s</coordinates></Point>"
               "</Placemark>" % (escape(nama), "<description>%s</description>" % escape(desc) if desc else "", style, ed,
                                 _c_persis(p) if persis else _c([p])))


PIN = ('<IconStyle><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>'
       '</Icon><hotSpot x="20" y="2" xunits="pixels" yunits="pixels"/></IconStyle>')   # gaya garis seperti hasil desainer


def _styles(w, lokal=None):
    lokal = lokal or {}
    for c, col in WARNA_CORE.items():
        w.a('<Style id="kabel%d">%s<LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (c, PIN, col, LEBAR_KABEL))
    for nm, col in WARNA_INFRA.items():
        w.a('<Style id="infra_%s">%s<LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (nm, PIN, col, 3 if nm == "GARIS_BANTU" else 10))
    w.a('<Style id="kandidat"><LineStyle><color>9900a5ff</color><width>6</width></LineStyle></Style>')
    w.a('<Style id="kandidat_tolak"><LineStyle><color>66888888</color><width>3</width></LineStyle></Style>')
    for k, href in IKON.items():
        w.a('<Style id="ikon_%s"><IconStyle><color>%s</color><scale>%s</scale><Icon><href>%s</href></Icon>'
            '</IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, WARNA_IKON[k], SKALA[k], href))
    for c, col in WARNA_CORE.items():                 # garis Colo Pole: warna kapasitas kabelnya, lebar 3 (template APD)
        w.a('<Style id="kolo%d"><LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (c, col, LEBAR_KABEL))
    for k, (href, skala) in IKON_APD.items():
        w.a('<Style id="apd_%s"><IconStyle><scale>%s</scale><Icon><href>%s</href></Icon></IconStyle>'
            '<LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, skala, href))
    w.ikon_pakai = pilih_ikon(lokal)
    for k, (netral, skala, _isi) in w.ikon_pakai.items():     # ikon pengguna: tanpa pewarnaan, skala template
        w.a('<Style id="lokal_%s"><IconStyle><scale>%s</scale><Icon><href>files/%s</href></Icon></IconStyle>'
            '<LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, skala, netral))
        w.a('<Style id="lokal_%s_eks"><IconStyle><color>%s</color><scale>%s</scale><Icon><href>files/%s</href></Icon>'
            '</IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, WARNA_EKSISTING, skala, netral))
        w.lokal[k] = "lokal_" + k


def _jarak_ke_ruas(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5


def _dp(xy, tol):
    """Douglas-Peucker: buang titik yang menyimpang < tol meter dari garis lurus (ujung tetap)."""
    if len(xy) < 3:
        return list(xy)
    simpan = [False] * len(xy)
    simpan[0] = simpan[-1] = True
    tumpuk = [(0, len(xy) - 1)]
    while tumpuk:
        a, b = tumpuk.pop()
        jauh, idx = 0.0, None
        for i in range(a + 1, b):
            d = _jarak_ke_ruas(xy[i], xy[a], xy[b])
            if d > jauh:
                jauh, idx = d, i
        if idx is not None and jauh > tol:
            simpan[idx] = True
            tumpuk += [(a, idx), (idx, b)]
    return [p for p, s in zip(xy, simpan) if s]


def rapikan_garis(xy, kembali_m=15.0, taji_m=40.0, tol_m=2.5):
    """Rapikan jalur hasil graf (koordinat lokal meter) agar seperti digambar desainer: jalur graf bisa berpindah-pindah
    di antara kabel inventaris dan kabel compile yang sejajar di jalan yang sama, sehingga muncul taji, jalur pergi-pulang
    (garis dobel) dan zigzag. Ujung awal dan akhir (titik sambung, FDT, POP) tidak pernah digeser.
      1. titik kembar (< 0,5 m) dibuang;
      2. penggalan pergi-pulang: bila jalur kembali ke dalam kembali_m dari titik sebelumnya, penggalan di antaranya
         dipotong (kabel ditarik langsung, bukan bolak-balik);
      3. taji: titik yang membuat jalur berbalik arah tajam (> 150 derajat) dengan ruas pendek (< taji_m) dibuang;
      4. zigzag kecil antar kabel sejajar dihaluskan (Douglas-Peucker, toleransi tol_m)."""
    import math
    p = []
    for q in xy:
        q = (float(q[0]), float(q[1]))
        if not p or math.hypot(q[0] - p[-1][0], q[1] - p[-1][1]) >= 0.5:
            p.append(q)
    if len(p) < 3:
        return p
    # 2. potong penggalan pergi-pulang (cari titik terjauh di depan yang kembali dekat titik i)
    out, i = [], 0
    while i < len(p):
        out.append(p[i])
        j_pilih = None
        acc = 0.0
        for j in range(i + 1, len(p)):
            acc += math.hypot(p[j][0] - p[j - 1][0], p[j][1] - p[j - 1][1])
            if j > i + 1 and acc > 2.5 * kembali_m and \
                    math.hypot(p[j][0] - p[i][0], p[j][1] - p[i][1]) <= kembali_m:
                j_pilih = j
        i = j_pilih if j_pilih is not None else i + 1
    if out[-1] != p[-1]:
        out.append(p[-1])
    p = out
    # 3. taji
    ubah = True
    while ubah and len(p) >= 3:
        ubah = False
        for k in range(1, len(p) - 1):
            a, b, c = p[k - 1], p[k], p[k + 1]
            u = (b[0] - a[0], b[1] - a[1])
            v = (c[0] - b[0], c[1] - b[1])
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 1e-6 or lv < 1e-6:
                del p[k]
                ubah = True
                break
            cos = (u[0] * v[0] + u[1] * v[1]) / (lu * lv)
            if cos < -0.866 and min(lu, lv) < taji_m:
                del p[k]
                ubah = True
                break
    # 4. haluskan zigzag
    return _dp(p, tol_m)


def _lengkung(xy, langkah_m=1.0, jendela=6, ulang=3):
    """Belokan dilengkungkan merata seperti kabel udara di tiang sudut. Garis dicacah tiap langkah_m meter lalu
    dihaluskan dengan rata-rata bergerak (+-jendela titik, diulang 'ulang' kali, kira-kira kurva Gauss), sehingga jari-jari
    lengkung tidak bergantung pada panjang ruas aslinya: tanpa patahan dan tanpa gelombang. Ujung awal/akhir tetap
    (jendela menyempit di dekat ujung). Garis bergeser dari titik sudut sekitar 2-3 m. Titik segaris dibuang lagi."""
    import math
    p = [(float(q[0]), float(q[1])) for q in xy]
    if len(p) < 3:
        return p
    # cacah merata
    r = [p[0]]
    for a, b in zip(p, p[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(L // langkah_m))
        for j in range(1, n + 1):
            s = j / float(n)
            r.append((a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s))
    n = len(r)
    if n < 5:
        return p
    for _ in range(ulang):
        s = [r[0]]
        for i in range(1, n - 1):
            w = min(jendela, i, n - 1 - i)          # simetris: ujung tidak tertarik
            xs = r[i - w:i + w + 1]
            s.append((sum(q[0] for q in xs) / len(xs), sum(q[1] for q in xs) / len(xs)))
        s.append(r[-1])
        r = s
    return _dp(r, 0.1)


def _bersihkan_ll(ll):
    """rapikan_garis untuk garis (lon, lat): dihitung dalam meter lokal, ujung awal dan akhir tidak berubah."""
    import math
    ll = [(float(p[0]), float(p[1])) for p in ll]
    if len(ll) < 3:
        return ll
    k = math.cos(math.radians(ll[0][1]))
    xy = [(p[0] * 111320.0 * k, p[1] * 110574.0) for p in ll]
    r = _lengkung(rapikan_garis(xy))
    out = [(q[0] / (111320.0 * k), q[1] / 110574.0) for q in r]
    out[0], out[-1] = ll[0], ll[-1]
    return out


def _sepotong(kabel, ll, min_m=2.0):
    """Bagian garis kabel final (kabel = daftar garis lon/lat yang sudah dirapikan dan dilengkungkan) di antara proyeksi
    ujung awal dan ujung akhir ll. Colo Pole dan New Infra diambil dari sini supaya selalu berimpit persis dengan kabel
    barunya. -> garis lon/lat searah kabel, atau None bila terlalu pendek / tidak ada kabel."""
    import math
    if not kabel or len(ll) < 2:
        return None
    k = math.cos(math.radians(ll[0][1]))
    m = lambda p: (p[0] * 111320.0 * k, p[1] * 110574.0)
    b = lambda q: (q[0] / (111320.0 * k), q[1] / 110574.0)

    def proyeksi(q, xy):
        best, acc = None, 0.0
        for i in range(len(xy) - 1):
            a, c = xy[i], xy[i + 1]
            dx, dy = c[0] - a[0], c[1] - a[1]
            L = math.hypot(dx, dy)
            t = 0.0 if L <= 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (L * L)))
            d = math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)
            if best is None or d < best[0]:
                best = (d, acc + t * L)
            acc += L
        return best
    p0, p1 = m(ll[0]), m(ll[-1])
    pilih = None
    for g in kabel:
        if len(g) < 2:
            continue
        xy = [m(p) for p in g]
        a, c = proyeksi(p0, xy), proyeksi(p1, xy)
        if pilih is None or a[0] + c[0] < pilih[0]:
            pilih = (a[0] + c[0], xy, min(a[1], c[1]), max(a[1], c[1]))
    if pilih is None or pilih[3] - pilih[2] < min_m:
        return None
    _, xy, s0, s1 = pilih
    out, acc = [], 0.0
    for i in range(len(xy) - 1):
        a, c = xy[i], xy[i + 1]
        L = math.hypot(c[0] - a[0], c[1] - a[1])
        if L <= 0:
            continue
        for s in (s0, s1):
            if acc <= s <= acc + L and (not out or s == s1):
                t = (s - acc) / L
                out.append((a[0] + t * (c[0] - a[0]), a[1] + t * (c[1] - a[1])))
                if s == s1:
                    return [b(q) for q in out]
        if out and acc + L < s1:
            out.append(c)
        acc += L
    return [b(q) for q in out] if len(out) >= 2 else None


def _ke_kabel(p, kabel, tol_m=8.0):
    """Titik (hanger/tiang) digeser ke garis kabel final terdekat bila jaraknya <= tol_m, supaya duduk di atas kabel."""
    import math
    if not kabel:
        return p
    k = math.cos(math.radians(p[1]))
    q = (p[0] * 111320.0 * k, p[1] * 110574.0)
    best = None
    for g in kabel:
        for a, c in zip(g, g[1:]):
            a = (a[0] * 111320.0 * k, a[1] * 110574.0)
            c = (c[0] * 111320.0 * k, c[1] * 110574.0)
            dx, dy = c[0] - a[0], c[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
            r = (a[0] + t * dx, a[1] + t * dy)
            d = math.hypot(q[0] - r[0], q[1] - r[1])
            if best is None or d < best[0]:
                best = (d, r)
    if best is None or best[0] > tol_m:
        return p
    return (best[1][0] / (111320.0 * k), best[1][1] / 110574.0)


def _pangkas_ke_kabel(ll, kabel, tol_m=5.0):
    """Ujung garis Colo Pole yang menjorok keluar dari kabel baru (sisa taji yang sudah dibuang dari kabel) dipotong,
    supaya Colo Pole selalu berimpit dengan kabel barunya seperti gambar desainer."""
    import math
    if not kabel or len(ll) < 2:
        return ll
    k = math.cos(math.radians(ll[0][1]))

    def m(p):
        return (p[0] * 111320.0 * k, p[1] * 110574.0)
    ruas = [(m(a), m(b)) for g in kabel for a, b in zip(g, g[1:])]

    def jauh(p):
        q = m(p)
        return min(_jarak_ke_ruas(q, a, b) for a, b in ruas)

    def proyeksi(p):
        q = m(p)
        best = None
        for a, b in ruas:
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
            r = (a[0] + t * dx, a[1] + t * dy)
            d = math.hypot(q[0] - r[0], q[1] - r[1])
            if best is None or d < best[0]:
                best = (d, r)
        return (best[1][0] / (111320.0 * k), best[1][1] / 110574.0)
    ll = list(ll)
    # ujung yang menjorok diganti titik terdekatnya di kabel baru (titik belok kabel)
    for i in (-1, 0):
        if jauh(ll[i]) > tol_m:
            ll[i] = proyeksi(ll[i])
    return [p for j, p in enumerate(ll) if j == 0 or geo.haversine(p, ll[j - 1]) >= 0.5]


def _core_bulat(c):
    return min(CORE, key=lambda x: (abs(x - (c or 48)), x))


def _titik_tiap(ll, langkah):
    """Titik di sepanjang polyline (lon, lat) tiap 'langkah' meter dari awal -> [((lon, lat), jarak_m)]; ujung akhir
    tidak diulang (di sana sudah ada slack FDT)."""
    out, acc, target = [], 0.0, langkah
    for a, b in zip(ll, ll[1:]):
        d = geo.haversine(a, b)
        while d > 0 and acc + d >= target:
            t = (target - acc) / d
            out.append(((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), int(round(target))))
            target += langkah
        acc += d
    if out and acc - out[-1][1] < 0.25 * langkah:
        out.pop()
    return out


def nama_traksi(h, prm, tgl=None):
    f = h["fdt"]
    n = h["penomoran"]
    tgl = tgl or datetime.date.today().strftime("%d-%m-%Y")
    clus = f.get("cluster") or "IDCLUSTER"
    area = f.get("area") or f.get("kode")
    return "F%d_T%d_%s_APD Feeder KMZ_%s_%s" % (n["feeder"], n["t"], clus, area, tgl)


def _isi_traksi(w, h, prm, ke_ll):
    """Isi satu folder traksi sesuai template compile. ke_ll: lokal(m) -> (lon,lat)."""
    f, pop = h["fdt"], h["pop"]
    sel = h.get("terpilih")
    baru = h["keputusan"] == "FEEDER_BARU"
    rute = sel["rute"] if sel else (h["feeder_baru"] if baru else None)
    core_cab = int(prm["core_feeder_baru"] if baru else ((sel or {}).get("core_cabang") or prm["core_cabang"]))
    ts = (sel or {}).get("tap_slack")
    try:        # closure di titik sambung: sebesar kabel yang disambung, kecuali diatur angka tetap
        core_tap = _core_bulat(int(prm["closure_tap"]))
    except (TypeError, ValueError):
        core_tap = _core_bulat((sel or {}).get("core") or 96)
    n = h["penomoran"]
    stub = mesin.panjang_144(prm, n.get("feeder"))      # 144F feeder baru: pola slack ujung per feeder, maks. 750 m
    kab_baru = {}            # core -> [ll]
    infra = []               # [(kelas, core, ll, keterangan)] berurutan dari awal rute
    bantu = []
    if rute:
        titik = [ke_ll(p) for p in rapikan_garis(rute["titik"])]
        if baru and len(titik) >= 2:
            # feeder baru digambar dari POP: titik rute berurutan POP -> FDT
            awal, sisa = geo.potong(titik, stub)
            kab_baru.setdefault(144, []).append(awal)
            if len(sisa) >= 2:
                kab_baru.setdefault(core_cab, []).append(sisa)
        else:
            kab_baru.setdefault(core_cab, []).append(titik)
        sisa_stub = stub if baru else 0.0      # bagian awal feeder baru memakai kabel 144
        for kelas, ref, xy in rute["segmen"]:
            ll = [ke_ll(p) for p in rapikan_garis(xy)]
            if kelas == "GARIS_BANTU":
                bantu.append(ll)
                kelas = "NEW_INFRA"
            pjg = sum(geo.haversine(ll[i], ll[i + 1]) for i in range(len(ll) - 1))
            if sisa_stub > 1.0 and pjg > sisa_stub + 1.0 and len(ll) >= 2:
                awal, lanjut = geo.potong(ll, sisa_stub)
                infra.append((kelas, 144, awal, ref or ""))
                if len(lanjut) >= 2:
                    infra.append((kelas, core_cab, lanjut, ref or ""))
                sisa_stub = 0.0
            else:
                infra.append((kelas, 144 if sisa_stub > 1.0 else core_cab, ll, ref or ""))
                sisa_stub = max(0.0, sisa_stub - pjg)
    tgt = sel["rute"]["titik"][0] if sel else None
    tap_ll = ke_ll(tgt) if tgt is not None else None
    # PDF 3.3: closure baru tepat di koordinat slack/closure existing, tidak digeser; kabel baru dimulai dari titik itu
    if tap_ll and ts and ts.get("jenis") in ("slack", "closure") and ts.get("ll"):
        asli = (float(ts["ll"][0]), float(ts["ll"][1]))
        if geo.haversine(asli, tap_ll) > 0.3:
            for c_, daftar in kab_baru.items():
                for ll in daftar:
                    if ll and geo.haversine(ll[0], tap_ll) < 0.3:
                        ll.insert(0, asli)
        tap_ll = asli
    # tiang baru hanya di ruas New Infra (PDF 3.4): 9 m di kedua sisi penyeberangan jalan (ditulis ke folder Tiang 9
    # Meter), 7 m sebagai tiang virtual tiap tiang_m (jumlahnya di metadata kabel; titiknya ditulis hanya bila
    # tulis_tiang aktif - desainer tidak menaruh titik tiang 7 m, 0 dari 46 traksi)
    # bentuk akhir kabel baru (dirapikan + dilengkungkan sekali); Colo Pole, New Infra, hanger dan tiang diambil dari
    # bentuk ini supaya semuanya berimpit persis dengan kabelnya
    kab_final = {c: [_bersihkan_ll(ll) for ll in daftar] for c, daftar in kab_baru.items()}
    semua_final = [g for daftar in kab_final.values() for g in daftar]
    tiang = {6: [], 7: [], 9: []}
    if rute and float(prm.get("tiang_m") or 0) >= 10:
        for a, b in rute.get("seberang") or []:
            tiang[9] += [ke_ll(a), ke_ll(b)]
        for kelas, _core, ll, _ref in infra:
            if kelas != "NEW_INFRA" or ll in bantu:
                continue
            calon = [ll[0]] + [q for q, _j in _titik_tiap(ll, float(prm["tiang_m"]))]
            for q in calon:
                if all(geo.haversine(q, p9) > 12.0 for p9 in tiang[9]) and \
                        all(geo.haversine(q, p7) > 0.5 * float(prm["tiang_m"]) for p7 in tiang[7]):
                    tiang[7].append(q)
    # metadata keputusan & audit rute digabung ke placemark kabel (PDF 8), ditulis apa adanya untuk aplikasi BOM/review
    meta = {"Keputusan": str(mesin.nama_keputusan(h["keputusan"])), "Folder F/T": "F%s_T%s" % (n.get("feeder"), n.get("t")),
            "Tube": ("T%s" % n.get("t")) if n.get("t") else "-", "Kelompok tube": n.get("kelompok") or "-",
            "POP": pop["nama"] if pop else "-", "FDT": f["kode"]}
    if sel:
        meta.update({"Feeder yang dipakai": sel.get("nama") or sel.get("id"), "Kabel baru (m)": sel.get("kabel_baru_m"),
                     "Menumpang tiang existing (%)": round(100 * (sel.get("colo_rasio") or 0)),
                     "Titik sambung": str(mesin.label_tap(ts)) if ts else "titik baru di tengah kabel (perlu dicek)",
                     "Redaman (dB)": (sel.get("budget") or {}).get("total_db", "-"),
                     "Jalur POP-FDT (m)": sel.get("jalur_serat_m")})
    elif rute:
        meta.update({"Kabel baru (m)": round(rute.get("panjang_m", 0))})
    meta["Tiang baru 7 m (perkiraan)"] = len(tiang[7])
    meta["Tiang baru 9 m penyeberangan"] = len(tiang[9])
    meta["Status"] = "Usulan Tembuku - wajib ditinjau desainer"

    # seperti hasil desainer (Gresik 09-11-2026): kabel baru digambar dari FDT ke titik sambung bila menumpang feeder
    arah = (lambda ll: list(reversed(ll))) if not baru else (lambda ll: ll)

    def cable():
        def udara():
            # nama = angka core saja ('48'), tanpa keterangan tambahan (seperti hasil desainer)
            for c in CORE:
                w.folder("New Cable %dC" % c, lambda c=c: [w.garis("%d" % c, arah(ll), "kabel%d" % c, final=True)
                                                              for ll in kab_final.get(c, [])])
        w.folder("New Cable Aerial/Udara", udara)

        def colo():
            # nama 'COLO CABLE', keterangan = nama traksi feeder yang dipakai (seperti hasil desainer)
            if sel and sel.get("colo_xy"):
                tr = re.sub(r"\.km[lz]$", "", str(sel.get("traksi") or sel.get("nama") or ""), flags=re.I)
                w.garis("COLO CABLE", [ke_ll(p) for p in rapikan_garis(sel["colo_xy"])], "infra_COLO_CABLE", tr)
        w.folder("Collo Cable", colo)
        w.folder("UG Utilities", lambda: (w.folder("Manhole", lambda: None), w.folder("Handhole", lambda: None)))
    w.folder("Cable", cable)
    for m in (6, 7, 9):
        w.folder("Tiang %d Meter" % m, lambda m=m: (
            w.folder("New Tiang %d Meter" % m, lambda: [w.titik("Tiang %d" % m, _ke_kabel(q, semua_final), w.ik("tiang%d" % m),
                                                              "Tiang baru %d m (usulan)%s" % (
                                                                  m, " - penyeberangan jalan" if m == 9 else ""))
                                                      for q in tiang[m]] if (m == 9 or prm.get("tulis_tiang", False))
                                                      else None),
            w.folder("Eksisting Tiang %d Meter" % m, lambda: None)))

    def hanger():
        def nh():
            # hasil desainer (Gresik 09-11-2026) tidak memuat titik hanger/slack baru: bawaan tidak ditulis
            if not prm.get("tulis_hanger", True):
                return
            if tap_ll:
                w.titik("Slack", tap_ll, w.ik("slack"), "Slack %d m di titik sambung (tap)" % prm["slack_m"])
            # hanger/slack tiap hanger_m dari awal penarikan kabel baru (aturan 300 m)
            langkah = float(prm.get("hanger_m") or 0)
            if rute and langkah >= 50:
                semua_tiang = tiang[7] + tiang[9]
                for q, jarak in _titik_tiap([ke_ll(p) for p in rute["titik"]], langkah):
                    # aturan: hanger disesuaikan ke tiang terdekat (tiang baru usulan dalam 30 m)
                    dekat = min(semua_tiang, key=lambda t: geo.haversine(q, t), default=None)
                    if dekat is not None and geo.haversine(q, dekat) <= 30.0:
                        q = dekat
                    # hanger yang berdempetan dengan slack di titik sambung atau di FDT tidak ditulis dua kali
                    if any(u and geo.haversine(q, u) < 20.0 for u in (tap_ll, f["ll"])):
                        continue
                    w.titik("Slack", _ke_kabel(q, semua_final), w.ik("slack"),
                            "Hanger di sekitar %d m dari awal kabel baru" % jarak)
            w.titik("Slack", f["ll"], w.ik("slack"), "Slack %d m di FDT" % prm["slack_m"])
        w.folder("New Hanger", nh)
        w.folder("Eksisting Hanger", lambda: None)
    w.folder("Hanger", hanger)

    def closure():
        def nc():
            for c in CORE:
                def isi(c=c):
                    # seperti hasil desainer: New Closure 96 di FDT; titik sambung di tengah kabel (tanpa slack/closure
                    # existing) juga mendapat New Closure baru
                    if c == core_tap and h["keputusan"] != "PERLU_MANUAL" and (sel or baru):
                        if tap_ll and not ts and not baru:
                            w.titik("New Closure", tap_ll, w.ik("closure", c))
                        w.titik("New Closure", f["ll"], w.ik("closure", c))
                    if baru and c == 144 and kab_baru.get(144):
                        w.titik("New Closure", kab_baru[144][0][-1], w.ik("closure", 144))
                w.folder("New Closure %d" % c, isi)
        w.folder("New Closure", nc)
        # slack/closure/ujung kabel existing yang dipakai sebagai titik sambung = 'Ext Closure' (seperti hasil desainer)
        w.folder("Eksisting Closure", lambda: (w.titik("Ext Closure", tap_ll,
                                                       w.ik("closure", core_tap, eks=True))
                                               if tap_ll and ts and not baru else None))
    w.folder("Closure", closure)

    def otb():
        def no():
            for c in CORE:
                w.folder("New OTB %d" % c, lambda c=c: (w.titik("OTB %d" % c, pop["ll"], w.ik("otb"), "OTB di POP")
                                                        if baru and pop and c == 144 else None))
        w.folder("New OTB", no)
        # hasil desainer tidak menulis OTB Existing saat menumpang feeder yang ada: bawaan tidak ditulis
        w.folder("Eksisting OTB", lambda: (w.titik("OTB Existing", pop["ll"], w.ik("otb"))
                                           if sel and pop and not baru and prm.get("tulis_otb_eksisting", True) else None))
    w.folder("OTB", otb)

    def fdt():
        # urutan kolom seperti hasil desainer: FDT FAT CODE, PREMISES, SPLITTERS, LAT, LONG, F/T (SP1), F/T (SP2)
        attrs = {str(k).strip().upper(): v for k, v in (f.get("attrs") or {}).items() if k}
        data = {"FDT FAT CODE": f["kode"], "PREMISES": int(f["premises"]) if f.get("premises") else "-",
                "SPLITTERS": ("%dx1x%d" % (f["splitter"], f.get("rasio") or 4)) if f.get("splitter") else "-",
                "LAT": attrs.get("LAT") or repr(float(f["ll"][1])), "LONG": attrs.get("LONG") or repr(float(f["ll"][0])),
                "F (SP1)": "-", "T (SP1)": "-", "F (SP2)": "-", "T (SP2)": "-"}
        # F/T (SP1) diisi dari keputusan (aturan 11-11-2026); kolom lain apa adanya
        if n.get("feeder") and n.get("t") and h["keputusan"] != "PERLU_MANUAL":
            data["F (SP1)"], data["T (SP1)"] = n["feeder"], n["t"]
        for kk, vv in (f.get("attrs") or {}).items():
            if kk and kk.strip().upper() not in {x.upper() for x in data} | {"NAME"} and len(str(vv)) <= 200:
                data[kk] = vv if str(vv).strip() else "-"
        w.folder("Eksisting FDT", lambda: (w.titik(f["kode"], f["ll"], w.ik("fdt", eks=True), "", data, persis=True)
                                           if f.get("status") == "Eksisting" else None))
        w.folder("New FDT", lambda: (w.titik(f["kode"], f["ll"], w.ik("fdt"), "", data, persis=True)
                                     if f.get("status") != "Eksisting" else None))
    w.folder("FDT", fdt)
    # OLT di POP: selalu untuk feeder baru; saat menumpang feeder ikut pengaturan tulis_otb_eksisting (penanda ujung awal)
    w.folder("OLT", lambda: w.titik(pop["nama"], pop["ll"], w.ik("pop"), "")
             if pop and (baru or (sel and prm.get("tulis_otb_eksisting", True))) else None)

    def ket():
        w.folder("New Cable Galian", lambda: [w.folder("New Cable %dC UG" % c, lambda: None) for c in CORE])

        pemilik = (rute or {}).get("pemilik") or {}

        def tiang_colo():
            # template APD: warna kapasitas kabelnya, lebar 3; nama 'Colo Pole FTTH' untuk tiang feeder sendiri dan
            # 'Colo Pole <pemilik>' untuk jaringan lain (seperti penamaan desainer)
            for c in CORE:
                def isi(c=c):
                    gab = []        # ruas berurutan digabung jadi satu garis (seperti hasil desainer)
                    for kelas, core, ll, ref in infra:
                        if core == c and kelas in ("TIANG_NASIONAL", "TIANG_COMPILE"):
                            # hasil desainer: selalu 'COLO POLE FTTH', garis b3ffaa55 lebar 10 (nama pemilik tidak ditulis)
                            # ruas berikutnya yang mulai dekat (<= 15 m, satu tiang/koridor) disambung jadi satu garis
                            if gab and geo.haversine(gab[-1][-1], ll[0]) <= 15.0:
                                gab[-1].extend(ll[1:] if geo.haversine(gab[-1][-1], ll[0]) < 1.0 else ll)
                            else:
                                gab.append(list(ll))
                    # garis Colo Pole = potongan garis kabel final di antara ujung-ujung ruasnya (berimpit persis)
                    gab = [x for x in (_sepotong(kab_final.get(c) or semua_final, x) for x in gab) if x and len(x) >= 2]
                    for ll in (gab if baru else [arah(x) for x in reversed(gab)]):
                        w.garis("COLO POLE FTTH", ll, "infra_TIANG_COMPILE", final=True)
                w.folder("Colo Pole %dC" % c, isi)
        w.folder("Collo Tiang", tiang_colo)

        # ruas kabel baru yang belum punya tiang/jalur = 'New Infra' (seperti desainer: garis b300ff55 lebar 10 di
        # Keterangan Infra/New Infra), supaya tim BOM/lapangan tahu di mana tiang baru dibutuhkan
        gab = []
        for kelas, _core, ll, _ref in infra:
            if kelas != "NEW_INFRA" or len(ll) < 2:
                continue
            if gab and geo.haversine(gab[-1][-1], ll[0]) <= 15.0:
                gab[-1].extend(ll[1:] if geo.haversine(gab[-1][-1], ll[0]) < 1.0 else ll)
            else:
                gab.append(list(ll))
        gab = [x for x in (_sepotong(semua_final, x) for x in gab) if x and len(x) >= 2]
        gab = [x for x in gab if sum(geo.haversine(x[i], x[i + 1]) for i in range(len(x) - 1)) >= 10.0]
        if gab and h["keputusan"] != "PERLU_MANUAL":
            w.folder("New Infra", lambda: [w.garis("New Infra", ll if baru else arah(ll), "infra_NEW_INFRA", final=True)
                                           for ll in (gab if baru else list(reversed(gab)))])
    w.folder("Keterangan Infra", ket)
    return bantu, [ll for kelas, _c, ll, _r in infra if kelas == "NEW_INFRA"], tiang


def _analisis_folder(w, h, ke_ll, bantu, infra_baru=(), tiang=None):
    def isi():
        for m_, daftar in sorted((tiang or {}).items()):
            for q in daftar:
                w.titik("Tiang %d m (usulan)" % m_, q, w.ik("tiang%d" % m_),
                        "Perkiraan tiang baru %d m%s" % (m_, " di penyeberangan jalan" if m_ == 9 else ""))
        for ll in infra_baru:
            if ll not in bantu:
                w.garis("Butuh tiang atau jalur baru", ll, "infra_NEW_INFRA",
                        "Di bagian ini belum ada tiang atau kabel yang bisa ditumpangi.")
        for ll in bantu:
            w.garis("GARIS BANTU - gambar ulang mengikuti jalan/tiang", ll, "infra_GARIS_BANTU",
                    "Tidak ada data jalan atau kabel di bagian ini: garis lurus sementara, bukan jalur pasang. "
                    "Gambar ulang mengikuti jalan atau tiang.")
        for i, k in enumerate(h["kandidat"][:5]):
            w.garis("#%d %s %s" % (i + 1, k["label_colo"], k["nama"] or k["id"]), [ke_ll(k["rute"]["titik"][0]),
                                                                                    h["fdt"]["ll"]],
                    "kandidat" if k["lolos"] else "kandidat_tolak",
                    mesin.uraian_kandidat(k))
            w.titik("Tap #%d" % (i + 1), ke_ll(k["rute"]["titik"][0]), "ikon_tap",
                    "Titik sambung (tap) kandidat #%d: %s" % (i + 1, k["nama"] or k["id"]))
    w.folder("Analisis %s (%s)" % (h["fdt"]["kode"], mesin.nama_keputusan(h["keputusan"])), isi)


def periksa_template(path):
    """Buka kembali KMZ hasil dan cocokkan tiap folder traksi dengan susunan template Feeder (nama + urutan).
    -> daftar masalah (kosong = sesuai). Tidak ada folder tambahan yang diizinkan di KMZ desain."""
    import re
    with zipfile.ZipFile(path) as zf:
        kml = zf.read("doc.kml").decode("utf-8")
        berkas = set(zf.namelist())
    masalah, jalur, traksi, kini, dalam = [], [], {}, None, None
    for m in re.finditer(r"<Folder><name>([^<]*)</name>|</Folder>", kml):
        if m.group(1) is None:
            jalur.pop()
            if dalam is not None and len(jalur) < dalam:
                dalam = None
            continue
        jalur.append(m.group(1).replace("&amp;", "&"))
        if dalam is not None and len(jalur) > dalam:
            traksi[kini].append("/".join(jalur[dalam:]))
        elif jalur[-1] == "Feeder" and len(jalur) >= 2 and re.match(r"^F\d+[_-]?T", jalur[-2], re.I):
            dalam = len(jalur)                                    # kedalaman bebas: dengan/tanpa folder POP di atasnya
            kini = "%s #%d" % (jalur[-2], len(traksi) + 1)        # nama traksi bisa kembar: tiap kemunculan diperiksa
            traksi[kini] = []
    if not traksi:
        masalah.append("tidak ada folder Feeder di dalam folder traksi")
    for t, ada in traksi.items():
        inti = list(ada)
        if inti[-1:] == [FOLDER_NEW_INFRA]:      # tambahan yang juga dipakai desainer, hanya bila ada ruas New Infra
            inti = inti[:-1]
        if tuple(inti) != TEMPLATE_FEEDER:
            kurang = [x for x in TEMPLATE_FEEDER if x not in inti]
            lebih = [x for x in inti if x not in TEMPLATE_FEEDER]
            masalah.append("%s: %s" % (t, "; ".join(filter(None, [
                "folder hilang: " + ", ".join(kurang[:4]) if kurang else "",
                "folder di luar template: " + ", ".join(lebih[:4]) if lebih else "",
                "urutan folder berbeda dari template" if not kurang and not lebih else ""]))))
    if re.search(r"<Folder><name>Distribution", kml, re.I):
        masalah.append("ada folder Distribution")
    if re.search(r"<Folder><name>(Analisis|TEMBUKU)", kml):
        masalah.append("ada folder analisis di dalam KMZ desain")
    for href in set(re.findall(r"<href>(files/[^<]+)</href>", kml)):
        if href.replace("&amp;", "&") not in berkas:
            masalah.append("ikon tidak tertanam: " + href)
    return masalah


def lokasi_fdt(path):
    """Baca kembali lokasi titik FDT di KMZ hasil -> {kode: (lon, lat)} (untuk membuktikan FDT tidak bergeser)."""
    import re
    with zipfile.ZipFile(path) as zf:
        kml = zf.read("doc.kml").decode("utf-8")
    out = {}
    for m in re.finditer(r"<Folder><name>(?:New|Eksisting) FDT</name>(.*?)</Folder>", kml, re.S):
        for n, c in re.findall(r"<Placemark><name>([^<]*)</name>.*?<Point><coordinates>([^<]*)</coordinates>", m.group(1), re.S):
            x, y = c.split(",")[:2]
            out.setdefault(n, []).append((float(x), float(y)))
    return out


def tulis(hasil, path, prm, judul=None, ikon_lokal=None, analisis=False):
    """Tulis satu KMZ berisi satu atau banyak hasil FDT. ikon_lokal: {nama berkas: bytes} ikon milik pengguna.
    analisis=False: KMZ desain, MURNI susunan folder template Feeder (untuk aplikasi BOM).
    analisis=True : KMZ pendamping berisi bahan tinjauan (kandidat, titik sambung, garis bantu, bagian yang butuh tiang
                    atau jalur baru) - sengaja dipisah agar tidak ikut terbaca sebagai objek BOM."""
    w = _W()
    ikon_lokal = ikon_lokal or {}
    w.a('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
        '<Document><name>%s</name><!-- %s -->' % (
            escape(judul or os.path.basename(path)),
            # arahan finalisasi: keterangan ini tidak lagi tampil di Google Earth; tetap ada sebagai komentar KML
            # (penanda hasil Tembuku untuk keluaran_tembuku + atribusi data jalan OpenStreetMap)
            ("Dibuat oleh Tembuku (Feeder Tap Designer). " + osm.ATRIBUSI).replace("--", "-")))
    _styles(w, ikon_lokal)
    kelompok = {}
    for h in hasil:
        n = h["penomoran"]
        kelompok.setdefault(n["pop_folder"], {}).setdefault(n["feeder"], []).append(h)
    for popf, fdrs in kelompok.items():
        def pop_isi(fdrs=fdrs):
            for fn, hs in sorted(fdrs.items()):
                def fdr_isi(hs=hs):
                    for h in hs:
                        L = geo.Lokal(*h["lokal"])
                        if analisis:
                            bantu, infra_baru, tiang = _isi_traksi(_W(), h, prm, L.balik)
                            _analisis_folder(w, h, L.balik, bantu, infra_baru, tiang)
                            continue

                        def tr(h=h, L=L):
                            w.folder("Feeder", lambda: _isi_traksi(w, h, prm, L.balik))
                        w.folder(nama_traksi(h, prm), tr)
                w.folder("Feeder %d" % fn, fdr_isi)
        # satu folder POP di akar, sama dengan compile (POP / Feeder N / traksi) - tanpa akar tambahan, tanpa ".kmz"
        w.folder(re.sub(r"\.km[lz]$", "", (popf or "POP").strip(), flags=re.I) or "POP", pop_isi)
    w.a("</Document></kml>")
    teks = "".join(w.o) if analisis else _rapikan("".join(w.o))
    _zip(path, teks, w)
    return path


def _rapikan(teks, awalan=""):
    """Buang definisi style Tembuku (id berawalan 'awalan') yang tidak dirujuk placemark mana pun, seperti hasil
    desainer yang hanya memuat style yang dipakai."""
    dipakai = set(re.findall(r"<styleUrl>#([^<]+)</styleUrl>", teks))
    return re.sub(r'<Style id="(%s[^"]*)">.*?</Style>' % re.escape(awalan),
                  lambda m: m.group(0) if m.group(1) in dipakai else "", teks, flags=re.S)


def _ikon_dipakai(teks, w, lokal=None):
    """Hanya ikon yang benar-benar dirujuk di KML yang ditanam (seperti hasil desainer). lokal: ikon pengguna
    {nama berkas: bytes}, dipakai juga untuk ikon yang dirujuk KMZ masukan tetapi tidak ikut di dalamnya."""
    dipakai = {x.replace("&amp;", "&") for x in re.findall(r"<href>\s*(files/[^<]+?)\s*</href>", teks)}
    out = {}
    for nama, isi in ikon.semua().items():
        if nama in dipakai:
            out[nama] = isi
    for asli, _skala, isi in w.ikon_pakai.values():
        if "files/" + asli in dipakai:
            out.setdefault("files/" + asli, isi)
    for nama, isi in (lokal or {}).items():
        if "files/" + os.path.basename(nama) in dipakai:
            out.setdefault("files/" + os.path.basename(nama), isi)
    return out


def _zip(path, teks, w, lain=None, lokal=None):
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", teks.encode("utf-8"))
        for nama, isi in (lain or {}).items():
            zf.writestr(nama, isi)
        for nama, isi in _ikon_dipakai(teks, w, lokal).items():
            if nama not in zf.namelist():
                zf.writestr(nama, isi)
    os.replace(tmp, path)


def _cari_folder(kml, nama, mulai=0):
    """Posisi (awal, akhir) elemen <Folder> pertama bernama 'nama' (teks KML apa adanya), atau None."""
    for m in re.finditer(r"<Folder(?:\s[^>]*)?>\s*<name>\s*%s\s*</name>" % re.escape(nama), kml[mulai:]):
        a = mulai + m.start()
        tingkat, i = 0, a
        for t in re.finditer(r"<Folder(?:\s[^>]*)?>|</Folder>", kml[a:]):
            tingkat += 1 if t.group(0) != "</Folder>" else -1
            if tingkat == 0:
                return a, a + t.end()
        return None
    return None


def bisa_isi_distribusi(path):
    """True bila KMZ ini KMZ APD Distribusi dengan folder Feeder (template) di samping folder Distribution."""
    try:
        with zipfile.ZipFile(path) as zf:
            nm = next((n for n in zf.namelist() if n.lower().endswith(".kml")), None)
            if not nm or zf.getinfo(nm).file_size > 200 * 1024 * 1024:
                return False
            kml = zf.read(nm).decode("utf-8", "replace")
    except (OSError, zipfile.BadZipFile, KeyError):
        return False
    return _cari_folder(kml, "Feeder") is not None and _cari_folder(kml, "Distribution") is not None


def nama_hasil_distribusi(path_masukan):
    """Nama berkas hasil: nama dokumen di dalam KMZ distribusi (tanpa salinan ' (1)') + ' - HASIL.kmz'."""
    nama = os.path.basename(path_masukan)
    try:
        with zipfile.ZipFile(path_masukan) as zf:
            nm = next(n for n in zf.namelist() if n.lower().endswith(".kml"))
            m = re.search(r"<Document[^>]*>\s*<name>([^<]+)</name>", zf.read(nm)[:4096].decode("utf-8", "replace"))
            if m and m.group(1).strip():
                nama = m.group(1).strip().replace("&amp;", "&")
    except (OSError, zipfile.BadZipFile, StopIteration):
        pass
    nama = re.sub(r"\.km[lz]$", "", nama, flags=re.I)
    nama = re.sub(r"\s*\(\d+\)$", "", nama)
    return re.sub(r'[\\/:*?"<>|]', "_", nama) + " - HASIL.kmz"


def tulis_distribusi(h, path_masukan, path, prm, ikon_lokal=None):
    """KMZ APD Distribusi masukan dengan folder Feeder diisi desain feeder FDT ini, seperti hasil desainer: isi
    Distribution dan semua berkas di KMZ masukan tetap apa adanya; hanya folder Feeder (template kosong) diganti."""
    with zipfile.ZipFile(path_masukan) as zf:
        nm = next(n for n in zf.namelist() if n.lower().endswith(".kml"))
        kml = zf.read(nm).decode("utf-8")
        lain = {n: zf.read(n) for n in zf.namelist() if n != nm and not n.endswith("/")}
    pos = _cari_folder(kml, "Feeder")
    if pos is None:
        raise ValueError("folder Feeder tidak ada di KMZ distribusi")
    w = _W()
    _styles(w, ikon_lokal or {})
    gaya = "".join(w.o)
    w.o = []
    L = geo.Lokal(*h["lokal"])
    w.folder("Feeder", lambda: _isi_traksi(w, h, prm, L.balik))
    isi = "".join(w.o)
    # id style Tembuku diberi awalan agar tidak bentrok dengan style di KMZ masukan
    for sid in set(re.findall(r'<Style id="([^"]+)"', gaya)):
        gaya = gaya.replace('<Style id="%s">' % sid, '<Style id="tbk_%s">' % sid)
        isi = isi.replace("<styleUrl>#%s</styleUrl>" % sid, "<styleUrl>#tbk_%s</styleUrl>" % sid)
    kml = kml[:pos[0]] + isi + kml[pos[1]:]
    m = re.search(r"<Document[^>]*>\s*(<name>[^<]*</name>)?", kml)
    sisip = m.end() if m else 0
    kml = kml[:sisip] + "\n<!-- Desain feeder: Tembuku. Data jalan (c) OpenStreetMap contributors, ODbL -->" + gaya + \
        kml[sisip:]
    _zip(path, _rapikan(kml, "tbk_"), w, lain, ikon_lokal)
    return path
