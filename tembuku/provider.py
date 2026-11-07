# -*- coding: utf-8 -*-
# Tembuku - penyedia Processing. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from . import __version__
from .alg import TembukuFolder


class TembukuProvider(QgsProcessingProvider):
    def id(self):
        return "tembuku"

    def name(self):
        return "Tembuku"

    def longName(self):
        return "Tembuku - Feeder Tap Designer v%s" % __version__

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))

    def loadAlgorithms(self):
        self.addAlgorithm(TembukuFolder())
