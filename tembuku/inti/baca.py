# -*- coding: utf-8 -*-
# Tembuku - pembaca data peta dari berbagai format, dikenali dari ISI berkas.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Semua pembaca menghasilkan objek yang sama dengan kml_aman.placemarks():
dict(path=[folder...], name, desc, geoms=[("Point"|"LineString", [(lon, lat), ...])], attrs, style, warna, ikon).

Format dikenali dari isi (magic bytes / struktur), ekstensi hanya petunjuk:
  KML / KMZ   - Google Earth, ekspor ArcGIS/QGIS/AutoCAD Map; KMZ bernama .kml (dan sebaliknya) tetap terbaca;
  ZIP         - satu zip berisi banyak KMZ/KML/GeoJSON/CSV/Excel/Shapefile: isinya diambil dengan aman (tanpa folder,
                tanpa '..', batas ukuran) lalu dibaca satu per satu;
  GeoJSON     - RFC 7946 (WGS 84 lon/lat);
  CSV / TXT   - tabel titik dengan kolom lintang/bujur (nama kolom Indonesia atau Inggris, pemisah , ; tab |, desimal
                koma), kolom koordinat gabungan 'lat, lon', atau kolom WKT;
  Excel XLSX  - lembar pertama, aturan kolom sama dengan CSV (dibaca langsung, tanpa paket tambahan);
  Shapefile, GeoPackage, GML, MapInfo TAB, FlatGeobuf, GPX - lewat GDAL/OGR yang selalu ada di QGIS; koordinat
                diubah ke WGS 84 dari sistem koordinat layer."""
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET  # nosec B405 - DOCTYPE/ENTITY ditolak sebelum parsing
import zipfile

from . import atribut, kml_aman
from .kml_aman import BerkasDitolak

EKST_OGR = (".shp", ".gpkg", ".gml", ".tab", ".fgb", ".gpx", ".sqlite")
EKST_DATA = (".kmz", ".kml", ".zip", ".geojson", ".json", ".csv", ".txt", ".xlsx") + EKST_OGR
EKST_PETA_ZIP = (".kmz", ".kml", ".geojson", ".csv", ".xlsx") + EKST_OGR   # isi ZIP yang dianggap data peta
MAKS_TABEL = 512 * 1024 ** 2        # GeoJSON/CSV/XLSX: batas ukuran baca (berkas tabel sebesar ini tidak lazim)

NAMA_FORMAT = {"KML": "KML", "KMZ": "KMZ", "ZIP": "ZIP", "GEOJSON": "GeoJSON", "CSV": "CSV", "XLSX": "Excel",
               "OGR": "GIS (GDAL)"}


def _ogr():
    try:
        from osgeo import ogr, osr  # noqa: F401  (tersedia di setiap instalasi QGIS)
        return ogr, osr
    except ImportError:
        return None, None


def rusak(path):
    """True bila berkas tampak seperti data peta (tanda zip, atau ekstensi peta) tapi isinya tidak utuh."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    if head[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as zf:
                return zf.testzip() is not None if os.path.getsize(path) < (64 << 20) else False
        except (zipfile.BadZipFile, OSError, EOFError, ValueError, RuntimeError):
            return True
    return path.lower().endswith((".kmz", ".kml", ".geojson"))


