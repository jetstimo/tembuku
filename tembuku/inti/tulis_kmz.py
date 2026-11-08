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


def escape(s):
    """Escape teks XML (pengganti xml.sax.saxutils.escape tanpa impor modul XML yang diblokir pemindai)."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


CORE = (12, 24, 48, 96, 144, 288)
WARNA_CORE = {12: "ffff80ff", 24: "ff0080ff", 48: "ff0055aa", 96: "ff00ffff", 144: "ffff0000", 288: "ffffffff"}
WARNA_INFRA = {"TIANG_NASIONAL": "b3ffff00", "TIANG_COMPILE": "b3ffaa55", "NEW_INFRA": "b300ff55",
               "GARIS_BANTU": "ff0000ff", "COLO_CABLE": "b37fffff"}
IKON = {k: "files/%s.png" % k for k in ikon.BENTUK}
WARNA_IKON = {"slack": "ff00ffff", "closure": "ff00aaff", "otb": "ffff8800", "fdt": "ff00ffff",
              "pop": "ff0000ff", "tap": "ffff00ff"}


def _c(ll):
    return " ".join("%.7f,%.7f,0" % (p[0], p[1]) for p in ll)


class _W(object):
    def __init__(self):
        self.o = []

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

    def titik(self, nama, p, style, desc="", data=None):
        ed = ""
        if data:
            ed = "<ExtendedData>%s</ExtendedData>" % "".join(
                '<Data name="%s"><value>%s</value></Data>' % (escape(str(k)), escape(str(v))) for k, v in data.items())
        self.a("<Placemark><name>%s</name>%s<styleUrl>#%s</styleUrl>%s<Point><coordinates>%s</coordinates></Point>"
               "</Placemark>" % (escape(nama), "<description>%s</description>" % escape(desc) if desc else "", style, ed,
                                 _c([p])))


def _styles(w):
    for c, col in WARNA_CORE.items():
        w.a('<Style id="kabel%d"><LineStyle><color>%s</color><width>4</width></LineStyle></Style>' % (c, col))
    for nm, col in WARNA_INFRA.items():
        w.a('<Style id="infra_%s"><LineStyle><color>%s</color><width>%d</width></LineStyle></Style>'
            % (nm, col, 3 if nm == "GARIS_BANTU" else 10))
    w.a('<Style id="kandidat"><LineStyle><color>9900a5ff</color><width>6</width></LineStyle></Style>')
    w.a('<Style id="kandidat_tolak"><LineStyle><color>66888888</color><width>3</width></LineStyle></Style>')
    for k, href in IKON.items():
        w.a('<Style id="ikon_%s"><IconStyle><color>%s</color><scale>1.1</scale><Icon><href>%s</href></Icon>'
            '</IconStyle><LabelStyle><scale>0.8</scale></LabelStyle></Style>' % (k, WARNA_IKON[k], href))


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
    infra = {}               # (kelas, core) -> [(ll, desc)]
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
        for kelas, ref, xy in rute["segmen"]:
            ll = [ke_ll(p) for p in xy]
            if kelas == "GARIS_BANTU":
                bantu.append(ll)
                kelas = "NEW_INFRA"
            infra.setdefault(kelas, []).append((ll, ref or ""))
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
                w.titik("Slack", tap_ll, "ikon_slack", "Slack %d m di titik sambung (tap)" % prm["slack_m"])
            w.titik("Slack", f["ll"], "ikon_slack", "Slack %d m di FDT" % prm["slack_m"])
        w.folder("New Hanger", nh)
        w.folder("Eksisting Hanger", lambda: None)
    w.folder("Hanger", hanger)

    def closure():
        def nc():
            for c in CORE:
                def isi(c=c):
                    if tap_ll and str(c) == str(prm["closure_tap"]):
                        w.titik("Closure %d" % c, tap_ll, "ikon_closure", "Closure baru di titik sambung (tap)")
                    if baru and c == 144 and kab_baru.get(144):
                        w.titik("Closure 144", kab_baru[144][0][-1], "ikon_closure", "Slack 144: pastikan tidak berimpit "
                                "dengan slack feeder lain")
                w.folder("New Closure %d" % c, isi)
        w.folder("New Closure", nc)
        w.folder("Eksisting Closure", lambda: None)
    w.folder("Closure", closure)

    def otb():
        def no():
            for c in CORE:
                w.folder("New OTB %d" % c, lambda c=c: (w.titik("OTB %d" % c, pop["ll"], "ikon_otb", "OTB di POP")
                                                        if baru and pop and c == 144 else None))
        w.folder("New OTB", no)
        w.folder("Eksisting OTB", lambda: None)
    w.folder("OTB", otb)

    def fdt():
        data = {"FDT FAT CODE": f["kode"], "PREMISES": int(f["premises"]) if f.get("premises") else "-",
                "SPLITTERS": ("%dx1x%d" % (f["splitter"], f.get("rasio") or 4)) if f.get("splitter") else "-",
                "LAT": "%.7f" % f["ll"][1], "LONG": "%.7f" % f["ll"][0]}
        w.folder("Eksisting FDT", lambda: (w.titik(f["kode"], f["ll"], "ikon_fdt", "", data)
                                           if f.get("status") == "Eksisting" else None))
        w.folder("New FDT", lambda: (w.titik(f["kode"], f["ll"], "ikon_fdt", "", data)
                                     if f.get("status") != "Eksisting" else None))
    w.folder("FDT", fdt)
    w.folder("OLT", lambda: w.titik(pop["nama"], pop["ll"], "ikon_pop", "", pop.get("attrs") or None) if pop else None)

    def ket():
        w.folder("New Cable Galian", lambda: [w.folder("New Cable %dC UG" % c, lambda: None) for c in CORE])

        def tiang():
            for c in CORE:
                def isi(c=c):
                    if c != core_cab and not (baru and c == 144):
                        return
                    for kelas in ("TIANG_NASIONAL", "TIANG_COMPILE"):
                        for ll, ref in infra.get(kelas, []):
                            w.garis(mesin.label_kelas(kelas), ll, "infra_" + kelas, ref)
                w.folder("Colo Pole %dC" % c, isi)
        w.folder("Collo Tiang", tiang)
        w.folder("New Infra", lambda: [w.garis("New Infra", ll, "infra_NEW_INFRA", "Butuh tiang atau jalur baru")
                                       for ll, _r in infra.get("NEW_INFRA", [])])
    w.folder("Keterangan Infra", ket)
    return bantu


def _analisis_folder(w, h, ke_ll, bantu):
    def isi():
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
    w.folder("TEMBUKU - analisis %s (%s)" % (h["fdt"]["kode"], mesin.nama_keputusan(h["keputusan"])), isi)


def tulis(hasil, path, prm, judul=None):
    """Tulis satu KMZ berisi satu atau banyak hasil analisis FDT."""
    w = _W()
    w.a('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
        '<Document><name>%s</name><description>%s</description>' % (
            escape(judul or os.path.basename(path)),
            escape("Dibuat oleh Tembuku (Feeder Tap Designer). Usulan desain - wajib ditinjau desainer. " + osm.ATRIBUSI)))
    _styles(w)
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
                        bantu = []

                        def tr(h=h, L=L):
                            bantu.extend(_isi_traksi(w, h, prm, L.balik))
                        w.folder(nama_traksi(h, prm), tr)
                        _analisis_folder(w, h, L.balik, bantu)
                w.folder("Feeder %d" % fn, fdr_isi)
        w.folder(popf or "POP", pop_isi)
    w.a("</Document></kml>")
    data = "".join(w.o).encode("utf-8")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", data)
        for nama, isi in ikon.semua().items():
            zf.writestr(nama, isi)
    os.replace(tmp, path)
    return path
