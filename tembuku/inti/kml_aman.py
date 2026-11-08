# -*- coding: utf-8 -*-
# Tembuku - Feeder Tap Designer - pembaca KMZ/KML aman dan streaming
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Membaca KMZ/KML yang tidak dipercaya tanpa memuat seluruh berkas ke memori.

Pengaman (OWASP XXE & File Upload Cheat Sheet; Snyk Zip Slip 2018):
  * KMZ TIDAK diekstrak ke disk: entri KML dibaca langsung sebagai stream dari zip (tidak ada zip-slip);
  * nama entri absolut / berisi '..' / huruf drive ditolak; jumlah entri dibatasi;
  * batas ukuran setelah dekompresi dan rasio kompresi (zip bomb) dihitung saat membaca, bukan dari header;
  * berkas dengan <!DOCTYPE atau <!ENTITY ditolak (KML sah tidak memerlukannya: XXE / billion laughs);
  * teks deskripsi tidak pernah dijalankan sebagai HTML (penulis KMZ dan laporan meng-escape semua teks).
"""
import os
import re
import xml.etree.ElementTree as ET  # nosec B405 - DOCTYPE/ENTITY ditolak sebelum parsing (lihat _cek_prolog)
import zipfile

from . import atribut

MAKS_ENTRI = 5000
MAKS_BYTE = 4 * 1024 ** 3          # 4 GB setelah dekompresi (KML kabel nasional Jawa 0,8 GB)
MAKS_RASIO = 200                   # zip bomb: KMZ kabel nasional ~11:1
PROLOG = 1024 * 1024


class BerkasDitolak(Exception):
    """KMZ/KML tidak aman atau rusak."""


class _Hitung(object):
    """Pembungkus stream yang menghitung byte terbaca dan menghentikan zip bomb."""

    def __init__(self, fh, batas):
        self.fh, self.batas, self.n = fh, batas, 0

    def read(self, k=-1):
        b = self.fh.read(k if k and k > 0 else 1 << 20)
        self.n += len(b)
        if self.n > self.batas:
            raise BerkasDitolak("isi KMZ melebihi batas aman (%d MB)" % (self.batas // 1048576))
        return b

    def close(self):
        self.fh.close()


def _nama_aman(n):
    return not (n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/") or re.match(r"^[A-Za-z]:", n))


def _cek_prolog(head):
    up = head.upper()
    if b"<!DOCTYPE" in up or b"<!ENTITY" in up:
        raise BerkasDitolak("berkas memuat DOCTYPE/ENTITY (tidak lazim untuk KML, ditolak demi keamanan)")


def jenis_isi(path):
    """Jenis berkas dari ISI (magic bytes), bukan ekstensi: 'KMZ', 'KML', 'ZIP' (zip tanpa KML), atau None."""
    with open(path, "rb") as fh:
        head = fh.read(65536)
    if head[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(path) as zf:
                nama = [i.filename.lower() for i in zf.infolist()[:MAKS_ENTRI]]
        except zipfile.BadZipFile:
            return None
        return "KMZ" if any(n.endswith(".kml") for n in nama) else "ZIP"
    teks = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if teks.startswith(b"<?xml") or teks.startswith(b"<kml"):
        return "KML" if b"<kml" in head.lower() else None
    return None


def buka(path):
    """-> objek file KML (stream) yang aman. KMZ: entri doc.kml atau .kml pertama. Jenis dikenali dari isi berkas,
    jadi KMZ yang diberi nama .kml (atau sebaliknya) tetap terbaca."""
    jenis = jenis_isi(path)
    if jenis == "KML":
        size = os.path.getsize(path)
        fh = open(path, "rb")
        _cek_prolog(fh.read(PROLOG))
        fh.seek(0)
        return _Hitung(fh, max(size, 1) + 1)
    if jenis is None:
        raise BerkasDitolak("bukan KMZ/KML yang sah")
    if not zipfile.is_zipfile(path):
        raise BerkasDitolak("bukan KMZ/zip yang sah")
    zf = zipfile.ZipFile(path)
    info = zf.infolist()
    if len(info) > MAKS_ENTRI:
        raise BerkasDitolak("KMZ berisi terlalu banyak entri (%d)" % len(info))
    kml = [i for i in info if i.filename.lower().endswith(".kml") and _nama_aman(i.filename)]
    if not kml:
        raise BerkasDitolak("KMZ tidak berisi KML")
    pilih = next((i for i in kml if i.filename.lower() == "doc.kml"), kml[0])
    batas = min(MAKS_BYTE, max(64 * 1024 ** 2, pilih.compress_size * MAKS_RASIO))
    with zf.open(pilih) as fh:
        _cek_prolog(fh.read(PROLOG))
    return _Hitung(zf.open(pilih), batas)


def _ln(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _angka(s):
    try:
        return float(s)
    except ValueError:
        return None


def _coords(txt, maks=2_000_000):
    out = []
    for tok in (txt or "").split():
        p = tok.split(",")
        if len(p) >= 2:
            x = _angka(p[0])
            y = _angka(p[1])
            if x is not None and y is not None and -180 <= x <= 180 and -180 <= y <= 180:      # lat/lon tertukar dikoreksi di validasi
                out.append((x, y))
                if len(out) >= maks:
                    break
    return out


def placemarks(path, bbox=None, progres=None):
    """Iterasi Placemark: dict(path, name, desc, geoms[(jenis, [(lon,lat)..])], attrs, style, warna).
    bbox=(minlon,minlat,maxlon,maxlat) menyaring geometri yang tidak bersinggungan (hemat memori)."""
    src = buka(path)
    styles, smap = {}, {}
    try:
        ctx = ET.iterparse(src, events=("start", "end"))  # nosec B314 - prolog sudah diperiksa
        tags, els, folders = [], [], []
        k = 0
        for ev, el in ctx:
            t = _ln(el.tag)
            if ev == "start":
                tags.append(t)
                els.append(el)
                if t in ("Folder", "Document"):
                    folders.append("")
                continue
            tags.pop()
            els.pop()
            if t == "name" and tags and tags[-1] in ("Folder", "Document") and folders:
                folders[-1] = (el.text or "").strip()
            elif t in ("Folder", "Document"):
                folders.pop()
                el.clear()
            elif t == "Style" and "Placemark" not in tags:
                sid = el.get("id")
                lc = icon = None
                for x in el.iter():
                    lx = _ln(x.tag)
                    if lx == "LineStyle":
                        for y in x:
                            if _ln(y.tag) == "color":
                                lc = (y.text or "").strip()
                    elif lx == "href":
                        icon = (x.text or "").strip()
                if sid:
                    styles["#" + sid] = (lc, icon)
            elif t == "StyleMap":
                for pair in el:
                    kk = su = None
                    for y in pair:
                        if _ln(y.tag) == "key":
                            kk = (y.text or "").strip()
                        elif _ln(y.tag) == "styleUrl":
                            su = (y.text or "").strip()
                    if kk == "normal" and el.get("id"):
                        smap["#" + el.get("id")] = su
            elif t == "Placemark":
                k += 1
                if progres and k % 5000 == 0:
                    progres(k, src.n)
                rec = _placemark(el, folders, styles, smap, bbox)
                if els:
                    try:
                        els[-1].remove(el)
                    except ValueError:
                        el.clear()
                else:
                    el.clear()
                if rec is not None:
                    yield rec
    except ET.ParseError as e:
        raise BerkasDitolak("KML rusak: %s" % e)
    finally:
        src.close()


def _placemark(el, folders, styles, smap, bbox):
    name = desc = su = None
    inline = None
    balon = ""
    geoms, attrs = [], {}
    for x in el.iter():
        t = _ln(x.tag)
        if t in ("Point", "LineString", "LinearRing"):
            cs = []
            for y in x.iter():
                if _ln(y.tag) == "coordinates":
                    cs = _coords(y.text)
            if cs:
                geoms.append(("Point" if t == "Point" else "LineString", cs))
        elif t == "SimpleData":
            attrs[x.get("name") or ""] = (x.text or "").strip()
        elif t == "Data":
            v = next((y for y in x if _ln(y.tag) == "value"), None)
            attrs[x.get("name") or ""] = ((v.text if v is not None else "") or "").strip()
        elif t == "LineStyle":
            for y in x:
                if _ln(y.tag) == "color":
                    inline = (y.text or "").strip()
        elif t == "BalloonStyle":
            for y in x:
                if _ln(y.tag) == "text":
                    balon = (y.text or "").strip()
    for x in el:
        t = _ln(x.tag)
        if t == "name":
            name = (x.text or "").strip()
        elif t == "description":
            desc = (x.text or "").strip()
        elif t == "styleUrl":
            su = (x.text or "").strip()
    if not geoms:
        return None
    if bbox is not None:
        ok = False
        for _g, cs in geoms:
            xs = [c[0] for c in cs]
            ys = [c[1] for c in cs]
            if max(xs) >= bbox[0] and min(xs) <= bbox[2] and max(ys) >= bbox[1] and min(ys) <= bbox[3]:
                ok = True
                break
        if not ok:
            return None
    st = styles.get(smap.get(su, su) if su else None, (None, None))
    if desc or balon:
        attrs = atribut.lengkapi(attrs, desc, balon)
    return {"path": [f for f in folders if f], "name": name or "", "desc": desc or "", "geoms": geoms,
            "attrs": attrs, "style": su or "", "warna": inline or st[0], "ikon": st[1]}
