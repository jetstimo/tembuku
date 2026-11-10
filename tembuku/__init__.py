# -*- coding: utf-8 -*-
# Tembuku - Feeder Tap Designer - QGIS plugin
# Copyright (C) 2026 Joseph Edward Timothy Siahaan
# This program is free software; you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version, with the additional terms of section 7 in LICENSE
# (author attribution, no misrepresentation of origin, no trademark licence).

__version__ = "1.3.1"
__product__ = "Tembuku - Feeder Tap Designer"
__author__ = "Joseph Edward Timothy Siahaan"


def classFactory(iface):  # noqa: N802 - name required by QGIS
    from .plugin import TembukuPlugin
    return TembukuPlugin(iface)
