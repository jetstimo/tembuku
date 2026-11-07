# -*- coding: utf-8 -*-
# Tembuku - data jalan OpenStreetMap. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.
"""Jalan dipakai untuk menggambar jalur kabel baru (tiang baru mengikuti jalan). Sumber, berurutan:
  1. layer/berkas jalan milik pengguna (GPKG/SHP/GeoJSON/KML, mis. ekstrak Geofabrik), atau
  2. Overpass API, SATU permintaan per area, disimpan di cache (kebijakan pemakaian overpass-api.de: hemat permintaan).
Data (c) OpenStreetMap contributors, ODbL 1.0 - atribusi ditulis di KMZ dan laporan.
Faktor biaya per kelas jalan: jalan lingkungan 1,0; jalan utama 1,3 (izin & penyeberangan lebih berat)."""
import json

ATRIBUSI = "Data jalan (c) OpenStreetMap contributors, ODbL 1.0 - openstreetmap.org/copyright"
KELAS = ("trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link",
         "unclassified", "residential", "living_street", "service", "road", "track", "pedestrian")
FAKTOR = {"trunk": 1.3, "trunk_link": 1.3, "primary": 1.25, "primary_link": 1.25, "secondary": 1.1,
          "secondary_link": 1.1, "track": 1.4, "pedestrian": 1.5}


def query(bb):
    """bb=(minlon,minlat,maxlon,maxlat) -> teks query Overpass (urutan S,W,N,E)."""
    return ('[out:json][timeout:90];way["highway"~"^(%s)$"](%.6f,%.6f,%.6f,%.6f);out geom;'
            % ("|".join(KELAS), bb[1], bb[0], bb[3], bb[2]))


def parse_overpass(js):
    if isinstance(js, (bytes, str)):
        js = json.loads(js)
    out = []
    for el in js.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        hw = (el.get("tags") or {}).get("highway", "road")
        ll = [(float(g["lon"]), float(g["lat"])) for g in el["geometry"] if "lon" in g and "lat" in g]
        if len(ll) >= 2:
            out.append({"kelas": hw, "ll": ll, "nama": (el.get("tags") or {}).get("name", "")})
    return out


def faktor(kelas):
    return FAKTOR.get((kelas or "").lower(), 1.0)
