# -*- coding: utf-8 -*-
# Tembuku - panel hasil interaktif. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Right-hand panel: list of FDTs with their decisions, the reasons in plain words, and the candidate feeders.
Double-click another candidate to USE it (the designer always has the final say): the route is redrawn and the KMZ can
be saved again with that choice. Reasons and notes come from the results and are written in Indonesian."""
import os

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle
from qgis.PyQt import QtGui, QtWidgets
from qgis.PyQt.QtCore import QUrl

from . import qtc
from .inti import geo

from .plugin import KEPUTUSAN_EN as NAMA

WARNA = {"COLO": "#0f766e", "COLO_CEK": "#b45309", "COLO_MANUAL": "#7c3aed", "FEEDER_BARU": "#1d4ed8",
         "PERLU_MANUAL": "#b91c1c"}
KAPASITAS = {"LOLOS": "Free tubes available", "PENUH": "Full", "BELUM_TERVERIFIKASI": "Not verified",
             "BUKAN_FEEDER": "Not a feeder"}


def _esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PanelTembuku(QtWidgets.QDockWidget):
    def __init__(self, plugin):
        super().__init__("Tembuku")
        self.setObjectName("TembukuPanel")
        self.plugin = plugin
        self.iface = plugin.iface
        self.hasil = []
        self.keluaran = None
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        bar = QtWidgets.QHBoxLayout()
        self.b_data = QtWidgets.QPushButton("Design feeders...")
        self.b_data.setToolTip("Choose your data folder and run")
        self.b_klik = QtWidgets.QPushButton("Click an FDT on the map")
        self.b_klik.setToolTip("Turn on, then click where an FDT is for an instant recommendation")
        b_bantu = QtWidgets.QToolButton()
        b_bantu.setText("?")
        b_bantu.setToolTip("Help: how to read these results")
        b_bantu.clicked.connect(lambda: plugin.bantuan("results"))
        self.b_klik.setCheckable(True)
        self.b_data.clicked.connect(plugin.buka_dialog)
        self.b_klik.toggled.connect(plugin.mode_klik)
        bar.addWidget(self.b_data)
        bar.addWidget(self.b_klik)
        b_peta = QtWidgets.QToolButton()
        b_peta.setText("Basemap")
        b_peta.setToolTip("Add OpenStreetMap or satellite imagery under the results")
        b_peta.setPopupMode(qtc.e(QtWidgets.QToolButton, "ToolButtonPopupMode", "InstantPopup"))
        b_peta.setMenu(plugin.buat_menu_peta(b_peta))
        bar.addWidget(b_peta)
        bar.addWidget(b_bantu)
        lay.addLayout(bar)
        self.status = QtWidgets.QLabel("To start: press 'Design feeders...' and choose your data folder, or click an "
                                       "FDT on the map.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.daftar = QtWidgets.QListWidget()
        self.daftar.currentRowChanged.connect(self._pilih)
        lay.addWidget(self.daftar, 2)
        self.info = QtWidgets.QTextBrowser()
        self.info.setOpenExternalLinks(False)
        lay.addWidget(self.info, 3)
        self.tabel = QtWidgets.QTableWidget(0, 6)
        self.tabel.setHorizontalHeaderLabels(["#", "Existing cable", "Free tubes", "New cable", "Route ratio",
                                              "Result"])
        self.tabel.setEditTriggers(qtc.NO_EDIT)
        self.tabel.setSelectionBehavior(qtc.SELECT_ROWS)
        self.tabel.horizontalHeader().setSectionResizeMode(qtc.TO_CONTENTS)
        self.tabel.cellDoubleClicked.connect(self._pakai_kandidat)
        self.tabel.setToolTip("Double-click a candidate to use it as the feeder (your decision as the designer)")
        lay.addWidget(self.tabel, 2)
        bawah = QtWidgets.QHBoxLayout()
        self.b_kmz = QtWidgets.QPushButton("Save this FDT as KMZ")
        self.b_html = QtWidgets.QPushButton("Open report")
        self.b_folder = QtWidgets.QPushButton("Open results folder")
        self.b_kmz.clicked.connect(self._simpan_kmz)
        self.b_html.clicked.connect(self._buka_html)
        self.b_folder.clicked.connect(self._buka_folder)
        for b in (self.b_kmz, self.b_html, self.b_folder):
            bawah.addWidget(b)
        lay.addLayout(bawah)
        self.setWidget(w)
        self._aktif()

    def _aktif(self):
        ada = bool(self.hasil)
        self.b_kmz.setEnabled(ada)
        self.b_html.setEnabled(bool(self.keluaran and self.keluaran.get("html")))
        self.b_folder.setEnabled(bool(self.keluaran))

    def set_status(self, teks):
        self.status.setText(teks)

    def tampil(self, hasil, keluaran=None, tambah=False):
        self.hasil = (self.hasil + hasil) if tambah else list(hasil)
        if keluaran is not None:
            self.keluaran = keluaran
        self.daftar.clear()
        for h in self.hasil:
            it = QtWidgets.QListWidgetItem("%s  -  %s%s" % (h["fdt"]["kode"], NAMA.get(h["keputusan"], h["keputusan"]),
                                                             "  (borderline)" if h.get("batas") else ""))
            it.setForeground(QtGui.QBrush(QtGui.QColor(WARNA.get(h["keputusan"], "#333"))))
            self.daftar.addItem(it)
        if self.hasil:
            self.daftar.setCurrentRow(len(self.hasil) - 1 if tambah else 0)
        self._aktif()

    def _pilih(self, i):
        if i < 0 or i >= len(self.hasil):
            return
        h = self.hasil[i]
        sel = h.get("terpilih")
        n = h["penomoran"]
        teks = ["<h3 style='margin:2px 0'>%s <span style='color:%s'>%s</span></h3>" % (
            _esc(h["fdt"]["kode"]), WARNA.get(h["keputusan"]), NAMA.get(h["keputusan"]))]
        teks.append("<p>Compilation folder: <b>F%d_T%d</b> &middot; POP %s (%s m away)%s</p>" % (
            n["feeder"], n["t"], _esc(h["pop"]["nama"] if h["pop"] else "-"), h["jarak_pop_m"],
            " &middot; new cable <b>%d m</b>" % sel["kabel_baru_m"] if sel else ""))
        if h.get("batas"):
            teks.append("<p style='color:#7c3aed'><b>Borderline:</b> reusing the feeder and building a new one are "
                        "almost equally good here. Please review both before deciding.</p>")
        teks.append("<p style='color:#5b6b78;margin:4px 0'>Why (from the report, in Indonesian):</p>")
        teks += ["<p style='background:#eef6f6;padding:4px'>%s</p>" % _esc(a) for a in h["alasan"]]
        teks += ["<p style='background:#fff4e0;padding:4px'>&#9888; %s</p>" % _esc(a) for a in h["peringatan"]]
        rute = sel["rute"] if sel else h.get("feeder_baru")
        if rute and rute.get("bantu_m", 0) > 1:
            teks.append("<p style='background:#fde8e8;padding:4px'><b>%d m is a straight helper line</b> (no road or "
                        "cable data there). Redraw it along the poles or road.</p>" % rute["bantu_m"])
        self.info.setHtml("".join(teks))
        self.tabel.setRowCount(0)
        for k in h["kandidat"]:
            r = self.tabel.rowCount()
            self.tabel.insertRow(r)
            vals = [str(r + 1), "%s %s" % (k["label_colo"], k["nama"] or k["id"]),
                    KAPASITAS.get(k["kapasitas"], k["kapasitas"]), "%d m" % k["kabel_baru_m"],
                    "-" if k.get("rasio_jalur") is None else str(k["rasio_jalur"]),
                    "Passes all checks" if k["lolos"] else "; ".join(k["gagal"] + k["catatan"])[:120]]
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(v)
                it.setToolTip("%s\n%s" % (k["ket_kapasitas"], "; ".join(k["gagal"] + k["catatan"])))
                if sel is k:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.tabel.setItem(r, c, it)
        self._zoom(h)

    def _zoom(self, h):
        pts = [h["fdt"]["ll"]] + ([h["pop"]["ll"]] if h["pop"] and h["jarak_pop_m"] < 8000 else [])
        sel = h.get("terpilih")
        if sel:
            L = geo.Lokal(*h["lokal"])
            pts.append(L.balik(sel["rute"]["titik"][0]))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = QgsRectangle(min(xs) - 0.003, min(ys) - 0.003, max(xs) + 0.003, max(ys) + 0.003)
        canvas = self.iface.mapCanvas()
        tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                    canvas.mapSettings().destinationCrs(), QgsProject.instance())
        try:
            canvas.setExtent(tr.transformBoundingBox(r))
            canvas.refresh()
        except Exception:   # CRS kanvas tidak dapat ditransformasi: biarkan tampilan
            return

    def _pakai_kandidat(self, row, _col):
        i = self.daftar.currentRow()
        if i < 0:
            return
        h = self.hasil[i]
        k = h["kandidat"][row]
        jawab = QtWidgets.QMessageBox.question(
            self, "Tembuku", "Use candidate #%d (%s) as the feeder for %s?\n\nThe KMZ and the report will show it as "
            "the designer's choice." % (row + 1, k["nama"] or k["id"], h["fdt"]["kode"]))
        if jawab != qtc.e(QtWidgets.QMessageBox, "StandardButton", "Yes"):
            return
        from .inti import mesin
        if self.plugin.sesi and self.plugin.sesi.data is not None:
            mesin.pilih_manual(h, row, self.plugin.sesi.data)
        else:
            QtWidgets.QMessageBox.warning(self, "Tembuku", "The data of this session is no longer loaded. Run the "
                                          "design again, then choose the candidate.")
            return
        self.plugin.gambar(self.hasil)
        self.tampil(self.hasil)
        self.daftar.setCurrentRow(i)

    def _simpan_kmz(self):
        i = self.daftar.currentRow()
        if i < 0:
            return
        h = self.hasil[i]
        awal = os.path.join(self.plugin.folder_keluar(), "TEMBUKU_%s.kmz" % h["fdt"]["kode"])
        path, _f = QtWidgets.QFileDialog.getSaveFileName(self, "Save KMZ", awal, "KMZ (*.kmz)")
        if not path:
            return
        from .inti import tulis_kmz
        tulis_kmz.tulis([h], path, self.plugin.prm(), os.path.basename(path)[:-4])
        self.iface.messageBar().pushSuccess("Tembuku", "KMZ saved: %s" % path)

    def _buka_html(self):
        if self.keluaran and self.keluaran.get("html"):
            QtGui.QDesktopServices.openUrl(QUrl.fromLocalFile(self.keluaran["html"]))

    def _buka_folder(self):
        if self.keluaran and self.keluaran.get("html"):
            QtGui.QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.keluaran["html"])))
