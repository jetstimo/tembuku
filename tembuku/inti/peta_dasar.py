# -*- coding: utf-8 -*-
# Tembuku - katalog peta dasar (OpenStreetMap & citra satelit TERKINI) untuk QGIS dan laporan HTML.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Prinsip: desain hari ini (tahun berapa pun) hanya boleh dibandingkan dengan peta yang TERKINI dan yang TANGGALNYA DIKETAHUI. Citra lama
(mis. mozaik 2016) dihapus karena rumah dan jalan baru tidak terlihat. Hanya tiga peta, semuanya sah untuk perusahaan:

1. OpenStreetMap standar (tile.openstreetmap.org) - diperbarui terus oleh kontributor; dipakai interaktif dengan atribusi
   dan User-Agent aplikasi, tidak diunduh massal / disimpan offline (OSMF Tile Usage Policy).
2. Copernicus Sentinel-2 L2A Quarterly Cloudless Mosaics (Copernicus Data Space Ecosystem) - BEBAS AWAN, 10 m, seluruh
   dunia termasuk seluruh Indonesia, satu mozaik per kuartal dan dirilis paling lambat sebulan setelah kuartal berakhir
   (CDSE, 16 Mar 2026). Lisensi Copernicus: bebas termasuk komersial. Lewat akun gratis & instance ID MILIK pengguna.
   Jendela 12 bulan + PRIORITY=mostRecent: piksel terbaru dipakai; yang masih berawan diisi kuartal sebelumnya.
   Tanggal label mozaik = awal kuartal (forum CDSE).
3. Esri World Imagery (Vantor, 0,3-0,5 m di kota-kota Indonesia; tanggal pemotretan berbeda per lokasi, umumnya
   2024-2025 pada pemeriksaan 7 Nov 2026) - hanya dengan kunci ArcGIS Location Platform milik pengguna. Tanggal
   pemotretan di lokasi DIBACA OTOMATIS dari layanan metadata resmi Esri (World_Imagery_Metadata_<tahun>_r<nn>, rilis
   terbaru = isi World Imagery saat ini), supaya engineer tahu umur citra yang sedang dilihat.

