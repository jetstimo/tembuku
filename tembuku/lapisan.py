# -*- coding: utf-8 -*-
# Tembuku - layer hasil di QGIS. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Hasil ditampilkan sebagai layer memori bergaya (WGS 84) dalam grup 'Tembuku': jalur usulan per jenis infrastruktur,
colo cable POP->tap, kandidat feeder, dan titik FDT/POP/tap. Gaya = warna laporan & slide 16."""
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsField, QgsGeometry, QgsLineSymbol,
                       QgsMarkerSymbol, QgsPalLayerSettings, QgsPointXY, QgsProject, QgsRendererCategory,
                       QgsSingleSymbolRenderer, QgsVectorLayer, QgsVectorLayerSimpleLabeling)

try:                                            # Qt5 / QGIS 3
    from qgis.PyQt.QtCore import QVariant
    _STR, _INT = QVariant.String, QVariant.Int
except (ImportError, AttributeError):           # Qt6 / QGIS 4
    from qgis.PyQt.QtCore import QMetaType
    _STR, _INT = QMetaType.Type.QString, QMetaType.Type.Int


class _T(object):           # tipe field Qt5/Qt6
    String, Int = _STR, _INT

from .inti import geo, mesin
from .plugin import KEPUTUSAN_EN

WARNA = {"TIANG_COMPILE": "#0e7c7b", "TIANG_NASIONAL": "#00b4d8", "NEW_INFRA": "#22c55e", "GARIS_BANTU": "#ef4444",
         "Colo Cable": "#a855f7", "Kandidat lolos": "#f59e0b", "Kandidat ditolak": "#9ca3af", "FDT": "#c2410c",
         "POP": "#1d4ed8", "TAP": "#111827"}


def _layer(geom, nama, fields):
    lyr = QgsVectorLayer("%s?crs=EPSG:4326" % geom, nama, "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([QgsField(n, t) for n, t in fields])
    lyr.updateFields()
    return lyr


def _isi(lyr, rows):
    feats = []
    for geomobj, attrs in rows:
        f = QgsFeature(lyr.fields())
        f.setGeometry(geomobj)
        f.setAttributes(attrs)
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    lyr.updateExtents()


def _garis(ll):
    return QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in ll])


def _gaya_kategori(lyr, field, kategori, garis=True):
    cats = []
    for nilai, (warna, lebar, gaya) in kategori.items():
        if garis:
            sym = QgsLineSymbol.createSimple({"color": warna, "width": str(lebar), "line_style": gaya,
                                              "capstyle": "round", "joinstyle": "round"})
        else:
            sym = QgsMarkerSymbol.createSimple({"name": gaya, "color": warna, "size": str(lebar),
                                                "outline_color": "#ffffff", "outline_width": "0.5"})
        cats.append(QgsRendererCategory(nilai, sym, nilai))
    lyr.setRenderer(QgsCategorizedSymbolRenderer(field, cats))


def _label(lyr, field):
    s = QgsPalLayerSettings()
    s.fieldName = field
    s.enabled = True
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def tampilkan(hasil, judul="Tembuku", ganti=None):
    """Tambahkan layer hasil ke proyek dalam satu grup. ganti: nama grup yang diganti (mode pratinjau klik-peta)."""
    proj = QgsProject.instance()
    root = proj.layerTreeRoot()
    if ganti:
        g = root.findGroup(ganti)
        if g is not None:
            for lyr_node in g.findLayers():
                proj.removeMapLayer(lyr_node.layerId())
            root.removeChildNode(g)
    grp = root.insertGroup(0, judul)
    jalur = _layer("LineString", "Proposed cable route", [("fdt", _T.String), ("keputusan", _T.String),
                                                  ("kelas", _T.String), ("panjang_m", _T.Int)])
    colo = _layer("LineString", "Existing feeder used (POP to tap)", [("fdt", _T.String), ("kabel", _T.String),
                                                        ("panjang_m", _T.Int)])
    kand = _layer("LineString", "Candidate feeders", [("fdt", _T.String), ("no", _T.Int),
                                                     ("nama", _T.String), ("status", _T.String),
                                                     ("kapasitas", _T.String), ("kabel_baru_m", _T.Int),
                                                     ("alasan", _T.String)])
    titik = _layer("Point", "FDT, POP and tap points", [("jenis", _T.String), ("label", _T.String),
                                               ("fdt", _T.String), ("keputusan", _T.String)])
    desain = _layer("LineString", "Designer's own design (for comparison)", [("fdt", _T.String), ("jenis", _T.String)])
    rd = []
    rj, rc, rk, rt = [], [], [], []
    for h in hasil:
        L = geo.Lokal(*h["lokal"])
        kode = h["fdt"]["kode"]
        sel = h.get("terpilih")
        rute = sel["rute"] if sel else (h["feeder_baru"] if h["keputusan"] == "FEEDER_BARU" else None)
        if rute:
            for kelas, _ref, xy in rute["segmen"]:
                ll = [L.balik(p) for p in xy]
                rj.append((_garis(ll), [kode, h["keputusan"], mesin.label_kelas(kelas), int(geo.panjang_deg(ll))]))
        if sel and sel.get("colo_xy"):
            ll = [L.balik(p) for p in sel["colo_xy"]]
            rc.append((_garis(ll), [kode, sel["nama"] or sel["id"], int(geo.panjang_deg(ll))]))
        for i, k in enumerate(h["kandidat"][:6]):
            st = "Candidate passes" if k["lolos"] else "Candidate rejected"
            rk.append((_garis(k["ll_kabel"]), [kode, i + 1, k["nama"] or k["id"], st, k["ket_kapasitas"],
                                               k["kabel_baru_m"], "; ".join(k["gagal"] + k["catatan"])[:250]]))
            tp = L.balik(k["rute"]["titik"][0])
            rt.append((QgsGeometry.fromPointXY(QgsPointXY(tp[0], tp[1])), ["TAP", "tap #%d" % (i + 1), kode,
                                                                            h["keputusan"]]))
        g = h["fdt"].get("_uji")
        if g:
            for ll in g["kabel_baru"]:
                rd.append((_garis(ll), [kode, "new cable"]))
            for ll in g["colo"]:
                rd.append((_garis(ll), [kode, "existing feeder used"]))
        f = h["fdt"]["ll"]
        rt.append((QgsGeometry.fromPointXY(QgsPointXY(f[0], f[1])), ["FDT", "%s (%s)" % (kode, KEPUTUSAN_EN.get(h["keputusan"], h["keputusan"])), kode,
                                                                      h["keputusan"]]))
        if h["pop"]:
            p = h["pop"]["ll"]
            rt.append((QgsGeometry.fromPointXY(QgsPointXY(p[0], p[1])), ["POP", h["pop"]["nama"], kode, ""]))
    _isi(jalur, rj)
    _isi(colo, rc)
    _isi(kand, rk)
    _isi(titik, rt)
    _isi(desain, rd)
    _gaya_kategori(desain, "jenis", {"new cable": ("#111111", 0.8, "dash"), "existing feeder used": ("#555555", 0.5, "dot")})
    _gaya_kategori(jalur, "kelas", {mesin.label_kelas(k): (WARNA[k], 1.6 if k != "GARIS_BANTU" else 0.9,
                                                           "dash" if k == "GARIS_BANTU" else "solid")
                                    for k in ("TIANG_COMPILE", "TIANG_NASIONAL", "NEW_INFRA", "GARIS_BANTU")})
    colo.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": WARNA["Colo Cable"], "width": "1.2"})))
    _gaya_kategori(kand, "status", {"Candidate passes": (WARNA["Kandidat lolos"], 1.0, "solid"),
                                    "Candidate rejected": (WARNA["Kandidat ditolak"], 0.5, "dot")})
    _gaya_kategori(titik, "jenis", {"FDT": (WARNA["FDT"], 4.5, "square"), "POP": (WARNA["POP"], 5.0, "star"),
                                    "TAP": (WARNA["TAP"], 2.6, "circle")}, garis=False)
    _label(titik, "label")
    for lyr in (titik, jalur, colo, kand) + ((desain,) if rd else ()):
        proj.addMapLayer(lyr, False)
        grp.addLayer(lyr)
    return grp, [titik, jalur, colo, kand]
