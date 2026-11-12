# -*- coding: utf-8 -*-
# Tembuku - dialog utama. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""One window, three steps: (1) choose the data folder (or add files), (2) read the input check, (3) Run.
File roles are recognised automatically and can be corrected by the user. The Run buttons stay locked while there is a
FATAL finding (missing, damaged or rejected file, or a required source is absent)."""
import datetime
import json
import os

from qgis.core import QgsMapLayerProxyModel, QgsSettings
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt import QtGui, QtWidgets

from . import layanan, qtc
from .inti import profil, sumber
from .inti import validasi as V
from .inti.teks import T, en

PERAN = ["NASIONAL", "COMPILE", "TARGET", "POP", "AUDIT", "LAIN"]
LABEL = {"NASIONAL": "Cable inventory (existing network)", "COMPILE": "Feeder design compilation (on-going)",
         "TARGET": "Target FDTs", "POP": "POP / OLT locations", "AUDIT": "Feeder tube record",
         "LAIN": "(ignore this file)"}
TINGKAT_EN = {V.FATAL: "CANNOT RUN", V.PERBAIKI: "AUTO-CORRECTED", V.PERINGATAN: "CHECK", V.INFO: "NOTE"}
WARNA = {V.FATAL: "#b91c1c", V.PERBAIKI: "#0e7c7b", V.PERINGATAN: "#b45309", V.INFO: "#5b6b78"}


class DialogTembuku(QtWidgets.QDialog):
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.st = QgsSettings()
        self.setWindowTitle("Tembuku - Design Feeders")
        self.setMinimumSize(760, 640)
        self.sesi = None
        lay = QtWidgets.QVBoxLayout(self)
        judul = QtWidgets.QLabel("<b style='font-size:14px'>1. Your data</b> &nbsp; Choose the folder that holds your KMZ "
                                 "files: the cable inventory and/or the feeder design compilation, a KMZ with the FDT "
                                 "points to design, and the POP list. Tembuku works out what each file is; you can "
                                 "change it in the list below.")
        judul.setWordWrap(True)
        lay.addWidget(judul)
        baris = QtWidgets.QHBoxLayout()
        self.w_folder = QgsFileWidget()
        self.w_folder.setStorageMode(qtc.e(QgsFileWidget, "StorageMode", "GetDirectory"))
        self.w_folder.setFilePath(self.st.value("tembuku/folder", ""))
        self.w_folder.fileChanged.connect(lambda _p: self.periksa())
        b_tambah = QtWidgets.QPushButton("Add files...")
        b_tambah.setToolTip("Add map data files that are in other folders (KMZ, KML, ZIP, GeoJSON, CSV, Excel, Shapefile, "
                            "GeoPackage)")
        b_tambah.clicked.connect(self._tambah)
        baris.addWidget(self.w_folder, 1)
        baris.addWidget(b_tambah)
        lay.addLayout(baris)
        self.tambahan = [p for p in json.loads(self.st.value("tembuku/tambahan", "[]") or "[]") if os.path.exists(p)]
        self.tabel = QtWidgets.QTableWidget(0, 4)
        self.tabel.setHorizontalHeaderLabels(["File", "Read as", "Why", "Size"])
        self.tabel.setToolTip("Each file's type is recognised from what is inside it (object shapes, data columns, "
                              "folder layout), not from its name. If one was recognised wrongly, choose the right "
                              "role in the 'Read as' column")
        self.tabel.horizontalHeader().setSectionResizeMode(0, qtc.STRETCH)
        self.tabel.setEditTriggers(qtc.NO_EDIT)
        self.tabel.horizontalHeader().setSectionResizeMode(1, qtc.TO_CONTENTS)
        self.tabel.horizontalHeader().setSectionResizeMode(2, qtc.STRETCH)
        self.tabel.horizontalHeader().setSectionResizeMode(3, qtc.TO_CONTENTS)
        lay.addWidget(self.tabel, 2)
        lay.addWidget(QtWidgets.QLabel("<b style='font-size:14px'>2. Input check</b> &nbsp; "
                                       "<span style='color:#0e7c7b'>auto-corrected</span> &middot; "
                                       "<span style='color:#b45309'>please check</span> &middot; "
                                       "<span style='color:#b91c1c'>cannot run until fixed</span> &nbsp; "
                                       ""))
        self.temuan = QtWidgets.QTextBrowser()
        lay.addWidget(self.temuan, 2)

        lay.addWidget(QtWidgets.QLabel("<b style='font-size:14px'>3. Results</b>"))
        f2 = QtWidgets.QFormLayout()
        self.w_keluar = QgsFileWidget()
        self.w_keluar.setStorageMode(qtc.e(QgsFileWidget, "StorageMode", "GetDirectory"))
        self.w_keluar.setFilePath(self.st.value("tembuku/keluar", ""))
        self.w_keluar.lineEdit().setPlaceholderText("empty = a new TEMBUKU_HASIL_<date> folder inside the data folder")
        f2.addRow("Results folder", self.w_keluar)
        self.c_osm = QtWidgets.QCheckBox("Follow OpenStreetMap roads where new poles are needed (uses the internet once "
                                         "per area; kept for 90 days)")
        self.c_osm.setToolTip("Without road data, new sections are drawn as straight helper lines that you must redraw "
                              "by hand. Only the map area around your FDTs is downloaded; nothing is uploaded.")
        self.c_osm.setChecked(self.st.value("tembuku/osm", "1") == "1")
        f2.addRow("", self.c_osm)
        lay.addLayout(f2)

        self.lanjut = QtWidgets.QGroupBox("Advanced (decision settings and your own road layer)")
        self.lanjut.setToolTip("Most users never need this. The default values were calibrated on real approved designs.")
        self.lanjut.setCheckable(True)
        self.lanjut.setChecked(False)
        gl0 = QtWidgets.QVBoxLayout(self.lanjut)
        self.isi_lanjut = QtWidgets.QWidget()          # one container, so labels hide together with their fields
        gl0.addWidget(self.isi_lanjut)
        gl = QtWidgets.QVBoxLayout(self.isi_lanjut)
        gl.setContentsMargins(0, 0, 0, 0)
        fr = QtWidgets.QFormLayout()
        self.cb_jalan = QgsMapLayerComboBox()
        try:                                    # QGIS >= 3.34 / 4.x
            from qgis.core import Qgis
            self.cb_jalan.setFilters(Qgis.LayerFilter.LineLayer)
        except (ImportError, AttributeError, TypeError):
            self.cb_jalan.setFilters(qtc.e(QgsMapLayerProxyModel, "Filter", "LineLayer"))
        self.cb_jalan.setAllowEmptyLayer(True)
        self.cb_jalan.setLayer(None)
        fr.addRow("Your own road layer (optional)", self.cb_jalan)
        self.e_overpass = QtWidgets.QLineEdit(self.st.value("tembuku/overpass", layanan.OVERPASS))
        self.e_overpass.setToolTip("Address of the OpenStreetMap road data server (Overpass API). The free public server "
                                   "asks companies with regular, heavy use to run their own or a paid server; enter its "
                                   "address here. Must start with https://")
        fr.addRow("Road data server", self.e_overpass)
        self.c_peta_lap = QtWidgets.QCheckBox("Also put my satellite basemaps (Copernicus account, Esri key) "
                                              "in the HTML report")
        self.c_peta_lap.setToolTip("Off by default. The key or address is written into the report, so anyone who "
                                   "receives the report could use it. Without this, the report shows OpenStreetMap only.")
        self.c_peta_lap.setChecked(self.st.value("tembuku/peta_di_laporan", "0") == "1")
        fr.addRow("", self.c_peta_lap)
        gl.addLayout(fr)
        self.t_prm = QtWidgets.QTableWidget(0, 3)
        self.t_prm.setHorizontalHeaderLabels(["Setting", "Value", "What it means"])
        self.t_prm.horizontalHeader().setSectionResizeMode(2, qtc.STRETCH)
        gl.addWidget(self.t_prm)
        b_reset = QtWidgets.QPushButton("Restore default values")
        b_reset.clicked.connect(lambda: self._isi_prm({}))
        gl.addWidget(b_reset)
        self.lanjut.toggled.connect(self.isi_lanjut.setVisible)
        self.isi_lanjut.setVisible(False)
        lay.addWidget(self.lanjut)
        self._isi_prm(json.loads(self.st.value("tembuku/prm", "{}") or "{}"))

        tombol = QtWidgets.QHBoxLayout()
        self.b_periksa = QtWidgets.QPushButton("Check again")
        self.b_periksa.setToolTip("Read the files again after you fix or add something")
        self.b_klik = QtWidgets.QPushButton("Prepare for map clicks")
        self.b_klik.setToolTip("Load the data once, then click anywhere on the map to get an instant recommendation "
                               "for an FDT at that spot")
        self.b_uji = QtWidgets.QPushButton("Accuracy test")
        self.b_uji.setToolTip("Each FDT already designed in the compilation is hidden in turn and designed again by "
                              "Tembuku; the report compares Tembuku with the designer's own design")
        b_bantu = QtWidgets.QPushButton("Help")
        b_bantu.setToolTip("Open the quick guide and glossary (works offline)")
        b_bantu.clicked.connect(lambda: self.plugin.bantuan("start"))
        self.b_uji.clicked.connect(lambda: self._mulai("uji"))
        self.b_jalan = QtWidgets.QPushButton("Run all FDTs")
        self.b_jalan.setToolTip("Design every target FDT and write the report, the KMZ files and the CSV summary")
        self.b_jalan.setDefault(True)
        self.b_jalan.setStyleSheet("QPushButton{font-weight:bold;padding:6px 16px}")
        b_tutup = QtWidgets.QPushButton("Close")
        self.b_periksa.clicked.connect(self.periksa)
        self.b_klik.clicked.connect(lambda: self._mulai("muat"))
        self.b_jalan.clicked.connect(lambda: self._mulai("batch"))
        b_tutup.clicked.connect(self.reject)
        tombol.addWidget(b_bantu)
        tombol.addWidget(self.b_periksa)
        tombol.addStretch(1)
        tombol.addWidget(self.b_uji)
        tombol.addWidget(self.b_klik)
        tombol.addWidget(self.b_jalan)
        tombol.addWidget(b_tutup)
        lay.addLayout(tombol)
        self.petunjuk = QtWidgets.QLabel("")            # tells the user what to do next, in one line
        self.petunjuk.setWordWrap(True)
        self.petunjuk.setStyleSheet("color:#2b3a8f")
        lay.addWidget(self.petunjuk)
        if self.w_folder.filePath() or self.tambahan:
            self.periksa()
        else:
            self._kunci(True, True)

    # ------------------------------------------------------------------ parameter
    def _isi_prm(self, ubah):
        p = profil.baru(ubah)
        self.t_prm.setRowCount(0)
        dasar = {"KEBIJAKAN": "policy", "DATA": "calibrated on real designs", "STANDAR": "standard",
                 "KEBIJAKAN+DATA": "policy, checked against real designs", "PDF": "engineering rules of 11 Nov 2026"}
        for k, (v0, kel, _ket) in profil.BAWAAN.items():
            nama, arti = profil.PENJELASAN_EN[k]
            r = self.t_prm.rowCount()
            self.t_prm.insertRow(r)
            a = QtWidgets.QTableWidgetItem(nama)
            a.setData(qtc.USER_ROLE, k)
            a.setToolTip("Internal name: %s. Default: %s" % (k, v0))
            a.setFlags(a.flags() & ~qtc.ITEM_EDITABLE)
            b = QtWidgets.QTableWidgetItem(str(p[k]))
            c = QtWidgets.QTableWidgetItem("%s (%s)" % (arti, dasar.get(kel, kel)))
            c.setFlags(c.flags() & ~qtc.ITEM_EDITABLE)
            c.setToolTip(arti)
            if str(p[k]) != str(v0):
                b.setBackground(QtGui.QBrush(QtGui.QColor("#fff4cc")))
            self.t_prm.setItem(r, 0, a)
            self.t_prm.setItem(r, 1, b)
            self.t_prm.setItem(r, 2, c)

    def prm(self):
        out, salah = {}, []
        for r in range(self.t_prm.rowCount()):
            k = self.t_prm.item(r, 0).data(qtc.USER_ROLE)
            v = self.t_prm.item(r, 1).text().strip()
            v0 = profil.BAWAAN[k][0]
            try:
                if isinstance(v0, bool):
                    nv = v.lower() in ("1", "true", "ya", "y", "yes", "on")
                elif isinstance(v0, (int, float)):
                    nv = type(v0)(float(v.replace(",", ".")))
                    if nv < 0:
                        raise ValueError
                else:
                    nv = v
            except ValueError:
                salah.append(profil.PENJELASAN_EN[k][0])
                continue
            if nv != v0:
                out[k] = nv
        return out, salah

    # ------------------------------------------------------------------ berkas
    def _tambah(self):
        fs, _f = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add map data files", self.w_folder.filePath(),
            "Map data (*.kmz *.kml *.zip *.geojson *.json *.csv *.txt *.xlsx *.shp *.gpkg *.gml *.tab *.fgb *.gpx);;"
            "All files (*)")
        if fs:
            self.tambahan = sorted(set(self.tambahan + fs))
            self.periksa()

    def berkas(self):
        out = []
        d = self.w_folder.filePath().strip()
        if d:
            if os.path.isdir(d):
                out += sumber.cari_berkas(d)
            else:
                out.append(d)           # jalur salah ketik -> dilaporkan FATAL oleh pra-cek
        return sorted(set(out + self.tambahan))

    def periksa(self):
        paths = self.berkas()
        QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(qtc.TUNGGU))
        try:
            self.sesi = layanan.Sesi(paths, self.plugin.cache(), pakai_osm=False)
            t = self.sesi.pra_cek(target_manual=True)
            if not self.sesi.peran.get("TARGET"):
                t.tambah(V.INFO, "Kelengkapan", T("tidak ada titik FDT yang akan dirancang di berkas ini: tekan "
                                                  "'Prepare for map clicks' lalu klik lokasi FDT di peta",
                                                  "these files have no FDT points to design: press 'Prepare for map "
                                                  "clicks', then click where the FDT is on the map"), "",
                         T("atau tambahkan KMZ berisi titik FDT (distribusi atau desain)",
                           "or add a KMZ with the FDT points (distribution or design KMZ)"))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.tabel.setRowCount(0)
        for r_, p in [(r, p) for r in PERAN for p in self.sesi.peran.get(r, [])]:
            r = self.tabel.rowCount()
            self.tabel.insertRow(r)
            alasan = (getattr(self.sesi, "bukti", None) or {}).get(p) or ""
            it = QtWidgets.QTableWidgetItem(os.path.basename(p))
            it.setToolTip(p)
            self.tabel.setItem(r, 0, it)
            it = QtWidgets.QTableWidgetItem(en(alasan) if alasan else "")
            it.setToolTip(en(alasan) if alasan else "")
            self.tabel.setItem(r, 2, it)
            cb = QtWidgets.QComboBox()
            for x in PERAN:
                cb.addItem(LABEL[x], x)
            cb.setCurrentIndex(PERAN.index(r_))
            cb.currentIndexChanged.connect(lambda _i, p=p, cb=cb: self._ganti_peran(p, cb.currentData()))
            self.tabel.setCellWidget(r, 1, cb)
            self.tabel.setItem(r, 3, QtWidgets.QTableWidgetItem("%.1f MB" % (os.path.getsize(p) / 1048576.0)))
        self._tulis_temuan()

    def _ganti_peran(self, path, baru):
        for r in PERAN:
            if path in self.sesi.peran.get(r, []):
                self.sesi.peran[r].remove(path)
        self.sesi.peran.setdefault(baru, []).append(path)
        t = V.Temuan()
        for x in self.sesi.temuan.daftar:
            if x["kategori"] != "Kelengkapan" or x["berkas"]:
                t.daftar.append(x)
        t.tambah(V.INFO, "Kelengkapan", T("jenis berkas diubah pengguna menjadi %s", "file type changed by you to %s")
                 % LABEL[baru], os.path.basename(path))
        V.cek_peran(self.sesi.peran, t, True)
        self.sesi.temuan = t
        self._tulis_temuan()

    def _tulis_temuan(self):
        t = self.sesi.temuan
        hit = t.hitung()
        baris = ["<p><b>%d cannot run &middot; %d auto-corrected &middot; %d to check &middot; %d notes</b></p>" % (
            hit[V.FATAL], hit[V.PERBAIKI], hit[V.PERINGATAN], hit[V.INFO])]
        for x in sorted(t.daftar, key=lambda x: [V.FATAL, V.PERINGATAN, V.PERBAIKI, V.INFO].index(x["tingkat"])):
            baris.append("<div style='color:%s'>&#9679; <b>%s</b> %s%s%s</div>" % (
                WARNA[x["tingkat"]], TINGKAT_EN[x["tingkat"]], _e(x["berkas"] + ": ") if x["berkas"] else "",
                _e(en(x["pesan"])), (" <i>&rarr; %s</i>" % _e(en(x["saran"]))) if x["saran"] else ""))
        if len(baris) == 1:
            baris.append("<div style='color:#0e7c7b'>All files were read correctly.</div>")
        if t.fatal():
            baris.insert(1, "<p style='color:#b91c1c'><b>Tembuku cannot run yet.</b> Fix the red items (each one says "
                         "what to do after the arrow), then press 'Check again'.</p>")
        self.temuan.setHtml("".join(baris))
        fatal = bool(t.fatal())
        ada_target = bool(self.sesi.peran.get("TARGET"))
        self._kunci(fatal, fatal or not ada_target)

    def _kunci(self, kunci_klik, kunci_batch):
        ada_compile = bool(self.sesi and self.sesi.peran.get("COMPILE"))
        self.b_uji.setEnabled(not kunci_klik and ada_compile)
        self.b_klik.setEnabled(not kunci_klik)
        self.b_jalan.setEnabled(not kunci_batch)
        # highlight the one button that makes sense now, and say why in plain words
        utama = self.b_jalan if not kunci_batch else (self.b_uji if self.b_uji.isEnabled() else None)
        for b in (self.b_jalan, self.b_uji):
            b.setDefault(b is utama)
            b.setStyleSheet("QPushButton{font-weight:bold;padding:6px 16px}" if b is utama else "")
        if kunci_klik and self.sesi is not None:
            teks = "Fix the red items in the input check first, then press Check again."
        elif self.sesi is None:
            teks = "Choose the folder with your KMZ files to start."
        elif not kunci_batch:
            teks = "Ready: press Run all FDTs."
        elif ada_compile:
            teks = ("No target FDTs in these files. Press Accuracy test to compare Tembuku with the designs already in "
                    "the compilation, or Prepare for map clicks to design an FDT by clicking on the map.")
        else:
            teks = "No target FDTs in these files. Press Prepare for map clicks, then click where the FDT is."
        if hasattr(self, "petunjuk"):
            self.petunjuk.setText(teks)
        self.b_jalan.setToolTip("Design every target FDT and write the report, the KMZ files and the CSV summary" +
                                ("" if not kunci_batch else "\n(Not available: " + teks + ")"))

    # ------------------------------------------------------------------ jalankan
    def _mulai(self, mode):
        ubah, salah = self.prm()
        if salah:
            QtWidgets.QMessageBox.warning(self, "Tembuku", "These advanced settings need a valid number (zero or more): "
                                          "%s" % ", ".join(salah))
            return
        server = self.e_overpass.text().strip() or layanan.OVERPASS
        if not server.lower().startswith("https://"):
            QtWidgets.QMessageBox.warning(self, "Tembuku", "The road data server address must start with https:// "
                                          "(Advanced section).")
            return
        if self.sesi is None or self.sesi.temuan.fatal():
            self.periksa()
            if self.sesi.temuan.fatal():
                return
        self.st.setValue("tembuku/folder", self.w_folder.filePath())
        self.st.setValue("tembuku/tambahan", json.dumps(self.tambahan))
        self.st.setValue("tembuku/keluar", self.w_keluar.filePath())
        self.st.setValue("tembuku/osm", "1" if self.c_osm.isChecked() else "0")
        self.st.setValue("tembuku/prm", json.dumps(ubah))
        self.st.setValue("tembuku/overpass", server)
        keluar = self.w_keluar.filePath().strip()
        if not keluar:
            dasar = self.w_folder.filePath() if os.path.isdir(self.w_folder.filePath()) else os.path.dirname(
                (self.tambahan or [os.path.expanduser("~/x")])[0])
            keluar = os.path.join(dasar, "TEMBUKU_HASIL_%s" % datetime.datetime.now().strftime("%Y%m%d_%H%M"))
        jalan_lokal = self.plugin.jalan_dari_layer(self.cb_jalan.currentLayer()) if self.lanjut.isChecked() else None
        s = self.sesi
        s.prm = profil.baru(ubah)
        s.pakai_osm = self.c_osm.isChecked()
        s.ambil = self.plugin.ambil
        s.overpass = server
        s.peta_laporan = None
        self.st.setValue("tembuku/peta_di_laporan", "1" if self.c_peta_lap.isChecked() else "0")
        if self.lanjut.isChecked() and self.c_peta_lap.isChecked():
            from .inti import peta_dasar as P
            kunci = self.st.value("tembuku/esri_key", "") or ""
            inst = self.st.value("tembuku/cdse_instance", "") or ""
            lay = self.st.value("tembuku/cdse_layer", "") or ""
            ekstra = []
            if kunci and P.kunci_esri_sah(kunci):
                ekstra.append({"jenis": "esri", "nama": "Satelit detail 0,3-0,5 m, rumah terlihat (Esri) + tanggal pemotretan",
                               "url": P.url_lapis("esri", kunci_api=kunci), "zmax": 19, "atrib": P.ATRIB_ESRI})
            if inst and lay and P.id_sah(inst) and P.id_sah(lay):
                ekstra.append({"jenis": "cdse", "nama": "Satelit bebas awan terbaru 10 m, cek perubahan (Copernicus per kuartal)",
                               "url": P.url_cdse(inst, lay), "zmax": 14,
                               "atrib": P.ATRIB_CDSE % P.jendela_cdse()[1][:4]})
            s.peta_laporan = ekstra or None
        s.jalan_lokal = jalan_lokal
        self.plugin.mulai(s, mode, keluar)
        self.accept()


def _e(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
