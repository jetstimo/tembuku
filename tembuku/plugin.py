# -*- coding: utf-8 -*-
# Tembuku - Feeder Tap Designer - menu, toolbar, panel, alat klik-peta, Processing.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
import os

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
                       QgsSettings)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt import QtGui, QtWidgets

from . import __version__, _log, qtc, tugas
from .inti import mesin, profil
from .inti.teks import en

MENU = "&Tembuku"
# plain-English decision names for the user interface (reports keep their Indonesian wording)
KEPUTUSAN_EN = {k: en(v) for k, v in mesin.NAMA_KEPUTUSAN.items()}
HERE = os.path.dirname(__file__)


class AlatKlik(QgsMapToolEmitPoint):
    """Klik di peta = FDT baru: analisis feeder dalam ~1 detik (data sudah disiapkan)."""

    def __init__(self, plugin):
        super().__init__(plugin.iface.mapCanvas())
        self.plugin = plugin
        self.setCursor(QtGui.QCursor(qtc.SILANG))
        self.canvasClicked.connect(self._klik)

    def _klik(self, titik, _tombol):
        crs = self.canvas().mapSettings().destinationCrs()
        tr = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        p = tr.transform(titik)
        self.plugin.analisis_klik(p.x(), p.y())


class TembukuPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.panel = None
        self.alat = None
        self.sesi = None
        self.provider = None
        self._tugas = None
        self._n_klik = 0
        self._keluar = None

    # ------------------------------------------------------------------ QGIS
    def initProcessing(self):  # noqa: N802 - QGIS API name
        from .provider import TembukuProvider
        self.provider = TembukuProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def _aksi(self, label, tip, slot, toolbar=False, ikon="icon.png", cek=False):
        act = qtc.QAction(QtGui.QIcon(os.path.join(HERE, ikon)), label, self.iface.mainWindow())
        act.setToolTip(tip)
        act.setStatusTip(tip)
        act.setCheckable(cek)
        (act.toggled if cek else act.triggered).connect(slot)
        if toolbar:
            self.iface.addToolBarIcon(act)
        self.iface.addPluginToVectorMenu(MENU, act)
        self.actions.append(act)
        return act

    def initGui(self):  # noqa: N802 - QGIS API name
        self.initProcessing()
        self._aksi("Design Feeders...", "Choose a data folder: Tembuku checks the input files, finds an existing "
                   "feeder with free tubes heading toward each FDT and draws the cable route to it", self.buka_dialog,
                   toolbar=True)
        self.a_klik = self._aksi("Click an FDT on the Map", "Click where an FDT is: get an instant recommendation "
                                 "(reuse a feeder or build a new one)", self.mode_klik, toolbar=True,
                                 ikon="icon_klik.png", cek=True)
        self._aksi("Results Panel", "Show the Tembuku results panel", self.tampil_panel)
        self.menu_peta = self.buat_menu_peta(self.iface.mainWindow())
        act_peta = self.menu_peta.menuAction()
        act_peta.setIcon(QtGui.QIcon(os.path.join(HERE, "icon.png")))
        act_peta.setToolTip("Add a background map: OpenStreetMap or satellite imagery that updates itself")
        self.iface.addPluginToVectorMenu(MENU, act_peta)
        self.actions.append(act_peta)
        self._aksi("Help and Quick Guide", "How to use Tembuku, what each result means, and a glossary of terms",
                   self.bantuan)
        self._aksi("About Tembuku", "Version, author, licence and release authenticity", self.tentang)
        self.alat = AlatKlik(self)
        self.alat.setAction(self.a_klik)
        # satellite basemaps added by Tembuku move to the newest imagery date when QGIS starts or a project opens
        QgsProject.instance().readProject.connect(self._segarkan_peta)
        qtc.QtCore.QTimer.singleShot(4000, self._segarkan_peta)
        st = QgsSettings()
        if st.value("tembuku/sambut", "") != "1":
            st.setValue("tembuku/sambut", "1")
            self.iface.messageBar().pushInfo("Tembuku", "Installed. Click the Tembuku toolbar icon, choose your data "
                                             "folder and press Run. Help is in Vector > Tembuku > Help and Quick Guide.")

    def buat_menu_peta(self, induk):
        """Basemap menu, shared by the Vector menu and the results panel."""
        from .inti import peta_dasar as P
        m = QtWidgets.QMenu("Basemaps (OpenStreetMap / satellite)", induk)
        for kunci in P.URUTAN:
            a = m.addAction(P.KATALOG[kunci]["nama"])
            a.setToolTip(P.KATALOG[kunci]["ket"])
            a.setStatusTip(P.KATALOG[kunci]["ket"])
            a.triggered.connect(lambda _c=False, k=kunci: self.tambah_peta(k))
        m.addSeparator()
        a = m.addAction("When was the detailed satellite image here taken?")
        a.setToolTip("Reads the capture date of the Esri image at the map centre and warns if it is older than 12 months.")
        a.triggered.connect(self._cek_tanggal)
        a = m.addAction("Forget my saved keys (Esri, Copernicus)")
        a.triggered.connect(self._lupa_kunci)
        a = m.addAction("Which basemap should I use?")
        a.triggered.connect(lambda _c=False: self.bantuan("basemap"))
        try:
            m.setToolTipsVisible(True)
        except AttributeError as e:
            _log.note(e)
        return m

    def tambah_peta(self, kunci):
        from . import peta
        try:
            peta.tambah(self, kunci)
        except Exception as e:      # a basemap must never break the plugin; tell the user plainly
            _log.note(e)
            self.iface.messageBar().pushWarning("Tembuku", "The basemap could not be added: %s" % e)

    def _cek_tanggal(self, *_a):
        from . import peta
        try:
            peta.cek_tanggal(self)
        except Exception as e:
            _log.note(e)
            self.iface.messageBar().pushWarning("Tembuku", "The capture date could not be read: %s" % e)

    def _segarkan_peta(self, *_a):
        from . import peta
        try:
            peta.segarkan(self)
        except Exception as e:
            _log.note(e)

    def _lupa_kunci(self):
        st = QgsSettings()
        for k in ("tembuku/esri_key", "tembuku/cdse_instance", "tembuku/cdse_layer"):
            st.remove(k)
        self.iface.messageBar().pushInfo("Tembuku", "Your saved Esri key and Copernicus account details were removed "
                                         "from your QGIS profile.")

    def unload(self):
        try:
            QgsProject.instance().readProject.disconnect(self._segarkan_peta)
        except (TypeError, RuntimeError) as e:
            _log.note(e)
        if self.panel is not None:
            self.iface.removeDockWidget(self.panel)
            self.panel.deleteLater()
            self.panel = None
        if self.alat is not None and self.iface.mapCanvas().mapTool() is self.alat:
            self.iface.mapCanvas().unsetMapTool(self.alat)
        for act in self.actions:
            self.iface.removePluginVectorMenu(MENU, act)
            try:
                self.iface.removeToolBarIcon(act)
            except Exception as e:
                _log.note(e)
        self.actions = []
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    # ------------------------------------------------------------------ util
    def cache(self):
        return tugas.folder_cache()

    def ambil(self, url, data=None):
        return tugas.ambil(url, data)

    def prm(self):
        return self.sesi.prm if self.sesi else profil.baru()

    def folder_keluar(self):
        return self._keluar or os.path.expanduser("~")

    def jalan_dari_layer(self, lyr):
        """Layer garis pengguna -> [{kelas, ll}] dalam WGS 84 (kolom 'highway'/'fclass'/'kelas' bila ada)."""
        if lyr is None:
            return None
        tr = QgsCoordinateTransform(lyr.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        nama = [f.name() for f in lyr.fields()]
        kol = next((c for c in ("highway", "fclass", "kelas", "type") if c in nama), None)
        out = []
        for f in lyr.getFeatures():
            g = f.geometry()
            if g is None or g.isEmpty():
                continue
            tipe = g.type()
            if int(getattr(tipe, "value", tipe)) != 1:      # 1 = garis (QgsWkbTypes.LineGeometry / Qgis.GeometryType.Line)
                continue
            g.transform(tr)
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for part in parts:
                if len(part) >= 2:
                    out.append({"kelas": str(f[kol]) if kol else "road", "ll": [(p.x(), p.y()) for p in part]})
        return out

    # ------------------------------------------------------------------ panel & dialog
    def tampil_panel(self):
        if self.panel is None:
            from .panel import PanelTembuku
            self.panel = PanelTembuku(self)
            self.iface.addDockWidget(qtc.KANAN, self.panel)
            # share the right-hand area as a tab instead of squeezing under other panels (e.g. Processing Toolbox)
            mw = self.iface.mainWindow()
            try:
                lain = [d for d in mw.findChildren(QtWidgets.QDockWidget) if d is not self.panel and d.isVisible()
                        and not d.isFloating() and mw.dockWidgetArea(d) == qtc.KANAN]
                if lain:
                    mw.tabifyDockWidget(lain[0], self.panel)
            except (AttributeError, TypeError, RuntimeError) as e:
                _log.note(e)
        self.panel.show()
        self.panel.raise_()
        return self.panel

    def buka_dialog(self):
        from .dialog import DialogTembuku
        dlg = DialogTembuku(self, self.iface.mainWindow())
        qtc.jalankan(dlg)

    def mode_klik(self, on):
        if on:
            self.tampil_panel()
            if self.sesi is None or self.sesi.data is None:
                self.iface.messageBar().pushWarning("Tembuku", "Prepare the data first: in the Tembuku window choose your "
                                                    "folder, then press 'Prepare for map clicks'.")
                self.mode_klik(False)
                self.buka_dialog()
                return
            self.iface.mapCanvas().setMapTool(self.alat)
            for w in (self.a_klik, self.panel.b_klik):
                w.blockSignals(True)
                w.setChecked(True)
                w.blockSignals(False)
            self.panel.set_status("Click mode is on: click where the FDT is on the map.")
        else:
            if self.iface.mapCanvas().mapTool() is self.alat:
                self.iface.mapCanvas().unsetMapTool(self.alat)
            for w in ([self.a_klik] + ([self.panel.b_klik] if self.panel else [])):
                w.blockSignals(True)
                w.setChecked(False)
                w.blockSignals(False)

    # ------------------------------------------------------------------ jalankan
    def mulai(self, sesi, mode, keluar):
        if self._tugas is not None:
            self.iface.messageBar().pushWarning("Tembuku", "Tembuku is still working on the previous job. Please wait.")
            return
        self.sesi = sesi
        self._keluar = keluar
        self.tampil_panel().set_status("Working in the background (see the QGIS progress bar at the bottom)...")
        judul = {"batch": "Tembuku: designing feeders", "uji": "Tembuku: accuracy test"}.get(mode, "Tembuku: preparing data")
        self._tugas = tugas.TugasTembuku(judul, sesi, mode, self._selesai, folder_keluar=keluar)
        QgsApplication.taskManager().addTask(self._tugas)

    def analisis_klik(self, lon, lat):
        if self.sesi is None or self.sesi.data is None:
            self.mode_klik(False)
            return
        if self._tugas is not None:
            return
        self._n_klik += 1
        self.panel.set_status("Analysing the point %.6f, %.6f ..." % (lat, lon))
        self._tugas = tugas.TugasTembuku("Tembuku: clicked FDT", self.sesi, "titik", self._selesai,
                                         titik=(lon, lat, "FDT-KLIK-%d" % self._n_klik))
        QgsApplication.taskManager().addTask(self._tugas)

    def _selesai(self, t, ok):
        self._tugas = None
        panel = self.tampil_panel()
        if not ok:
            panel.set_status("Stopped: %s" % (t.galat or "unknown reason"))
            self.iface.messageBar().pushCritical("Tembuku", t.galat or "The job failed (see View > Panels > Log Messages > Tembuku)")
            return
        s = self.sesi
        if t.mode == "muat":
            n = len(s.target)
            panel.set_status("Data ready (%d on-going feeder cables, %d cable-inventory files). Click where the FDT is on the map." % (
                sum(len(c["kabel"]) for c in s.data.compiles), len(s.data.indeks)))
            self.mode_klik(True)
            if n:
                self.iface.messageBar().pushInfo("Tembuku", "%d target FDTs were also found. Use 'Run all FDTs' to "
                                                 "design them in one go." % n)
            return
        if t.mode == "titik":
            self.gambar(t.hasil, pratinjau=True)
            panel.tampil(t.hasil, tambah=True)
            h = t.hasil[0]
            panel.set_status("%s: %s. Click again for another point." % (h["fdt"]["kode"], KEPUTUSAN_EN.get(
                h["keputusan"], h["keputusan"])))
            return
        self.gambar(t.hasil)
        panel.tampil(t.hasil, t.keluaran)
        hit = {}
        for h in t.hasil:
            k = KEPUTUSAN_EN.get(h["keputusan"], h["keputusan"])
            hit[k] = hit.get(k, 0) + 1
        ring = ", ".join("%d %s" % (v, k.lower()) for k, v in sorted(hit.items()))
        if t.mode == "uji" and s.nilai_uji:
            from . import uji_akurasi
            r = uji_akurasi.ringkasan(s.nilai_uji)
            ring = "ACCURACY TEST: same decision %d/%d, same F/T folder %d/%d, median tap offset %s m, median route match %s%%" % (
                r["keputusan_cocok"], r["n"], r["folder_cocok"], r["n"], r["tap_median_m"], r["jalur_median_pct"])
        panel.set_status("Done: %d FDTs (%s). Results are in %s" % (len(t.hasil), ring, os.path.dirname(t.keluaran["html"])))
        self.iface.messageBar().pushSuccess("Tembuku", "%d FDTs designed (%s). Report and KMZ files: %s" % (
            len(t.hasil), ring, os.path.dirname(t.keluaran["html"])))
        try:
            QtGui.QDesktopServices.openUrl(qtc.QtCore.QUrl.fromLocalFile(t.keluaran["html"]))
        except Exception as e:
            _log.note(e)

    def gambar(self, hasil, pratinjau=False):
        from . import lapisan
        nama = "Tembuku - map clicks" if pratinjau else "Tembuku - results"
        semua = hasil
        if pratinjau and self.panel is not None:
            semua = [h for h in self.panel.hasil if h["fdt"].get("berkas") == "klik peta"] + list(hasil)
        lapisan.tampilkan(semua, nama, ganti=nama)

    def tentang(self):
        from . import keaslian
        try:
            status = keaslian.status(False)
        except Exception as e:      # status keaslian tidak boleh membuat dialog gagal
            status = "not verified (%s)" % e
        box = QtWidgets.QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Tembuku")
        box.setText(
            "<b>Tembuku&trade; - Feeder Tap Designer</b> v%s<br>Author: Joseph Edward Timothy Siahaan<br>"
            "Integrity: %s<br><br>A <i>tembuku</i> is the water divider of the Balinese subak irrigation system: the "
            "place where the main channel is shared out to branch channels. In the same way, this plugin finds an "
            "existing feeder that still has free tubes and runs toward the FDT, then taps it to serve the FDT.<br><br>"
            "Licensed under the GNU GPL v3 or later with additional section 7 terms (see LICENSE). Official releases are "
            "digitally signed; official key fingerprint <b>92C4-D078-D1FC-1C5B</b> (the same key as Seranta and "
            "Seuntai).<br>Road data &copy; OpenStreetMap contributors (ODbL)." % (__version__, status))
        b_ver = box.addButton("Verify online", qtc.e(QtWidgets.QMessageBox, "ButtonRole", "ActionRole"))
        box.addButton(qtc.e(QtWidgets.QMessageBox, "StandardButton", "Ok"))
        qtc.jalankan(box)
        if box.clickedButton() is b_ver:
            try:
                kode, teks = keaslian.verify_online(lambda url: tugas.ambil(url))
            except Exception as e:  # tanpa internet / repositori belum terbit: laporkan, jangan galat
                kode, teks = "FAILED", str(e)[:160]
            (QtWidgets.QMessageBox.information if kode == "TERVERIFIKASI" else QtWidgets.QMessageBox.warning)(
                self.iface.mainWindow(), "Tembuku - online verification", teks)

    def bantuan(self, bagian=""):
        """Open the bundled offline help (no internet needed)."""
        p = os.path.join(HERE, "help", "index.html")
        url = qtc.QtCore.QUrl.fromLocalFile(p)
        if bagian:
            url.setFragment(bagian)
        QtGui.QDesktopServices.openUrl(url)
