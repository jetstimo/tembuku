# -*- coding: utf-8 -*-
"""Catatan kesalahan yang sengaja diabaikan (fitur opsional QGIS yang tidak ada di versi tertentu, file yang
sedang dikunci, dsb.). Dicatat ke panel Log Messages QGIS (tab Tembuku) supaya tetap bisa ditelusuri.

Part of Tembuku - Feeder Tap Designer.
Copyright (C) 2026 Joseph Edward Timothy Siahaan. Licensed under GPL-3.0-or-later (see LICENSE).
"""


def note(exc=None, where=""):
    """Catat pengecualian yang tidak menghentikan proses. Tidak pernah melempar kesalahan baru."""
    try:
        from qgis.core import Qgis, QgsMessageLog
        level = getattr(getattr(Qgis, "MessageLevel", Qgis), "Info")
        QgsMessageLog.logMessage("%s%s: %r" % (where + " " if where else "", type(exc).__name__, exc), "Tembuku", level)
    except Exception:  # di luar QGIS (uji unit) cukup diabaikan
        return None
    return None
