# -*- coding: utf-8 -*-
# Tembuku - algoritma Processing (untuk batch, model builder, skrip).
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
import os

from qgis.core import (QgsProcessingAlgorithm, QgsProcessingException, QgsProcessingParameterBoolean,
                       QgsProcessingParameterFile, QgsProcessingParameterFolderDestination)

from . import layanan, tugas


class TembukuFolder(QgsProcessingAlgorithm):
    FOLDER, OSM, KELUAR, UJI = "FOLDER", "OSM", "KELUAR", "UJI"

    def name(self):
        return "desain_feeder_folder"

    def displayName(self):
        return "Design feeders from a data folder"

    def shortHelpString(self):
        return ("Reads every KMZ/KML file in the folder (cable inventory, feeder design compilation, distribution or "
                "design-lite KMZ with the target FDTs, POP list) and checks it first: small typing mistakes are "
                "corrected and listed, while a missing or damaged required file stops the run. For each FDT it then "
                "looks for an existing feeder with free tubes that runs toward the FDT and draws the cable route from "
                "the tap point to the FDT, or proposes a new feeder from the POP.\n\nOutputs: one KMZ per FDT in the "
                "compilation template, a combined KMZ, an interactive offline HTML report, a CSV summary and the input "
                "check. The results are written in Indonesian.")

    def createInstance(self):
        return TembukuFolder()

    def initAlgorithm(self, config=None):
        try:                                    # QGIS >= 3.36 / 4.x
            from qgis.core import Qgis
            folder = Qgis.ProcessingFileParameterBehavior.Folder
        except (ImportError, AttributeError):
            folder = getattr(getattr(QgsProcessingParameterFile, "Behavior", QgsProcessingParameterFile), "Folder")
        self.addParameter(QgsProcessingParameterFile(self.FOLDER, "Data folder", behavior=folder))
        self.addParameter(QgsProcessingParameterBoolean(self.OSM, "Follow OpenStreetMap roads (uses the internet)", True))
        self.addParameter(QgsProcessingParameterBoolean(self.UJI, "Accuracy test: compare with the designs already in "
                                                        "the compilation (no target FDTs needed)", False))
        self.addParameter(QgsProcessingParameterFolderDestination(self.KELUAR, "Results folder"))

    def processAlgorithm(self, parameters, context, feedback):
        folder = self.parameterAsFile(parameters, self.FOLDER, context)
        keluar = self.parameterAsString(parameters, self.KELUAR, context)
        osm = self.parameterAsBoolean(parameters, self.OSM, context)
        uji = self.parameterAsBoolean(parameters, self.UJI, context) if self.UJI in parameters else False
        from .inti import sumber
        s = layanan.Sesi(sumber.cari_berkas(folder) if os.path.isdir(folder) else [folder], tugas.folder_cache(),
                         pakai_osm=osm, ambil=tugas.ambil,
                         progres=lambda t, p=None: (feedback.setProgressText(t), p is not None and
                                                    feedback.setProgress(p)),
                         batal=feedback.isCanceled)
        from qgis.core import QgsSettings
        server = QgsSettings().value("tembuku/overpass", layanan.OVERPASS) or layanan.OVERPASS
        s.overpass = server if str(server).lower().startswith("https://") else layanan.OVERPASS
        t = s.pra_cek(target_manual=uji)
        for x in t.daftar:
            (feedback.reportError if x["tingkat"] == "FATAL" else feedback.pushInfo)(
                "[%s] %s%s%s" % (x["tingkat"], x["berkas"] + ": " if x["berkas"] else "", x["pesan"],
                                 " -> " + x["saran"] if x["saran"] else ""))
        if t.fatal():
            raise QgsProcessingException("The input is not complete or not correct; see the FATAL messages above. "
                                         "Nothing was run.")
        try:
            s.muat()
            if uji:
                s.siapkan_uji()
            hasil = s.analisis()
            out = s.simpan(keluar)
        except layanan.Dibatalkan:
            raise QgsProcessingException("Cancelled.")
        if s.nilai_uji:
            from . import uji_akurasi
            feedback.pushInfo("ACCURACY TEST: %s" % uji_akurasi.ringkasan(s.nilai_uji))
        for h in hasil:
            feedback.pushInfo("%s: %s - %s" % (h["fdt"]["kode"], h["keputusan"], (h["alasan"] or [""])[0]))
        return {self.KELUAR: keluar, "LAPORAN": out["html"], "KMZ_GABUNGAN": out["semua"] or (out["kmz"] or [""])[0]}
