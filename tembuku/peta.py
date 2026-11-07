# -*- coding: utf-8 -*-
# Tembuku - basemaps in QGIS: OpenStreetMap and CURRENT satellite imagery with a known date.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Three basemaps only, all current and all allowed for company use:
OpenStreetMap (live), the newest Copernicus quarterly cloud-free Sentinel-2 mosaic (moves forward by itself every
quarter) and Esri World Imagery (sharp, with the capture date at the map centre read from Esri's official metadata
service). Layers carry the custom property 'tembuku/peta'; when QGIS starts or a project opens they are moved to the
newest imagery and the capture date is checked again. Tiles are always streamed live and never stored offline."""
import urllib.parse

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
                       QgsRasterLayer, QgsSettings, QgsTask)
from qgis.PyQt import QtWidgets

from . import _log, tugas
from .inti import peta_dasar as P

PROP = "tembuku/peta"
LAMA = ("viirs", "hls", "eox2016", "sendiri")     # basemaps from earlier test builds, no longer offered


def _uri(url, zmax):
    return "type=xyz&url=%s&zmin=0&zmax=%d" % (urllib.parse.quote(url, safe=":/"), zmax)


def _nama_cdse():
    return "Satellite - cloud-free, newest up to %s (Copernicus quarterly, 10 m)" % P.kuartal_terakhir()


def _nama_esri(h=None):
    if h:
        return "Satellite - detailed (Esri), taken %s at map centre" % h["tanggal"].isoformat()
    return P.KATALOG["esri"]["nama"]


def cdse_akun(induk, tanya=True):
    """Instance ID and layer name of the user's OWN free Copernicus Data Space (Sentinel Hub) configuration."""
    st = QgsSettings()
    inst = st.value("tembuku/cdse_instance", "") or ""
    lay = st.value("tembuku/cdse_layer", "") or ""
    if (inst and lay) or not tanya:
        return inst, lay
    teks, ok = QtWidgets.QInputDialog.getText(
        induk, "Tembuku - latest cloud-free satellite (Copernicus)",
        "One-time setup (free, about 5 minutes; Help > Basemaps shows every click):\n"
        "1. Create a free account at dataspace.copernicus.eu\n"
        "2. In the Sentinel Hub dashboard, create a configuration and add a layer with data source\n"
        "   'Bring your own COG', collection %s (true colour)\n\n"
        "Paste here:  INSTANCE-ID  LAYER-NAME   (separated by a space)" % P.CDSE_KOLEKSI)
    if not ok:
        return "", ""
    bag = teks.split()
    if len(bag) != 2 or not (P.id_sah(bag[0]) and P.id_sah(bag[1])):
        QtWidgets.QMessageBox.warning(induk, "Tembuku", "Please paste the instance ID and the layer name, separated by "
                                      "one space (letters, numbers, '-' and '_' only).")
        return "", ""
    st.setValue("tembuku/cdse_instance", bag[0])
    st.setValue("tembuku/cdse_layer", bag[1])
    return bag[0], bag[1]


def esri_kunci(induk, tanya=True):
    st = QgsSettings()
    kunci = st.value("tembuku/esri_key", "") or ""
    if kunci or not tanya:
        return kunci
    kunci, ok = QtWidgets.QInputDialog.getText(
        induk, "Tembuku - detailed satellite",
        "Esri World Imagery needs your own ArcGIS Location Platform API key\n"
        "(free account: 2 million tiles per month; developers.arcgis.com).\n"
        "The key is saved in your QGIS profile and inside projects that use this layer.\n\nAPI key:")
    kunci = (kunci or "").strip()
    if not ok or not kunci:
        return ""
    if not P.kunci_esri_sah(kunci):
        QtWidgets.QMessageBox.warning(induk, "Tembuku", "That does not look like an ArcGIS API key (letters, numbers, "
                                      "'-', '_' and '.' only).")
        return ""
    st.setValue("tembuku/esri_key", kunci)
    return kunci


def _pasang(iface, kunci, url, zmax, nama, meta=None):
    lyr = QgsRasterLayer(_uri(url, zmax), nama, "wms")
    if not lyr.isValid():
        iface.messageBar().pushWarning("Tembuku", "The basemap could not be added (%s)." % nama)
        return None
    lyr.setCustomProperty(PROP, kunci)
    for k, v in (meta or {}).items():
        lyr.setCustomProperty("tembuku/" + k, v)
    atrib = (P.KATALOG.get(kunci) or {}).get("atrib", "")
    if kunci == "cdse":
        atrib = atrib % P.jendela_cdse()[1][:4]
    try:
        md = lyr.metadata()
        md.setRights([atrib] if atrib else [])
        lyr.setMetadata(md)
    except AttributeError as e:          # older QGIS without layer metadata rights
        _log.note(e)
    proj = QgsProject.instance()
    proj.addMapLayer(lyr, False)
    # below every result/data layer but ABOVE older basemaps, so the basemap just chosen is the one you see
    root = proj.layerTreeRoot()
    anak = root.children()
    posisi = len(anak)
    for i, node in enumerate(anak):
        lapis = getattr(node, "layer", lambda: None)()
        if lapis is not None and lapis.customProperty(PROP):
            posisi = i
            break
    root.insertLayer(posisi, lyr)
    return lyr


