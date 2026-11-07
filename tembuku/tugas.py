# -*- coding: utf-8 -*-
# Tembuku - tugas latar belakang. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Pekerjaan berat (indeks kabel nasional, unduh jalan, analisis) berjalan di QgsTask agar QGIS tidak membeku; progres tampil
di bilah tugas QGIS dan dapat dibatalkan. Hasil diserahkan ke callback di thread utama (aman untuk menambah layer)."""
import os
import traceback

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsTask

from . import __version__, layanan


def _enum(cls, scope, name):
    sc = getattr(cls, scope, None)
    return getattr(sc, name) if sc is not None and hasattr(sc, name) else getattr(cls, name)


def folder_cache():
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "tembuku")


def ambil(url, data=None):
    """HTTP lewat jaringan QGIS (proxy & sertifikat pengguna ikut terpakai). Aman dipanggil dari QgsTask."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest
    req = QNetworkRequest(QUrl(url))
    hdr = getattr(getattr(QNetworkRequest, "KnownHeaders", QNetworkRequest), "ContentTypeHeader")
    req.setHeader(hdr, "application/x-www-form-urlencoded")
    # identifies the application uniquely, as the OpenStreetMap/Overpass usage policies ask
    req.setRawHeader(b"User-Agent", ("Tembuku/%s (QGIS plugin; +https://github.com/jetstimo/tembuku)"
                                     % __version__).encode("ascii"))
    br = QgsBlockingNetworkRequest()
    err = br.post(req, data or b"", True) if data is not None else br.get(req, True)
    if err != _enum(QgsBlockingNetworkRequest, "ErrorCode", "NoError"):
        raise IOError(br.errorMessage())
    return bytes(br.reply().content())


def log(teks, warn=False):
    lvl = getattr(getattr(Qgis, "MessageLevel", Qgis), "Warning" if warn else "Info")
    QgsMessageLog.logMessage(teks, "Tembuku", lvl)


def _pesan(e):
    """Plain-English summary of an unexpected error; the full technical trace goes to the QGIS log."""
    if isinstance(e, MemoryError):
        return "Not enough memory. Close other programs or process fewer files at a time."
    if isinstance(e, PermissionError):
        return "Tembuku may not write to that folder (%s). Choose another results folder." % (e.filename or "")
    if isinstance(e, OSError) and getattr(e, "filename", None):
        return "A file could not be read or written: %s (%s)." % (e.filename, e.strerror or e)
    return ("Unexpected problem: %s: %s. Details are in View > Panels > Log Messages > Tembuku; please send them to "
            "the author." % (type(e).__name__, e))


class TugasTembuku(QgsTask):
    """mode: 'batch' (muat + analisis + simpan), 'muat' (siapkan data untuk klik peta), 'titik' (analisis satu titik)."""

    def __init__(self, judul, sesi, mode, selesai, folder_keluar=None, titik=None):
        super().__init__(judul, _enum(QgsTask, "Flag", "CanCancel"))
        self.sesi, self.mode, self.selesai_cb = sesi, mode, selesai
        self.folder_keluar, self.titik = folder_keluar, titik
        self.keluaran, self.galat, self.hasil, self.teks = None, None, None, ""
        sesi._prog = self._progres
        sesi._batal = self.isCanceled

    def _progres(self, teks, persen=None):
        self.teks = teks                        # dibaca thread utama (panel), tidak menyentuh widget dari thread ini
        if persen is not None:
            self.setProgress(max(0.0, min(100.0, float(persen))))

    def run(self):
        try:
            s = self.sesi
            if self.mode in ("batch", "muat", "uji") and s.data is None:
                s.muat()
            if self.mode == "uji":
                s.siapkan_uji()
                self.hasil = s.analisis()
                self.keluaran = s.simpan(self.folder_keluar, alat="Tembuku - uji akurasi")
            elif self.mode == "batch":
                self.hasil = s.analisis()
                self.keluaran = s.simpan(self.folder_keluar)
            elif self.mode == "titik":
                self.hasil = [s.analisis_titik(*self.titik)]
            return True
        except layanan.Dibatalkan:
            self.galat = "Cancelled by the user."
            return False
        except Exception as e:      # galat tak terduga dicatat lengkap di Log Messages, pengguna melihat ringkasannya
            self.galat = _pesan(e)
            log(traceback.format_exc(), warn=True)
            return False

    def finished(self, ok):
        try:
            self.selesai_cb(self, ok)
        except Exception:
            log(traceback.format_exc(), warn=True)