Tidak dipakai: mozaik EOX 2016 (terlalu lama), NASA HLS/VIIRS (30-375 m, sering berawan), EOX 2018+ (non-komersial),
Planet NICFI (berakhir Jan 2025; non-komersial), Google/Bing (ketentuan melarang akses langsung ke tile)."""
import datetime
import json
import re

ATRIB_OSM = "© OpenStreetMap contributors (ODbL) - openstreetmap.org/copyright"
ATRIB_ESRI = "Powered by Esri | Esri, Vantor, Earthstar Geographics, and the GIS User Community"
ATRIB_CDSE = "Contains modified Copernicus Sentinel data %s processed by Sentinel Hub | Copernicus Data Space Ecosystem"
CDSE_WMTS = "https://sh.dataspace.copernicus.eu/ogc/wmts/"
CDSE_KOLEKSI = "byoc-5460de54-082e-473a-b6ea-d5cbe3c17cca"   # Sentinel-2 L2A quarterly cloudless mosaics (CDSE)
ESRI_META = "https://metadata.maptiles.arcgis.com/arcgis/rest/services/"
UMUR_PERINGATAN = 12      # bulan: citra lebih tua dari ini diberi peringatan "bangunan/jalan baru mungkin belum terlihat"

KATALOG = {
    "osm": {
        "nama": "OpenStreetMap (live)",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "zmax": 19, "atrib": ATRIB_OSM,
        "ket": "Roads, buildings and places from OpenStreetMap; edits appear within minutes to days. Online only."},
    "cdse": {
        "nama": "Satellite - newest cloud-free, 10 m change check (Copernicus quarterly)",
        "zmax": 14, "atrib": ATRIB_CDSE, "kunci": True,
        "ket": "Use next to the detailed view to see what changed since its capture date. Newest cloud-free 3-month mosaic for the whole of Indonesia, published within a month after each "
               "quarter; still-cloudy spots are filled from the previous quarters. Shows new roads, land clearing and "
               "new housing areas; single houses are too small at 10 m. Free for companies. Needs your own free "
               "Copernicus Data Space account (one-time setup)."},
    "esri": {
        "nama": "Satellite - detailed 0.3-0.5 m, houses visible (Esri World Imagery, with capture date)",
        "url": "https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
               "?token={kunci}", "zmax": 19, "atrib": ATRIB_ESRI, "kunci": True,
        "ket": "Recommended satellite view: sharp enough to see houses, roads, poles and trees when zoomed in; a "
               "curated mosaic of mostly cloud-free pictures. Not daily: Tembuku shows "
               "the date the picture was taken at the map centre and warns if it is older than 12 months. Needs your "
               "own ArcGIS Location Platform API key (2 million free tiles per month)."},
}
URUTAN = ("osm", "esri", "cdse")   # citra tajam (rumah terlihat) adalah satelit utama


def hari_ini_utc():
    return datetime.datetime.now(datetime.timezone.utc).date()


def jendela_cdse(hari_ini=None, bulan=12):
    """Rentang TIME untuk mozaik kuartalan: 12 bulan terakhir. Dengan PRIORITY=mostRecent, piksel yang masih kosong
    (berawan sepanjang kuartal terbaru) diisi dari kuartal sebelumnya - hasilnya sebersih mungkin dan tetap terbaru."""
    d = hari_ini or hari_ini_utc()
    y, m = d.year, d.month - bulan
    while m <= 0:
        y, m = y - 1, m + 12
    awal = datetime.date(y, ((m - 1) // 3) * 3 + 1, 1)
    return awal.isoformat(), d.isoformat()


def kuartal_terakhir(hari_ini=None):
    """Label kuartal lengkap terakhir, mis. 'Q3-2026' (mozaik kuartal berjalan belum lengkap)."""
    d = hari_ini or hari_ini_utc()
    q = (d.month - 1) // 3
    return ("Q4-%d" % (d.year - 1)) if q == 0 else ("Q%d-%d" % (q, d.year))


def url_cdse(instance, layer, hari_ini=None):
    awal, akhir = jendela_cdse(hari_ini)
    return ("%s%s?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=%s&STYLE=default&FORMAT=image/jpeg"
            "&TILEMATRIXSET=PopularWebMercator256&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&TIME=%s/%s"
            "&PRIORITY=mostRecent" % (CDSE_WMTS, instance.strip(), layer.strip(), awal, akhir))


def id_sah(teks):
    """Instance ID / nama layer Sentinel Hub: huruf, angka, '-' dan '_' saja (tidak ada karakter URL)."""
    t = (teks or "").strip()
    return 0 < len(t) <= 80 and all(c.isalnum() or c in "-_" for c in t)


def kunci_esri_sah(teks):
    """Kunci API ArcGIS: karakter aman URL saja (huruf, angka, '-', '_', '.')."""
    t = (teks or "").strip()
    return 20 <= len(t) <= 600 and all(c.isalnum() or c in "-_." for c in t)


def url_lapis(kunci, kunci_api=""):
    """URL XYZ untuk QGIS / Leaflet. {z}/{x}/{y} dipertahankan apa adanya."""
    if kunci == "osm":
        return KATALOG["osm"]["url"]
    if kunci == "esri":
        return KATALOG["esri"]["url"].replace("{kunci}", kunci_api.strip())
    raise KeyError(kunci)


# ---------- tanggal pemotretan citra Esri (layanan metadata resmi, tanpa kunci) ----------
_POLA_META = re.compile(r"^World_Imagery_Metadata_(\d{4})_r(\d+)$")


def meta_terbaru(daftar_json):
    """Dari ESRI_META?f=json pilih rilis metadata terbaru (sama dengan isi World Imagery saat ini)."""
    d = json.loads(daftar_json) if isinstance(daftar_json, (str, bytes)) else daftar_json
    calon = []
    for s in d.get("services", []):
        m = _POLA_META.match(s.get("name", ""))
        if m and s.get("type", "MapServer") == "MapServer":
            calon.append((int(m.group(1)), int(m.group(2)), s["name"]))
    return max(calon)[2] if calon else None


def url_identify(layanan, lon, lat):
    return ("%s%s/MapServer/identify?geometry=%.6f,%.6f&geometryType=esriGeometryPoint&sr=4326&layers=all"
            "&tolerance=0&mapExtent=%.6f,%.6f,%.6f,%.6f&imageDisplay=400,400,96&returnGeometry=false&f=json"
            % (ESRI_META, layanan, lon, lat, lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01))


def _tgl_esri(a):
    """SRC_DATE2 'M/D/YYYY' atau SRC_DATE 'YYYYMMDD' / epoch ms -> datetime.date."""
    t = a.get("SRC_DATE2")
    if isinstance(t, str) and t.count("/") == 2:
        b, h, y = (int(x) for x in t.split("/"))
        return datetime.date(y, b, h)
    t = a.get("SRC_DATE")
    if isinstance(t, (int, float)) and t > 10 ** 9:
        return datetime.datetime.fromtimestamp(t / 1000.0, datetime.timezone.utc).date()
    t = str(t or "")
    if len(t) == 8 and t.isdigit():
        return datetime.date(int(t[:4]), int(t[4:6]), int(t[6:]))
    return None


def baca_identify(isi):
    """Hasil identify -> dict(tanggal, resolusi_m, sumber) dari lapisan resolusi TERTINGGI yang ada, atau None."""
    d = json.loads(isi) if isinstance(isi, (str, bytes)) else isi
    for r in d.get("results", []) or []:          # urutan layanan: resolusi tertinggi lebih dulu
        a = r.get("attributes") or {}
        tgl = _tgl_esri(a)
        if tgl:
            try:
                res = float(a.get("SRC_RES"))
            except (TypeError, ValueError):
                res = None
            return {"tanggal": tgl, "resolusi_m": res, "sumber": a.get("NICE_DESC") or a.get("SRC_DESC") or ""}
    return None


def umur_bulan(tgl, hari_ini=None):
    d = hari_ini or hari_ini_utc()
    return (d.year - tgl.year) * 12 + (d.month - tgl.month) - (1 if d.day < tgl.day else 0)


def tanggal_esri(ambil, lon, lat, layanan=None):
    """ambil(url) -> bytes. Mengembalikan dict baca_identify + 'umur_bulan' dan 'layanan', atau None bila gagal."""
    if not layanan:
        layanan = meta_terbaru(ambil(ESRI_META + "?f=json"))
    if not layanan:
        return None
    h = baca_identify(ambil(url_identify(layanan, lon, lat)))
    if h:
        h["umur_bulan"] = umur_bulan(h["tanggal"])
        h["layanan"] = layanan
    return h


def kalimat_umur(h):
    """Kalimat untuk pengguna (bahasa Inggris, UI)."""
    if not h:
        return "The capture date of the detailed satellite image here could not be read (no internet?)."
    t = h["tanggal"].strftime("%d %b %Y")
    res = (" at %.1f m" % h["resolusi_m"]) if h.get("resolusi_m") else ""
    if h["umur_bulan"] > UMUR_PERINGATAN:
        return ("Detailed satellite image here was taken on %s%s (%d months ago): houses and roads built since then "
                "are NOT visible. Check against OpenStreetMap, the Copernicus quarterly mosaic or a field survey."
                % (t, res, h["umur_bulan"]))
    return "Detailed satellite image here was taken on %s%s (%d months ago)." % (t, res, max(0, h["umur_bulan"]))