def _pusat_peta(iface):
    c = iface.mapCanvas()
    tr = QgsCoordinateTransform(c.mapSettings().destinationCrs(), QgsCoordinateReferenceSystem("EPSG:4326"),
                                QgsProject.instance())
    p = tr.transform(c.extent().center())
    return p.x(), p.y()


class TugasTanggal(QgsTask):
    """Reads the capture date of the Esri image at a point (two small requests to Esri's public metadata service)."""

    def __init__(self, lon, lat, selesai):
        super().__init__("Tembuku: reading the satellite capture date", tugas._enum(QgsTask, "Flag", "CanCancel"))
        self.lon, self.lat, self.selesai_cb, self.hasil = lon, lat, selesai, None

    def run(self):
        try:
            self.hasil = P.tanggal_esri(lambda u: tugas.ambil(u), self.lon, self.lat)
        except Exception as e:       # offline or service changed: report "unknown date", never fail
            _log.note(e)
            self.hasil = None
        return True

    def finished(self, ok):
        try:
            self.selesai_cb(self.hasil)
        except Exception as e:       # never break QGIS because of a basemap check
            _log.note(e)


_TUGAS = []      # keep references to running tasks


def _lapisan(kunci):
    return [lyr for lyr in QgsProject.instance().mapLayers().values() if lyr.customProperty(PROP) == kunci]


def cek_tanggal(plugin, diam=False):
    """Capture date of the detailed (Esri) image at the map centre -> layer name + message (warning if old)."""
    iface = plugin.iface
    lon, lat = _pusat_peta(iface)
    if not (-180 <= lon <= 180 and -85 <= lat <= 85):
        return

    def jadi(h):
        for lyr in _lapisan("esri"):
            lyr.setName(_nama_esri(h))
            if h:
                lyr.setCustomProperty("tembuku/tanggal", h["tanggal"].isoformat())
        if h and h["umur_bulan"] > P.UMUR_PERINGATAN:
            iface.messageBar().pushWarning("Tembuku", P.kalimat_umur(h))
        elif not diam or not h:
            iface.messageBar().pushInfo("Tembuku", P.kalimat_umur(h))
    t = TugasTanggal(lon, lat, jadi)
    _TUGAS.append(t)
    QgsApplication.taskManager().addTask(t)


def tambah(plugin, kunci):
    iface = plugin.iface
    if kunci == "osm":
        k = P.KATALOG["osm"]
        return _pasang(iface, kunci, k["url"], k["zmax"], k["nama"])
    if kunci == "cdse":
        inst, lay = cdse_akun(iface.mainWindow())
        if not inst:
            return None
        awal, akhir = P.jendela_cdse()
        lyr = _pasang(iface, kunci, P.url_cdse(inst, lay), P.KATALOG["cdse"]["zmax"], _nama_cdse(),
                      {"tanggal": akhir})
        if lyr is not None:
            iface.messageBar().pushInfo("Tembuku", "Cloud-free Copernicus mosaic added: newest quarter first, cloudy "
                                        "spots filled from earlier quarters (%s to %s). It moves forward by itself "
                                        "every quarter." % (awal, akhir))
        return lyr
    if kunci == "esri":
        kunci_api = esri_kunci(iface.mainWindow())
        if not kunci_api:
            return None
        k = P.KATALOG["esri"]
        lyr = _pasang(iface, kunci, P.url_lapis("esri", kunci_api), k["zmax"], _nama_esri())
        if lyr is not None:
            cek_tanggal(plugin)
        return lyr
    raise KeyError(kunci)


def segarkan(plugin):
    """At start / project load: move the Copernicus layer to the newest quarter, re-read the Esri capture date, and
    remove basemaps of earlier test builds that are no longer offered (old imagery must not mislead a current design)."""
    iface = plugin.iface
    hari_ini = P.hari_ini_utc().isoformat()
    proj = QgsProject.instance()
    ada_esri = False
    for lyr in list(proj.mapLayers().values()):
        kunci = lyr.customProperty(PROP)
        if kunci in LAMA:
            proj.removeMapLayer(lyr.id())
            iface.messageBar().pushInfo("Tembuku", "An old satellite basemap was removed from this project; use "
                                        "Vector > Tembuku > Basemaps for current imagery.")
            continue
        if kunci == "esri":
            ada_esri = True
        if kunci != "cdse" or lyr.customProperty("tembuku/dicek") == hari_ini:
            continue
        lyr.setCustomProperty("tembuku/dicek", hari_ini)
        inst, lay = cdse_akun(None, tanya=False)
        if inst:
            _ganti(lyr, P.url_cdse(inst, lay), P.KATALOG["cdse"]["zmax"], _nama_cdse(), hari_ini)
    if ada_esri:
        cek_tanggal(plugin, diam=True)


def _ganti(lyr, url, zmax, nama, tgl):
    try:
        lyr.setDataSource(_uri(url, zmax), nama, "wms")
    except (AttributeError, TypeError) as e:     # very old QGIS: keep the previous window
        _log.note(e)
        return
    lyr.setCustomProperty("tembuku/tanggal", tgl)
    lyr.triggerRepaint()