def jenis(path):
    """Format berkas dari isinya. -> 'KML'|'KMZ'|'ZIP'|'GEOJSON'|'CSV'|'XLSX'|'OGR'|None."""
    low = path.lower()
    try:
        if os.path.getsize(path) == 0:
            return None
        with open(path, "rb") as fh:
            head = fh.read(65536)
    except OSError:
        return None
    if head[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as zf:
                nama = [i.filename.lower() for i in zf.infolist()[:kml_aman.MAKS_ENTRI]]
        except zipfile.BadZipFile:
            return None
        if any(n.endswith(".kml") for n in nama) and not any(n.startswith(("ppt/", "word/")) for n in nama):
            return "KMZ"
        if "xl/workbook.xml" in nama:
            return "XLSX"
        if any(n.endswith(EKST_PETA_ZIP) for n in nama):
            return "ZIP"
        return None
    t = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    tl = t.lower()
    if (tl.startswith(b"<?xml") or tl.startswith(b"<kml")) and b"<kml" in head.lower():
        return "KML"
    if t[:1] in (b"{", b"[") and (b'"features"' in head or b'"geometry"' in head or b'"FeatureCollection"' in head):
        return "GEOJSON"
    if low.endswith(EKST_OGR):
        ogr, _osr = _ogr()
        return "OGR" if ogr is not None else None
    if low.endswith((".csv", ".txt", ".tsv")) or b"," in head[:2000] or b";" in head[:2000] or b"\t" in head[:2000]:
        try:
            teks = head.decode("utf-8-sig")
        except UnicodeDecodeError:
            teks = head.decode("latin-1")
        baris = [b for b in teks.splitlines() if b.strip()][:2]
        if baris and _kolom_koordinat(_pecah(baris[0], _pemisah(teks))):
            return "CSV"
    return None


def placemarks(path, bbox=None, progres=None):
    """Iterasi objek dari berkas apa pun yang dikenali (lihat jenis())."""
    j = jenis(path)
    if j in ("KML", "KMZ"):
        return kml_aman.placemarks(path, bbox, progres)
    if j == "GEOJSON":
        return _saring(_geojson(path), bbox)
    if j == "CSV":
        return _saring(_tabel(_baris_csv(path), path), bbox)
    if j == "XLSX":
        return _saring(_tabel(_baris_xlsx(path), path), bbox)
    if j == "OGR":
        return _saring(_ogr_baca(path), bbox)
    if j == "ZIP":
        raise BerkasDitolak("ZIP berisi beberapa berkas: buka lewat folder data agar isinya dibaca satu per satu")
    raise BerkasDitolak("bukan data peta yang dikenali (KMZ, KML, GeoJSON, CSV, Excel, Shapefile, GeoPackage)")


def _saring(gen, bbox):
    for pm in gen:
        if bbox is None:
            yield pm
            continue
        for _g, cs in pm["geoms"]:
            xs = [c[0] for c in cs]
            ys = [c[1] for c in cs]
            if max(xs) >= bbox[0] and min(xs) <= bbox[2] and max(ys) >= bbox[1] and min(ys) <= bbox[3]:
                yield pm
                break


def _pm(name, attrs, geoms, path):
    return {"path": [p for p in path if p], "name": str(name or "").strip(), "desc": "", "geoms": geoms,
            "attrs": {str(k): ("" if v is None else str(v)) for k, v in attrs.items()}, "style": "", "warna": None,
            "ikon": None}


def _nama_objek(attrs):
    for makna in ("kode_fdt", "nama", "pop"):
        v = atribut.nilai(attrs, makna)
        if v is not None:
            return v
    return ""


# ---------------------------------------------------------------------------- GeoJSON
def _cek_derajat(cs, path):
    for x, y in cs[:5]:
        if abs(x) > 180 or abs(y) > 180:
            raise BerkasDitolak("koordinat bukan derajat lintang/bujur (WGS 84) - ekspor ulang dalam EPSG:4326")


def _geom_ke_daftar(g):
    """Geometri GeoJSON -> [(jenis, [(lon, lat)...])]. Poligon diambil batas luarnya sebagai garis."""
    if not g:
        return []
    t, c = g.get("type"), g.get("coordinates")
    try:
        if t == "Point":
            return [("Point", [(float(c[0]), float(c[1]))])]
        if t == "MultiPoint":
            return [("Point", [(float(p[0]), float(p[1]))]) for p in c]
        if t == "LineString":
            return [("LineString", [(float(p[0]), float(p[1])) for p in c])]
        if t == "MultiLineString":
            return [("LineString", [(float(p[0]), float(p[1])) for p in ln]) for ln in c]
        if t == "Polygon":
            return [("LineString", [(float(p[0]), float(p[1])) for p in c[0]])] if c else []
        if t == "MultiPolygon":
            return [("LineString", [(float(p[0]), float(p[1])) for p in pg[0]]) for pg in c if pg]
        if t == "GeometryCollection":
            out = []
            for x in g.get("geometries") or []:
                out += _geom_ke_daftar(x)
            return out
    except (TypeError, ValueError, IndexError):
        return []
    return []


def _geojson(path):
    if os.path.getsize(path) > MAKS_TABEL:
        raise BerkasDitolak("GeoJSON terlalu besar (> %d MB)" % (MAKS_TABEL >> 20))
    with open(path, "rb") as fh:
        try:
            d = json.loads(fh.read().decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as e:
            raise BerkasDitolak("GeoJSON rusak: %s" % str(e)[:80])
    fitur = d.get("features") if isinstance(d, dict) else d
    if isinstance(d, dict) and d.get("type") == "Feature":
        fitur = [d]
    stem = os.path.splitext(os.path.basename(path))[0]
    for f in fitur or []:
        if not isinstance(f, dict):
            continue
        prop = f.get("properties") or {}
        geoms = [(j, cs) for j, cs in _geom_ke_daftar(f.get("geometry")) if cs]
        if not geoms:
            continue
        _cek_derajat(geoms[0][1], path)
        folder = prop.get("folder") or prop.get("Folder") or prop.get("layer") or prop.get("Layer") or ""
        yield _pm(_nama_objek(prop) or prop.get("name") or prop.get("Name") or "", prop, geoms,
                  [stem] + [x for x in str(folder).split("/") if x])


# ---------------------------------------------------------------------------- tabel (CSV / Excel)
LAT = ["LAT", "LATITUDE", "LINTANG", "Y", "YCOORD", "KOORDINATY", "COORDY", "LATDEC", "LATITUDEDEC"]
LON = ["LON", "LONG", "LNG", "LONGITUDE", "BUJUR", "X", "XCOORD", "KOORDINATX", "COORDX", "LONGDEC", "LONGITUDEDEC"]
GABUNG = ["KOORDINAT", "KOORDINATE", "COORDINATE", "COORDINATES", "LATLONG", "LATLON", "LATLNG", "LOKASI",
          "LOCATION", "POSISI", "TITIK", "COORD"]
WKT = ["WKT", "GEOMETRY", "GEOM", "THEGEOM", "SHAPE"]


def _pemisah(teks):
    sampel = "\n".join(teks.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sampel, delimiters=",;\t|").delimiter
    except csv.Error:
        return max(",;\t|", key=lambda c: sampel.count(c))


def _pecah(baris, sep):
    return next(csv.reader([baris], delimiter=sep))


def _kolom_koordinat(header):
    n = [atribut.norm(h) for h in header]
    i_lat = next((n.index(k) for k in LAT if k in n), None)
    i_lon = next((n.index(k) for k in LON if k in n), None)
    if i_lat is not None and i_lon is not None:
        return ("LATLON", i_lat, i_lon)
    i_g = next((n.index(k) for k in GABUNG if k in n), None)
    if i_g is not None:
        return ("GABUNG", i_g, None)
    i_w = next((n.index(k) for k in WKT if k in n), None)
    if i_w is not None:
        return ("WKT", i_w, None)
    return None


def _desimal(s):
    s = str(s or "").strip().replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    return float(s)


RX_WKT = re.compile(r"^\s*(POINT|LINESTRING|MULTILINESTRING|MULTIPOINT)\s*Z?\s*\((.*)\)\s*$", re.I | re.S)


def _wkt(s):
    m = RX_WKT.match(s or "")
    if not m:
        return []
    jenis_, isi = m.group(1).upper(), m.group(2)
    def pasangan(t):
        out = []
        for p in t.split(","):
            v = p.strip().strip("()").split()
            if len(v) >= 2:
                out.append((float(v[0]), float(v[1])))
        return out
    if jenis_ == "POINT":
        return [("Point", pasangan(isi)[:1])]
    if jenis_ == "MULTIPOINT":
        return [("Point", [p]) for p in pasangan(isi.replace("(", "").replace(")", ""))]
    if jenis_ == "LINESTRING":
        return [("LineString", pasangan(isi))]
    return [("LineString", pasangan(x)) for x in re.findall(r"\(([^()]*)\)", isi)]


def _tabel(baris_iter, path):
    """Baris tabel (baris pertama = judul kolom) -> objek titik/garis."""
    stem = os.path.splitext(os.path.basename(path))[0]
    it = iter(baris_iter)
    header = None
    for b in it:
        if b and any(str(x).strip() for x in b):
            header = [str(x).strip() for x in b]
            break
    if header is None:
        return
    kk = _kolom_koordinat(header)
    if kk is None:
        raise BerkasDitolak("tabel tidak punya kolom koordinat (mis. LAT/LON, LINTANG/BUJUR, KOORDINAT atau WKT)")
    mode, a, b2 = kk
    for b in it:
        if not b or not any(str(x).strip() for x in b):
            continue
        row = {header[i]: (b[i] if i < len(b) else "") for i in range(len(header)) if header[i]}
        try:
            if mode == "LATLON":
                geoms = [("Point", [(_desimal(b[b2]), _desimal(b[a]))])]
            elif mode == "GABUNG":
                v = re.split(r"[;,\s]+", str(b[a]).strip())
                v = [x for x in v if x]
                if len(v) < 2:
                    continue
                y, x = float(v[0]), float(v[1])          # kebiasaan umum: 'lintang, bujur' (Google Maps)
                geoms = [("Point", [(x, y)])]
            else:
                geoms = _wkt(b[a])
        except (ValueError, IndexError):
            geoms = []                                   # baris koordinat rusak: dilewati di bawah
        geoms = [(j, cs) for j, cs in geoms if cs]
        if not geoms:
            continue
        _cek_derajat(geoms[0][1], path)
        yield _pm(_nama_objek(row), row, geoms, [stem])


def _baris_csv(path):
    if os.path.getsize(path) > MAKS_TABEL:
        raise BerkasDitolak("tabel terlalu besar (> %d MB)" % (MAKS_TABEL >> 20))
    raw = open(path, "rb").read()
    try:
        teks = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        teks = raw.decode("latin-1")
    return csv.reader(io.StringIO(teks), delimiter=_pemisah(teks))


def _xml_aman(b):
    kml_aman._cek_prolog(b[:kml_aman.PROLOG])
    return ET.fromstring(b)  # nosec B314 - DOCTYPE/ENTITY ditolak di atas


def _baris_xlsx(path):
    """Lembar pertama XLSX -> daftar baris (teks). Hanya nilai sel; rumus tidak dihitung ulang (nilai tersimpan)."""
    if os.path.getsize(path) > MAKS_TABEL:
        raise BerkasDitolak("Excel terlalu besar (> %d MB)" % (MAKS_TABEL >> 20))
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        isi = {i.filename for i in zf.infolist()}
        total = sum(i.file_size for i in zf.infolist())
        if total > 4 * MAKS_TABEL:
            raise BerkasDitolak("isi Excel melebihi batas aman")
        ss = []
        if "xl/sharedStrings.xml" in isi:
            for si in _xml_aman(zf.read("xl/sharedStrings.xml")).iter(ns + "si"):
                ss.append("".join(t.text or "" for t in si.iter(ns + "t")))
        lembar = "xl/worksheets/sheet1.xml"
        if lembar not in isi:
            lembar = sorted(n for n in isi if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))[0]
        root = _xml_aman(zf.read(lembar))
    out = []
    for r in root.iter(ns + "row"):
        baris = {}
        for c in r.iter(ns + "c"):
            ref = c.get("r") or ""
            kol = 0
            for ch in re.match(r"[A-Z]*", ref).group(0):
                kol = kol * 26 + (ord(ch) - 64)
            v = c.find(ns + "v")
            t = c.get("t")
            if t == "s" and v is not None:
                teks = ss[int(v.text)] if v.text and int(v.text) < len(ss) else ""
            elif t == "inlineStr":
                teks = "".join(x.text or "" for x in c.iter(ns + "t"))
            else:
                teks = v.text if v is not None and v.text is not None else ""
            baris[(kol or len(baris) + 1) - 1] = teks
        if baris:
            out.append([baris.get(i, "") for i in range(max(baris) + 1)])
    return out


# ---------------------------------------------------------------------------- GDAL/OGR (di QGIS)
def _ogr_baca(path):
    ogr, osr = _ogr()
    if ogr is None:
        raise BerkasDitolak("format ini butuh GDAL (tersedia di QGIS)")
    ds = ogr.Open(path, 0)
    if ds is None:
        raise BerkasDitolak("berkas tidak bisa dibuka oleh GDAL")
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    urut_xy = getattr(osr, "OAMS_TRADITIONAL_GIS_ORDER", None)      # GDAL >= 3: urutan bujur, lintang
    if urut_xy is not None:
        wgs.SetAxisMappingStrategy(urut_xy)
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayer(i)
        srs = lyr.GetSpatialRef()
        tr = None
        if srs is not None:
            if urut_xy is not None:
                srs.SetAxisMappingStrategy(urut_xy)
            if not srs.IsSame(wgs):
                tr = osr.CoordinateTransformation(srs, wgs)
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None:
                continue
            g = g.Clone()
            if tr is not None:
                g.Transform(tr)
            geoms = [(j, cs) for j, cs in _geom_ke_daftar(json.loads(g.ExportToJson())) if cs]
            if not geoms:
                continue
            attrs = {k: v for k, v in f.items().items()}
            yield _pm(_nama_objek(attrs), attrs, geoms, [lyr.GetName()])


# ---------------------------------------------------------------------------- ZIP berisi banyak berkas
def buka_zip(path, folder_kerja=None, maks_total=2 * 1024 ** 3):
    """Ambil berkas data dari ZIP ke folder kerja (nama diratakan, tanpa folder dan '..'; batas ukuran dan jumlah).
    -> daftar path berkas yang diambil. Shapefile diambil bersama berkas pendampingnya (.dbf .shx .prj .cpg)."""
    with open(path, "rb") as fh:
        sidik = hashlib.sha256(fh.read(8 << 20) + str(os.path.getsize(path)).encode()).hexdigest()[:16]
    tujuan = os.path.join(folder_kerja or os.path.join(tempfile.gettempdir(), "tembuku_zip"), sidik)
    os.makedirs(tujuan, exist_ok=True)
    out, total = [], 0
    with zipfile.ZipFile(path) as zf:
        info = zf.infolist()
        if len(info) > kml_aman.MAKS_ENTRI:
            raise BerkasDitolak("ZIP berisi terlalu banyak entri (%d)" % len(info))
        pendamping = (".dbf", ".shx", ".prj", ".cpg", ".qix", ".sbn", ".sbx")
        for i in info:
            n = i.filename
            if i.is_dir() or not kml_aman._nama_aman(n):
                continue
            low = n.lower()
            if not (low.endswith(EKST_PETA_ZIP) or low.endswith(pendamping)):
                continue
            total += i.file_size
            if total > maks_total or (i.compress_size and i.file_size / max(i.compress_size, 1) > kml_aman.MAKS_RASIO):
                raise BerkasDitolak("isi ZIP melebihi batas aman")
            datar = re.sub(r"[^\w.\- ]", "_", n.replace("\\", "/").replace("/", "__"))[-180:]
            p = os.path.join(tujuan, datar)
            if not os.path.exists(p) or os.path.getsize(p) != i.file_size:
                with zf.open(i) as src, open(p, "wb") as dst:
                    while True:
                        b = src.read(1 << 20)
                        if not b:
                            break
                        dst.write(b)
            if low.endswith(EKST_PETA_ZIP) and not low.endswith(pendamping):
                out.append(p)
    return out
