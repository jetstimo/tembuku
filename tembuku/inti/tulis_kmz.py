# -*- coding: utf-8 -*-
# Tembuku - penulis KMZ format Compile APD Feeder.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""KMZ hasil mengikuti template Compile APD Feeder organisasi (hierarki folder contoh Bitung/Tomohon 2026) agar dapat langsung
ditempel ke compile (slide 7/11): POP / Feeder N / F<n>_T<k>_<ID>_APD Feeder KMZ_<area>_<tgl> / Cable, Tiang, Hanger,
Closure, OTB, FDT, OLT, Keterangan Infra. Warna kabel = slide 16 'Format Warna Kabel' (KML aabbggrr).
KMZ: doc.kml entri pertama, DEFLATE, UTF-8 tanpa BOM; semua teks di-escape (tidak ada HTML/JS dari input)."""
import datetime
import os
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
# Ikon milik pengguna (opsional, dari folder 'ikon'; tidak ikut di plugin). Dikenali dari kata di nama berkasnya, apa pun
# imbuhannya, lalu ditanam ke KMZ dengan nama netral: jenis -> (pola nama berkas, nama di KMZ, skala template).
IKON_LOKAL = {"fdt": (r"^FDT\b", "fdt_lokal.png", 0.5), "pop": (r"^OLT\b|^POP\b", "olt_lokal.png", 1.2),
              "closure": (r"^(CLOSURE|CL)[ _-]*96\b", "closure_96_lokal.png", 0.8),
              "closure_kecil": (r"^(CLOSURE|CL)[ _-]*48\b", "closure_48_lokal.png", 0.8),
              "closure_288": (r"^(CLOSURE|CL)[ _-]*288\b", "closure_288_lokal.png", 0.8),
              "otb": (r"^OTB\b", "otb_lokal.png", 0.8), "slack": (r"^(SPARE|SLACK)\b", "slack_lokal.png", 0.8)}


def pilih_ikon(lokal):
    """{nama berkas: bytes} -> {jenis: (nama netral di KMZ, skala, bytes)} untuk ikon pengguna yang dikenali."""
    import re
    out = {}
    for jenis, (pola, netral, skala) in IKON_LOKAL.items():
        for nama in sorted(lokal or {}):
            if re.search(pola, os.path.splitext(nama)[0].upper().replace("_", " ")):
                out[jenis] = (netral, skala, lokal[nama])
                break
    return out


SKALA = {"fdt": 0.5, "pop": 1.2, "closure": 0.8, "otb": 0.8, "slack": 0.8, "tap": 1.1}
WARNA_INFRA = {"TIANG_NASIONAL": "b3ffff00", "TIANG_COMPILE": "b3ffaa55", "NEW_INFRA": "b300ff55",
               "GARIS_BANTU": "ff0000ff", "COLO_CABLE": "b37fffff"}
IKON = {k: "files/%s.png" % k for k in ikon.BENTUK}
WARNA_IKON = {"slack": "ff00ffff", "closure": "ff00aaff", "otb": "ffff8800", "fdt": "ff00ffff",
              "pop": "ff0000ff", "tap": "ffff00ff"}


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

    def ik(self, jenis, core=None):
        """Style ikon: ikon organisasi bila ada (closure mengikuti kapasitas seperti template), selain itu bawaan."""
        if jenis == "closure" and core:
            j = "closure_288" if core >= 288 else ("closure_kecil" if core <= 48 else "closure")
            if j in self.lokal:
                return self.lokal[j]
        return self.lokal.get(jenis, "ikon_" + jenis)

    def a(self, s):
        self.o.append(s)

    def folder(self, nama, isi):
        self.a("<Folder><name>%s</name>" % escape(nama))
        isi()
        self.a("</Folder>")

    def garis(self, nama, ll, style, desc=""):
        self.a("<Placemark><name>%s</name>%s<styleUrl>#%s</styleUrl><LineString><tessellate>1</tessellate>"
               "<coordinates>%s</coordinates></LineString></Placemark>"
               % (escape(nama), "<description>%s</description>" % escape(desc) if desc else "", style, _c(ll)))

    def titik(self, nama, p, style, desc="", data=None, persis=False):
        ed = ""
        if data:
            ed = "<ExtendedData>%s</ExtendedData>" % "".join(
                '<Data name="%s"><value>%s</value></Data>' % (escape(str(k)), escape(str(v))) for k, v in data.items())
        self.a("<Placemark><name>%s</name>%s<styleUrl>#%s</styleUrl>%s<Point><coordinates>%s</coordinates></Point>"
               "</Placemark>" % (escape(nama), "<description>%s</description>" % escape(desc) if desc else "", style, ed,
                                 _c_persis(p) if persis else _c([p])))


def _styles(w, lokal=None):
    lokal = lokal or {}
    for c, col in WARNA_CORE.items():
        w.a('<Style id="kabel%d"><LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (c, col, LEBAR_KABEL))
    for nm, col in WARNA_INFRA.items():
        w.a('<Style id="infra_%s"><LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (nm, col, 3 if nm == "GARIS_BANTU" else 10))
    w.a('<Style id="kandidat"><LineStyle><color>9900a5ff</color><width>6</width></LineStyle></Style>')
    w.a('<Style id="kandidat_tolak"><LineStyle><color>66888888</color><width>3</width></LineStyle></Style>')
    for k, href in IKON.items():
        w.a('<Style id="ikon_%s"><IconStyle><color>%s</color><scale>%s</scale><Icon><href>%s</href></Icon>'
            '</IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, WARNA_IKON[k], SKALA[k], href))
    for c, col in WARNA_CORE.items():                 # garis Colo Pole: warna kapasitas kabelnya, lebar template
        w.a('<Style id="kolo%d"><LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (c, col, LEBAR_KABEL))
    w.ikon_pakai = pilih_ikon(lokal)
    for k, (netral, skala, _isi) in w.ikon_pakai.items():     # ikon pengguna: tanpa pewarnaan, skala template
        w.a('<Style id="lokal_%s"><IconStyle><scale>%s</scale><Icon><href>files/%s</href></Icon></IconStyle>'
            '<LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, skala, netral))
        w.lokal[k] = "lokal_" + k


def _core_bulat(c):
    return min(CORE, key=lambda x: (abs(x - (c or 48)), x))


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
    core_cab = int(prm["core_feeder_baru"] if baru else prm["core_cabang"])
    kab_baru = {}            # core -> [ll]
    infra = []               # [(kelas, core, ll, keterangan)] berurutan dari awal rute
    bantu = []
    if rute:
        titik = [ke_ll(p) for p in rute["titik"]]
        if baru and len(titik) >= 2:
            # feeder baru digambar dari POP: titik rute berurutan POP -> FDT
            awal, sisa = geo.potong(titik, prm["stub_144_m"])
            kab_baru.setdefault(144, []).append(awal)
            if len(sisa) >= 2:
                kab_baru.setdefault(core_cab, []).append(sisa)
        else:
            kab_baru.setdefault(core_cab, []).append(titik)
        sisa_stub = float(prm["stub_144_m"]) if baru else 0.0      # bagian awal feeder baru memakai kabel 144
        for kelas, ref, xy in rute["segmen"]:
            ll = [ke_ll(p) for p in xy]
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

    def cable():
        def udara():
            for c in CORE:
                w.folder("New Cable %dC" % c, lambda c=c: [w.garis("%dC" % c, ll, "kabel%d" % c,
                                                                      "Kabel baru usulan Tembuku") for ll in kab_baru.get(c, [])])
        w.folder("New Cable Aerial/Udara", udara)

        def colo():
            if sel and sel.get("colo_xy"):
                w.garis("Colo Cable", [ke_ll(p) for p in sel["colo_xy"]], "infra_COLO_CABLE",
                        "Feeder yang dipakai dari POP ke titik sambung: %s %s (%s)" % (
                            sel["label_colo"], sel["nama"], sel["ket_kapasitas"]))
        w.folder("Collo Cable", colo)
        w.folder("UG Utilities", lambda: (w.folder("Manhole", lambda: None), w.folder("Handhole", lambda: None)))
    w.folder("Cable", cable)
    for m in (6, 7, 9):
        w.folder("Tiang %d Meter" % m, lambda m=m: (w.folder("New Tiang %d Meter" % m, lambda: None),
                                                    w.folder("Eksisting Tiang %d Meter" % m, lambda: None)))

    def hanger():
        def nh():
            if tap_ll:
                w.titik("Slack", tap_ll, w.ik("slack"), "Slack %d m di titik sambung (tap)" % prm["slack_m"])
            w.titik("Slack", f["ll"], w.ik("slack"), "Slack %d m di FDT" % prm["slack_m"])
        w.folder("New Hanger", nh)
        w.folder("Eksisting Hanger", lambda: None)
    w.folder("Hanger", hanger)

    def closure():
        def nc():
            for c in CORE:
                def isi(c=c):
                    if tap_ll and str(c) == str(prm["closure_tap"]):
                        w.titik("Closure %d" % c, tap_ll, w.ik("closure", c), "Closure baru di titik sambung (tap)")
                    if baru and c == 144 and kab_baru.get(144):
                        w.titik("Closure 144", kab_baru[144][0][-1], w.ik("closure", 144), "Slack 144: pastikan tidak berimpit "
                                "dengan slack feeder lain")
                w.folder("New Closure %d" % c, isi)
        w.folder("New Closure", nc)
        w.folder("Eksisting Closure", lambda: None)
    w.folder("Closure", closure)

    def otb():
        def no():
            for c in CORE:
                w.folder("New OTB %d" % c, lambda c=c: (w.titik("OTB %d" % c, pop["ll"], w.ik("otb"), "OTB di POP")
                                                        if baru and pop and c == 144 else None))
        w.folder("New OTB", no)
        w.folder("Eksisting OTB", lambda: None)
    w.folder("OTB", otb)

    def fdt():
        data = {"FDT FAT CODE": f["kode"], "PREMISES": int(f["premises"]) if f.get("premises") else "-",
                "SPLITTERS": ("%dx1x%d" % (f["splitter"], f.get("rasio") or 4)) if f.get("splitter") else "-",
                "LAT": repr(float(f["ll"][1])), "LONG": repr(float(f["ll"][0]))}
        w.folder("Eksisting FDT", lambda: (w.titik(f["kode"], f["ll"], w.ik("fdt"), "", data, persis=True)
                                           if f.get("status") == "Eksisting" else None))
        w.folder("New FDT", lambda: (w.titik(f["kode"], f["ll"], w.ik("fdt"), "", data, persis=True)
                                     if f.get("status") != "Eksisting" else None))
    w.folder("FDT", fdt)
    # titik OLT hanya nama dan lokasi (seperti template); kolom data mentah dari daftar POP tidak ikut disalin
    w.folder("OLT", lambda: w.titik(pop["nama"], pop["ll"], w.ik("pop"), "") if pop else None)

    def ket():
        w.folder("New Cable Galian", lambda: [w.folder("New Cable %dC UG" % c, lambda: None) for c in CORE])

        def tiang():
            for c in CORE:
                def isi(c=c):
                    for kelas, core, ll, ref in infra:
                        if core == c and kelas in ("TIANG_NASIONAL", "TIANG_COMPILE"):
                            w.garis(mesin.label_kelas(kelas), ll, "kolo%d" % c, ref)
                w.folder("Colo Pole %dC" % c, isi)
        w.folder("Collo Tiang", tiang)
    w.folder("Keterangan Infra", ket)
    return bantu, [ll for kelas, _c, ll, _r in infra if kelas == "NEW_INFRA"]


def _analisis_folder(w, h, ke_ll, bantu, infra_baru=()):
    def isi():
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
    masalah, jalur, traksi, kini = [], [], {}, None
    for m in re.finditer(r"<Folder><name>([^<]*)</name>|</Folder>", kml):
        if m.group(1) is None:
            jalur.pop()
            continue
        jalur.append(m.group(1).replace("&amp;", "&"))
        if "Feeder" in jalur[3:4] and len(jalur) > 4:
            traksi[kini].append("/".join(jalur[4:]))
        elif len(jalur) == 4 and jalur[3] == "Feeder":
            kini = "%s #%d" % (jalur[2], len(traksi) + 1)        # nama traksi bisa kembar: tiap kemunculan diperiksa
            traksi[kini] = []
    if not traksi:
        masalah.append("tidak ada folder Feeder di dalam folder traksi")
    for t, ada in traksi.items():
        inti = list(ada)
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
        '<Document><name>%s</name><description>%s</description>' % (
            escape(judul or os.path.basename(path)),
            escape("Dibuat oleh Tembuku (Feeder Tap Designer). Usulan desain - wajib ditinjau desainer. " + osm.ATRIBUSI)))
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
                            bantu, infra_baru = _isi_traksi(_W(), h, prm, L.balik)
                            _analisis_folder(w, h, L.balik, bantu, infra_baru)
                            continue

                        def tr(h=h, L=L):
                            w.folder("Feeder", lambda: _isi_traksi(w, h, prm, L.balik))
                        w.folder(nama_traksi(h, prm), tr)
                w.folder("Feeder %d" % fn, fdr_isi)
        w.folder(popf or "POP", pop_isi)
    w.a("</Document></kml>")
    data = "".join(w.o).encode("utf-8")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", data)
        for nama, isi in ikon.semua().items():
            zf.writestr(nama, isi)
        for netral, _skala, isi in w.ikon_pakai.values():
            if "files/" + netral not in zf.namelist():
                zf.writestr("files/" + netral, isi)
    os.replace(tmp, path)
    return path
