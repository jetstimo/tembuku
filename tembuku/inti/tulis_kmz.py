# -*- coding: utf-8 -*-
# Tembuku - penulis KMZ format Compile APD Feeder.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""KMZ hasil mengikuti template Compile APD Feeder organisasi (hierarki folder contoh Bitung/Tomohon 2026) agar dapat langsung
ditempel ke compile (slide 7/11): POP / Feeder N / F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<tgl> / Cable, Tiang, Hanger,
Closure, OTB, FDT, OLT, Keterangan Infra. Warna kabel = slide 16 'Format Warna Kabel' (KML aabbggrr).
KMZ: doc.kml entri pertama, DEFLATE, UTF-8 tanpa BOM; semua teks di-escape (tidak ada HTML/JS dari input)."""
import datetime
import math
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
FOLDER_ROUTE_EXISTING = "Informasi Route Existing"  # arahan 18-11-2026: kabel existing yang dilalui (NAME, DESCR2)
# Ikon milik pengguna (opsional, dari folder 'ikon'; tidak ikut di plugin). Dikenali dari kata di nama berkasnya, apa pun
# imbuhannya, lalu ditanam ke KMZ dengan nama netral: jenis -> (pola nama berkas, nama di KMZ, skala template).
# Pola dicoba berurutan, dari nama persis set ikon tim (ICON_FTTH: 'FDT.png', 'Closure 96.png', 'CL_144.png',
# 'OTB_144.png', 'OLT.png', 'Spare Cable.png', 'ICONFTTH-7M.png', ...) ke pola umum; varian lain ('FDT Ground', 'FDT ioh',
# 'Pole 7m Ex') tidak dipakai untuk objek baru. Tiang template APD: New Tiang 7/9 m = ICONFTTH-7M/9m.
# FDT: desain nyata desainer memakai gambar 'FDT ioh' (compile Jambi & Gresik, isi berkas identik dengan set ICON_FTTH),
# jadi 'FDT ioh' didahulukan; 'FDT' biasa hanya bila 'FDT ioh' tidak ada.
_TANPA_VARIAN = r"(?!.*\b(GROUND|IOH|EX|EKS|EXISTING|EKSISTING)\b)"
IKON_LOKAL = {"fdt": ((r"^FDT IOH$", r"^FDT IOH\b", r"^FDT$", r"^FDT\b" + _TANPA_VARIAN, r"^FDT\b"), "fdt_lokal.png", 0.5),
              "pop": ((r"^OLT$", r"^OLT\b" + _TANPA_VARIAN, r"^POP\b"), "olt_lokal.png", 1.2),
              "closure": ((r"^(CLOSURE|CL) ?96$", r"^(CLOSURE|CL) ?96\b"), "closure_96_lokal.png", 0.8),
              "closure_kecil": ((r"^(CLOSURE|CL) ?48$", r"^(CLOSURE|CL) ?48\b"), "closure_48_lokal.png", 0.8),
              "closure_144": ((r"^(CLOSURE|CL) ?144$", r"^(CLOSURE|CL) ?144\b"), "closure_144_lokal.png", 0.8),
              "closure_288": ((r"^(CLOSURE|CL) ?288$", r"^(CLOSURE|CL) ?288\b"), "closure_288_lokal.png", 0.8),
              "otb": ((r"^OTB ?144$", r"^OTB\b" + _TANPA_VARIAN), "otb_lokal.png", 0.8),
              "slack": ((r"^SPARE CABLE$", r"^(SPARE|SLACK)\b"), "slack_lokal.png", 0.8),
              "tiang6": ((r"^6M$", r"^ICONFTTH ?6M$", r"^6M\b", r"^POLE 6\b" + _TANPA_VARIAN), "tiang6_lokal.png", 0.5),
              "tiang7": ((r"^ICONFTTH ?7M$", r"^ICONFTTH ?7M\b", r"^7M$", r"^7M\b", r"^POLE 7\b" + _TANPA_VARIAN),
                         "tiang7_lokal.png", 0.5),
              "tiang9": ((r"^ICONFTTH ?9M$", r"^ICONFTTH ?9M\b", r"^9M$", r"^9M\b", r"^POLE 9\b" + _TANPA_VARIAN),
                         "tiang9_lokal.png", 0.5)}


def _nama_ikon(n):
    """'ICONFTTH-7M.png' -> 'ICONFTTH 7M'; 'OTB_144.png' -> 'OTB 144' (huruf besar, pemisah jadi satu spasi)."""
    import re
    return re.sub(r"[\s_-]+", " ", os.path.splitext(os.path.basename(n))[0].upper()).strip()


def pilih_ikon(lokal):
    """{nama berkas: bytes} -> {jenis: (nama berkas di KMZ, skala, bytes)} untuk ikon pengguna yang dikenali.
    Urutan sumber dihormati (folder ikon Tembuku lebih dulu, lalu folder ikon di sekitar data), jadi pilihan ikon
    sama di setiap wilayah/cluster; di dalam satu sumber nama berkas diurutkan."""
    import re
    out = {}
    nama_urut = list(lokal or {})
    for jenis, (pola, netral, skala) in IKON_LOKAL.items():
        for p in (pola if isinstance(pola, tuple) else (pola,)):
            nama = next((n for n in nama_urut if re.search(p, _nama_ikon(n))), None)
            if nama:
                # nama berkas ikon asli pengguna dipakai di KMZ (seperti hasil desainer: files/Closure 96.png)
                asli = re.sub(r"[^\w .()-]", "_", os.path.basename(nama)) or netral
                out[jenis] = (asli, skala, lokal[nama])
                break
    return out


SKALA = {"fdt": 0.5, "pop": 1.2, "closure": 0.8, "otb": 0.8, "slack": 0.8, "tap": 1.1, "tiang": 0.5}
WARNA_INFRA = {"TIANG_NASIONAL": "b3ffff00", "TIANG_COMPILE": "b3ffaa55", "NEW_INFRA": "b300ff55",
               "GARIS_BANTU": "ff0000ff", "COLO_CABLE": "b37fffff", "ROUTE_EXISTING": "ff0080ff"}
IKON = {k: "files/%s.png" % k for k in ikon.BENTUK}
WARNA_IKON = {"slack": "ff00ffff", "closure": "ff00aaff", "otb": "ffff8800", "fdt": "ff00ffff",
              "pop": "ff0000ff", "tap": "ffff00ff", "tiang": "ff00ff55"}
# Ikon standar Google Earth menurut template APD (Resume Template APD Feeder 29-12-2025): New Hanger 'forbidden' skala
# 0,8 (juga dipakai 321 dari 321 titik hanger di 4 compile) dan OLT 'homegardenbusiness' skala 1,2.
IKON_APD = {"hanger": ("http://maps.google.com/mapfiles/kml/shapes/forbidden.png", 0.8),
            "olt": ("http://maps.google.com/mapfiles/kml/shapes/homegardenbusiness.png", 1.2)}
WARNA_EKSISTING = "ff00ffff"            # objek eksisting di compile diberi warna ikon ini (closure, FDT)
WARNA_LABEL_EXT = "ff0000ff"            # label 'Ext Closure' merah (KML aabbggrr), seperti data desainer


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
        """Style ikon: semua simbol dari set ikon tim (ICON_FTTH) bila tersedia - slack/hanger 'Spare Cable', OLT 'OLT',
        closure/FDT/OTB/tiang sesuai kapasitas; ikon template Google ('forbidden', OLT) hanya bila set tim tidak ada.
        eks=True: varian objek eksisting (warna ikon seperti di compile)."""
        if jenis in ("slack", "hanger"):    # arahan pengguna 19-11-2026: ikon hanya dari set tim -> 'Spare Cable'
            return self.lokal.get("slack", "apd_hanger")
        if jenis == "pop":                  # OLT: ikon tim 'OLT', selain itu ikon template
            return self.lokal.get("pop", "apd_olt")
        st = None
        if jenis == "closure" and core:      # 12-48 'Closure 48', 96 'Closure 96', 144 'CL_144' (bila ada), 288 'CL_288'
            j = "closure_288" if core >= 288 else ("closure_144" if core >= 144 and "closure_144" in self.lokal else
                                                   ("closure_kecil" if core <= 48 else "closure"))
            st = self.lokal.get(j)
        if st is None and jenis.startswith("tiang"):
            st = self.lokal.get(jenis, "ikon_tiang")
        if st is None:
            st = self.lokal.get(jenis, "ikon_" + jenis)
        if eks == "ext" and st.startswith("lokal_"):
            return st + "_ext"              # Ext Closure: label merah, ikon kuning, skala 0,8 (data desainer)
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


# Gaya garis tanpa ikon pushpin Google (arahan pengguna 19-11-2026: semua simbol hanya dari set ikon tim). Ikon pada gaya
# garis tidak tampil di peta, jadi tampilan garis tidak berubah.
PIN = ""


def _styles(w, lokal=None):
    lokal = lokal or {}
    for c, col in WARNA_CORE.items():
        w.a('<Style id="kabel%d">%s<LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (c, PIN, col, LEBAR_KABEL))
    for nm, col in WARNA_INFRA.items():
        w.a('<Style id="infra_%s">%s<LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (nm, PIN, col, 3 if nm == "GARIS_BANTU" else (4 if nm == "ROUTE_EXISTING" else 10)))
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
        # 'Ext Closure' seperti placemark desainer (revisi 23-11-2026): label merah, ikon kuning, keduanya skala 0,8
        w.a('<Style id="lokal_%s_ext"><IconStyle><color>%s</color><scale>0.8</scale><Icon><href>files/%s</href></Icon>'
            '</IconStyle><LabelStyle><color>%s</color><scale>0.8</scale></LabelStyle></Style>'
            % (k, WARNA_EKSISTING, netral, WARNA_LABEL_EXT))
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


def _potong_fraksi(ll, rute):
    """Garis lon/lat dipotong menurut [{label, s0, s1}] (posisi 0..1 di sepanjang garis) -> [(label, potongan)].
    Potongan bersambung ujung ke ujung (tanpa celah); [] bila tidak ada pembagian yang sah."""
    if not rute or not ll or len(ll) < 2:
        return []
    cum = [0.0]
    for a, b in zip(ll, ll[1:]):
        cum.append(cum[-1] + geo.haversine(a, b))
    total = cum[-1]
    if total <= 0:
        return []

    def titik(s):
        for i in range(len(ll) - 1):
            if cum[i] <= s <= cum[i + 1]:
                d = cum[i + 1] - cum[i]
                t = 0.0 if d <= 0 else (s - cum[i]) / d
                return (ll[i][0] + t * (ll[i + 1][0] - ll[i][0]), ll[i][1] + t * (ll[i + 1][1] - ll[i][1])), i
        return ll[-1], len(ll) - 2
    out = []
    for j, r in enumerate(rute):
        s0 = 0.0 if j == 0 else float(r["s0"]) * total
        s1 = total if j == len(rute) - 1 else float(r["s1"]) * total
        if s1 - s0 < 1.0:
            continue
        p0, i0 = titik(s0)
        p1, i1 = titik(s1)
        pot = [p0] + [ll[k] for k in range(i0 + 1, i1 + 1)] + [p1]
        pot = [p for n, p in enumerate(pot) if n == 0 or p != pot[n - 1]]
        if len(pot) >= 2:
            out.append((r["label"], pot))
    return out


def _sepotong(kabel, ll, min_m=2.0):
    """Bagian garis kabel final (kabel = daftar garis lon/lat yang sudah dirapikan dan dilengkungkan) di antara proyeksi
    ujung awal dan ujung akhir ll. Colo Pole dan New Infra diambil dari sini supaya selalu berimpit persis dengan kabel
    barunya. -> garis lon/lat searah kabel, atau None bila terlalu pendek / tidak ada kabel."""
    import math
    if not kabel or len(ll) < 2:
        return None
    k = math.cos(math.radians(ll[0][1]))

    def m(p):
        return (p[0] * 111320.0 * k, p[1] * 110574.0)

    def b(q):
        return (q[0] / (111320.0 * k), q[1] / 110574.0)

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


def _rapat_ke_feeder(g, feeder, tol_m=12.0, min_m=30.0):
    """Bagian awal kabel baru (dari titik sambung) yang menyusuri tiang feeder yang sama digambar persis di atas garis
    feeder (COLO CABLE), supaya dua kabel di tiang yang sama tidak tampak sebagai dua jalur. Hanya bila bagian yang
    berimpit >= min_m; sisanya (menuju FDT) tidak diubah. Ujung awal (titik sambung) dan ujung akhir (FDT) tetap."""
    import math
    if not feeder or len(feeder) < 2 or not g or len(g) < 3:
        return g
    k = math.cos(math.radians(g[0][1]))

    def m(p):
        return (p[0] * 111320.0 * k, p[1] * 110574.0)

    def b(q):
        return (q[0] / (111320.0 * k), q[1] / 110574.0)
    F = [m(p) for p in feeder]
    G = [m(p) for p in g]
    cum = [0.0]
    for i in range(1, len(F)):
        cum.append(cum[-1] + math.hypot(F[i][0] - F[i - 1][0], F[i][1] - F[i - 1][1]))

    def proy(q):
        best = None
        for i in range(len(F) - 1):
            a, c = F[i], F[i + 1]
            dx, dy = c[0] - a[0], c[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
            d = math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)
            if best is None or d < best[0]:
                best = (d, cum[i] + t * math.sqrt(L2))
        return best

    d0, s_tap = proy(G[0])
    if d0 > tol_m:
        return g
    j, jarak = 0, 0.0
    for i in range(1, len(G)):
        if proy(G[i])[0] > tol_m:
            break
        jarak += math.hypot(G[i][0] - G[i - 1][0], G[i][1] - G[i - 1][1])
        j = i
    if j >= len(G) - 1:                 # seluruh kabel menyusuri feeder: rapatkan sampai titik sebelum FDT
        j = len(G) - 2
        jarak = sum(math.hypot(G[i][0] - G[i - 1][0], G[i][1] - G[i - 1][1]) for i in range(1, j + 1))
    if jarak < min_m or j < 1:
        return g
    s_lepas = proy(G[j])[1]

    def titik_s(s):
        for i in range(len(F) - 1):
            if cum[i] <= s <= cum[i + 1]:
                L = cum[i + 1] - cum[i]
                t = 0.0 if L <= 0 else (s - cum[i]) / L
                return (F[i][0] + t * (F[i + 1][0] - F[i][0]), F[i][1] + t * (F[i + 1][1] - F[i][1]))
        return F[-1] if s > cum[-1] else F[0]
    lo, hi = min(s_tap, s_lepas), max(s_tap, s_lepas)
    sub = [titik_s(lo)] + [F[i] for i in range(len(F)) if lo < cum[i] < hi] + [titik_s(hi)]
    if s_tap > s_lepas:
        sub = list(reversed(sub))
    # sambungan dari garis feeder ke jalur menuju FDT dihaluskan setempat (+-20 m), bagian yang berimpit tetap
    ekor = G[j + 1:]
    acc, k0 = 0.0, len(sub) - 1
    while k0 > 1 and acc < 20.0:
        acc += math.hypot(sub[k0][0] - sub[k0 - 1][0], sub[k0][1] - sub[k0 - 1][1])
        k0 -= 1
    acc, k1 = 0.0, 0
    while k1 < len(ekor) - 1 and acc < 20.0:
        acc += math.hypot(ekor[k1 + 1][0] - ekor[k1][0], ekor[k1 + 1][1] - ekor[k1][1])
        k1 += 1
    halus = _lengkung(sub[k0:] + ekor[:k1 + 1])
    xy = sub[:k0] + halus + ekor[k1 + 1:]
    return [g[0]] + [b(q) for q in xy[1:-1]] + [g[-1]]


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


def kelompok_proyek(hasil, prm):
    """1.6.1: FDT satu proyek (berkas FDT yang sama, POP dan feeder yang sama) digabung menjadi SATU traksi/berkas
    hasil, seperti desainer ('F5_T1-T2_..._Jl. Mesjid Al Huda'). -> [[h, ...], ...] dengan urutan masukan."""
    if not prm.get("gabung_proyek", True):
        return [[h] for h in hasil]
    grup, urut = {}, []
    for h in hasil:
        n = h.get("penomoran") or {}
        pid = h["fdt"].get("_proyek_id")       # hanya FDT yang dirancang sebagai satu proyek (bukan uji akurasi)
        if h["keputusan"] in ("COLO", "COLO_CEK", "COLO_MANUAL", "FEEDER_BARU") and pid and n.get("feeder"):
            kunci = (pid, n.get("pop_folder"), n.get("feeder"))
        else:
            kunci = ("_sendiri", id(h))
        if kunci not in grup:
            grup[kunci] = []
            urut.append(kunci)
        grup[kunci].append(h)
    return [grup[k] for k in urut]


LEWAT_FDT_M = 20.0     # FDT proyek sedekat ini dari kabel utama dilewati kabel itu (satu garis, tanpa ekor)


def _teks_t(ts):
    ts = sorted(set(int(t) for t in ts if t))
    if len(ts) > 1 and ts == list(range(ts[0], ts[-1] + 1)):
        return "T%d-T%d" % (ts[0], ts[-1])
    return ",".join("T%d" % t for t in ts)


def nama_traksi_grup(hs, prm, tgl=None):
    nm = nama_traksi(hs[0], prm, tgl)
    if len(hs) < 2:
        return nm
    n = hs[0]["penomoran"]
    return nm.replace("F%d_T%d_" % (n["feeder"], n["t"]), "F%d_%s_" % (n["feeder"], _teks_t(
        [h["penomoran"].get("t") for h in hs])), 1)


def _numpang_proyek(h):
    """True bila FDT ini menyambung ke kabel baru FDT lain di proyek yang sama (kabelnya sama, tidak digambar ulang)."""
    return ((h.get("terpilih") or {}).get("tap_slack") or {}).get("jenis") == "usulan"


def _gabung_xml(a, b):
    """Gabung pohon Folder b ke a: folder bernama sama digabung, placemark kembar (nama + geometri sama) dilewati."""
    import xml.etree.ElementTree as ET  # noqa: F401
    for c in list(b):
        if c.tag == "Folder":
            nm = c.findtext("name")
            sama = next((x for x in a.findall("Folder") if x.findtext("name") == nm), None)
            if sama is None:
                a.append(c)
            else:
                _gabung_xml(sama, c)
        elif c.tag == "Placemark":
            kunci = (c.findtext("name"), "".join(c.itertext()))
            if not any(x.tag == "Placemark" and (x.findtext("name"), "".join(x.itertext())) == kunci for x in a):
                a.append(c)


def _isi_grup(w, hs, prm):
    """Folder 'Feeder' untuk satu traksi berisi satu FDT atau beberapa FDT satu proyek (digabung per folder template)."""
    if len(hs) == 1:
        L = geo.Lokal(*hs[0]["lokal"])
        w.folder("Feeder", lambda: _isi_traksi(w, hs[0], prm, L.balik))
        return
    import xml.etree.ElementTree as ET
    # FDT proyek yang menempel kabel utama (<= LEWAT_FDT_M): kabel utama dilewatkan ke FDT itu, ekornya tidak ditulis
    dekat = {id(h) for h in hs[1:] if _numpang_proyek(h) and
             float((h.get("terpilih") or {}).get("kabel_baru_m") or 0) <= LEWAT_FDT_M}
    lewat = [h["fdt"]["ll"] for h in hs if id(h) in dekat]
    akar = None
    for i, h in enumerate(hs):
        w2 = _W()
        w2.__dict__.update({k: v for k, v in w.__dict__.items() if k != "o"})
        w2.o = []
        L = geo.Lokal(*h["lokal"])
        w2.folder("Feeder", lambda w2=w2, h=h, L=L, i=i: _isi_traksi(
            w2, h, prm, L.balik, sekunder=i > 0 and _numpang_proyek(h), lewat=lewat if i == 0 else None,
            tanpa_kabel=id(h) in dekat))
        pohon = ET.fromstring("".join(w2.o))
        if akar is None:
            akar = pohon
        else:
            _gabung_xml(akar, pohon)
    w.a(ET.tostring(akar, encoding="unicode"))


def _jarak_ruas(q, a, b):
    """Jarak titik q ke ruas a-b (lon/lat) dalam meter."""
    lat0 = math.radians(q[1])
    kx, ky = 111320.0 * math.cos(lat0), 110574.0
    ax, ay, bx, by = (a[0] - q[0]) * kx, (a[1] - q[1]) * ky, (b[0] - q[0]) * kx, (b[1] - q[1]) * ky
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
    return math.hypot(ax + t * dx, ay + t * dy)


def _isi_traksi(w, h, prm, ke_ll, sekunder=False, lewat=None, tanpa_kabel=False):
    """Isi satu folder traksi sesuai template compile. ke_ll: lokal(m) -> (lon,lat).
    sekunder=True: FDT ini menyambung ke kabel baru FDT lain di proyek yang sama (traksi gabungan) - COLO CABLE dan
    Informasi Route Existing-nya sama dengan milik FDT pertama, jadi tidak ditulis ulang."""
    f, pop = h["fdt"], h["pop"]
    sel = h.get("terpilih")
    baru = h["keputusan"] == "FEEDER_BARU"
    rute = sel["rute"] if sel else (h["feeder_baru"] if baru else None)
    core_cab = int(mesin.core_feeder_baru(h, prm) if baru else ((sel or {}).get("core_cabang") or prm["core_cabang"]))
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
    # COLO CABLE digambar sekali; bagian kabel baru yang menyusuri tiang feeder yang sama dirapatkan ke garis itu
    colo_final = None
    if sel and sel.get("colo_xy") and len(sel["colo_xy"]) >= 2:
        colo_final = _bersihkan_ll([ke_ll(p) for p in rapikan_garis(sel.get("colo_gambar_xy") or sel["colo_xy"])])
        if not baru:
            kab_final = {c: [_rapat_ke_feeder(g, colo_final) for g in daftar] for c, daftar in kab_final.items()}
    semua_final = [g for daftar in kab_final.values() for g in daftar]
    # 1.6.1 satu proyek: FDT lain yang hanya beberapa meter dari kabel ini dilewati kabel utama (masuk ke closure FDT
    # itu, lalu lanjut) - satu garis kabel, bukan kabel utama + ekor pendek
    for q in lewat or ():
        terbaik = None
        for c_, daftar in kab_final.items():
            for g in daftar:
                for i in range(len(g) - 1):
                    d = _jarak_ruas(q, g[i], g[i + 1])
                    if terbaik is None or d < terbaik[0]:
                        terbaik = (d, g, i)
        if terbaik is not None:
            terbaik[1].insert(terbaik[2] + 1, (float(q[0]), float(q[1])))
    if tanpa_kabel:       # kabelnya sudah digambar sebagai bagian kabel utama proyek
        kab_final, semua_final, infra = {}, [], []
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
            # nama 'COLO CABLE'; keterangan = rute kabel feeder yang dilalui (arahan atasan 18-11-2026), mis.
            # 'Colo Cable F6 Feeder Perumahan karlia asri'; melewati beberapa cluster -> satu garis per cluster sesuai
            # urutan rute dari POP
            if sel and sel.get("colo_xy") and not sekunder:
                garis_colo = colo_final or [ke_ll(p) for p in rapikan_garis(sel["colo_xy"])]
                potong = _potong_fraksi(garis_colo, sel.get("colo_route") or [])
                if potong:
                    for label, ll in potong:
                        w.garis("COLO CABLE", ll, "infra_COLO_CABLE", label, final=True)
                else:
                    tr = re.sub(r"\.km[lz]$", "", str(sel.get("traksi") or sel.get("nama") or ""), flags=re.I)
                    w.garis("COLO CABLE", garis_colo, "infra_COLO_CABLE", tr, final=bool(colo_final))
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
                    w.titik("Slack", _ke_kabel(q, semua_final), w.ik("hanger"),
                            "Hanger di sekitar %d m dari awal kabel baru" % jarak)
            w.titik("Slack", f["ll"], w.ik("slack"), "Slack %d m di FDT" % prm["slack_m"])
        w.folder("New Hanger", nh)
        w.folder("Eksisting Hanger", lambda: None)
    w.folder("Hanger", hanger)

    def closure():
        def nc():
            for c in CORE:
                def isi(c=c):
                    # seperti hasil desainer: New Closure 96 di FDT. Revisi 23-11-2026: titik sambung di slack (feeder
                    # cluster lain), di ujung kabel atau di tengah kabel mendapat New Closure baru; hanya closure yang
                    # sudah ada yang ditulis sebagai Ext Closure
                    if c == core_tap and h["keputusan"] != "PERLU_MANUAL" and (sel or baru):
                        dekat_fdt = (ts or {}).get("jenis") == "usulan" and tap_ll and \
                            geo.haversine(tap_ll, f["ll"]) < 20.0     # closure FDT sekaligus titik sambung
                        if tap_ll and not baru and (not ts or ts.get("jenis") != "closure") and not dekat_fdt:
                            w.titik("New Closure", tap_ll, w.ik("closure", c))
                        w.titik("New Closure", f["ll"], w.ik("closure", c))
                    if baru and c == 144 and kab_baru.get(144):
                        w.titik("New Closure", kab_baru[144][0][-1], w.ik("closure", 144))
                w.folder("New Closure %d" % c, isi)
        w.folder("New Closure", nc)
        # revisi 23-11-2026: hanya CLOSURE existing yang dipakai sebagai titik sambung = 'Ext Closure' dengan ikon sesuai
        # kapasitasnya (Closure 96 -> Ext Closure 96); slack bukan closure, jadi tidak ditulis di sini
        core_ext = _core_bulat(int((ts or {}).get("core") or core_tap))
        w.folder("Eksisting Closure", lambda: (w.titik("Ext Closure", tap_ll, w.ik("closure", core_ext, eks="ext"),
                                                       "Closure %d existing di compile, dipakai sebagai titik sambung"
                                                       % core_ext)
                                               if tap_ll and ts and ts.get("jenis") == "closure" and not baru else None))
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

    # arahan 18-11-2026: kabel existing (inventaris) yang dilalui rute, dengan NAME dan DESCR2 di tabel balonnya
    info = (sel or {}).get("route_existing") if sel else ((h.get("feeder_baru") or {}).get("route_existing") if baru else None)
    if not prm.get("tulis_route_existing", True) or sekunder:   # opsional sejak 1.6.1; sekunder: sama dengan FDT pertama
        return bantu, [ll for kelas, _c, ll, _r in infra if kelas == "NEW_INFRA"], tiang
    w.folder(FOLDER_ROUTE_EXISTING, lambda: [
        w.garis(d["nama"], d["ll"], "infra_ROUTE_EXISTING", data={"NAME": d["nama"], "DESCR2": d["descr2"]},
                final=True)     # titiknya sudah dari garis rute yang digambar (bersih); tidak dipangkas lagi
        for d in (info or []) if h["keputusan"] != "PERLU_MANUAL" and len(d.get("ll") or []) >= 2])
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
        if inti[-1:] == [FOLDER_ROUTE_EXISTING]:  # folder keterangan arahan 18-11-2026, selalu paling akhir
            inti = inti[:-1]
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
                    if analisis:
                        for h in hs:
                            L = geo.Lokal(*h["lokal"])
                            bantu, infra_baru, tiang = _isi_traksi(_W(), h, prm, L.balik)
                            _analisis_folder(w, h, L.balik, bantu, infra_baru, tiang)
                        return
                    for grp in kelompok_proyek(hs, prm):     # FDT satu proyek = satu traksi (mis. F1_T2-T3)
                        w.folder(nama_traksi_grup(grp, prm), lambda grp=grp: _isi_grup(w, grp, prm))
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
    Distribution dan semua berkas di KMZ masukan tetap apa adanya; hanya folder Feeder (template kosong) diganti.
    h boleh daftar hasil satu proyek (1.6.1): folder Feeder berisi gabungan semua FDT proyek itu."""
    hs = h if isinstance(h, list) else [h]
    h = hs[0]
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
    _isi_grup(w, hs, prm)
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
