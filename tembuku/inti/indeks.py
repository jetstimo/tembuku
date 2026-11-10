# -*- coding: utf-8 -*-
# Tembuku - area index of the national cable inventory.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later with the section 7 terms (see LICENSE).
"""The national cable KMZ (0.6-0.8 GB of KML per file) is NOT parsed in full. Only the areas being designed are
indexed, and they are added on demand:

  1. The KML is streamed once per needed area. The first coordinate of every line is read with one regular expression
     pass over each 16 MB block (C speed); nothing else is parsed for cables outside the work area.
  2. Only <Placemark> blocks whose first coordinate lies within the work cells plus one more ring (0.5 degree cells:
     at least 110 km around every FDT, compile and POP; the analysis radius is at most 15 km) are parsed as XML and
     stored in SQLite with an R*Tree (both in the Python standard library).
  3. Indexed cells are recorded, so a later run in the same area reads nothing; a new city adds only its own cells.

Measured on the October W4 2026 files: area index for North Sulawesi in seconds instead of 70-150 s for the whole
country, and the Java file is skipped entirely when no work area touches it.
Data minimisation (Indonesian PDP Law 27/2022, art. 16): only geometry and decision attributes are stored
(NAME, MODEL, Owner, PRODUCT, STATUS, NUM_SPARE_, NAMOBJ), in the user's QGIS profile folder."""
import hashlib
import os
import re
import sqlite3
import struct
import time
import xml.etree.ElementTree as ET  # nosec B405 - parses single <Placemark> fragments; DOCTYPE checked in kml_aman

from . import atribut, baca, kabel, kml_aman

SKEMA = 7                   # 7: atribut dikenali dari makna (sinonim kolom, tabel keterangan); format non-KML
POTONG = 64                 # points per stored line chunk (R*Tree granularity)
SKALA = 1e7                 # coordinates stored as integers of 1e-7 degree (~1 cm)
SEL = 0.5                   # area cell size (degrees)
BLOK_MAKS = 64 * 1024 * 1024
_RX_KOORD = re.compile(rb"<coordinates>\s*(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


def sidik_berkas(path):
    """Fast file fingerprint: size + modification time + SHA-256 of the first and last 4 MB."""
    h = hashlib.sha256()
    st = os.stat(path)
    h.update(("%d|%d|" % (st.st_size, int(st.st_mtime))).encode())
    with open(path, "rb") as fh:
        h.update(fh.read(4 << 20))
        if st.st_size > (8 << 20):
            fh.seek(-(4 << 20), 2)
            h.update(fh.read())
    return h.hexdigest()


def sel_dari_titik(points, tetangga=1):
    """Area cells (0.5 degree) around (lon, lat) points, including `tetangga` rings of neighbouring cells."""
    out = set()
    for x, y in points:
        cx, cy = int((x + 180.0) // SEL), int((y + 90.0) // SEL)
        for dx in range(-tetangga, tetangga + 1):
            for dy in range(-tetangga, tetangga + 1):
                out.add((cx + dx, cy + dy))
    return out


def _sel(x, y):
    return (int((x + 180.0) // SEL), int((y + 90.0) // SEL))


def _pack(cs):
    return struct.pack("<%di" % (2 * len(cs)), *[int(round(v * SKALA)) for c in cs for v in c])


def _unpack(b):
    v = struct.unpack("<%di" % (len(b) // 4), b)
    return [(v[i] / SKALA, v[i + 1] / SKALA) for i in range(0, len(v), 2)]


def _ln(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


class IndeksKabel(object):
    def __init__(self, db, sumber=None):
        self.db = db
        self.sumber = sumber
        self.con = sqlite3.connect(db, check_same_thread=False)
        self.con.executescript(
            "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"
            "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"
            "CREATE TABLE IF NOT EXISTS atr(id INTEGER PRIMARY KEY, nama TEXT, model TEXT, owner TEXT, product TEXT,"
            " status TEXT, spare REAL, core INTEGER, cpt INTEGER, kota TEXT, grup TEXT);"
            "CREATE TABLE IF NOT EXISTS kabel(id INTEGER PRIMARY KEY, atr INTEGER, geom BLOB);"
            "CREATE TABLE IF NOT EXISTS sel(cx INTEGER, cy INTEGER, PRIMARY KEY(cx, cy));"
            "CREATE VIRTUAL TABLE IF NOT EXISTS idx USING rtree(id, x0, x1, y0, y1);")

    def close(self):
        self.con.close()

    @staticmethod
    def path_cache(folder_cache, sumber, sidik):
        base = os.path.splitext(os.path.basename(sumber))[0]
        safe = "".join(ch if ch.isalnum() else "_" for ch in base)[:60]
        return os.path.join(folder_cache, "%s_%s_v%d.sqlite" % (safe, sidik[:16], SKEMA))

    @classmethod
    def buka(cls, sumber, folder_cache):
        os.makedirs(folder_cache, exist_ok=True)
        sid = sidik_berkas(sumber)
        db = cls.path_cache(folder_cache, sumber, sid)
        try:
            ix = cls(db, sumber)
            ix.con.execute("SELECT count(*) FROM sel").fetchone()
        except sqlite3.DatabaseError:
            try:
                ix.close()
            except Exception:       # broken cache file: rebuilt below
                ix = None
            os.remove(db)
            ix = cls(db, sumber)
        ix._set_meta({"sumber": os.path.basename(sumber), "sidik": sid})
        return ix

    @classmethod
    def siapkan(cls, sumber, folder_cache, sel_perlu=None, progres=None, batal=None):
        """Open (and extend if needed) the index of `sumber` for the needed area cells.
        sel_perlu=None indexes the whole file (used by tests and by very large work areas)."""
        ix = cls.buka(sumber, folder_cache)
        ix.pastikan(sel_perlu, progres, batal)
        return ix

    def _set_meta(self, d):
        self.con.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [(k, str(v)) for k, v in d.items()])
        self.con.commit()

    def meta(self, k):
        r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def ringkasan(self):
        return {k: v for k, v in self.con.execute("SELECT k, v FROM meta")}

    def sel_ada(self):
        return {(a, b) for a, b in self.con.execute("SELECT cx, cy FROM sel")}

    def pastikan(self, sel_perlu=None, progres=None, batal=None):
        """Index the cells in `sel_perlu` that are not indexed yet. Returns the number of cables added."""
        semua = sel_perlu is None
        if semua and self.meta("lengkap") == "1":
            return 0
        baru = None if semua else set(sel_perlu) - self.sel_ada()
        if not semua and not baru:
            return 0
        ekstent = self.meta("ekstent")
        if baru and ekstent:
            x0, y0, x1, y1 = map(float, ekstent.split(","))
            luar = {c for c in baru if not (_sel(x0, y0)[0] - 1 <= c[0] <= _sel(x1, y1)[0] + 1 and
                                            _sel(x0, y0)[1] - 1 <= c[1] <= _sel(x1, y1)[1] + 1)}
            if luar:                       # cells outside the file's extent: nothing to read there
                self.con.executemany("INSERT OR IGNORE INTO sel VALUES (?,?)", list(luar))
                self.con.commit()
                baru -= luar
            if not baru:
                return 0
        isi = self.meta("sel_isi")
        if baru and isi is not None:
            # berkas ini sudah pernah dibaca penuh: sel yang (bersama tetangganya) tidak berisi kabel apa pun langsung
            # ditandai selesai tanpa membaca ulang berkas besar itu
            ada = set(tuple(int(v) for v in t.split(":")) for t in isi.split(";") if t)
            kosong = {c for c in baru if not any((c[0] + dx, c[1] + dy) in ada for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
            if kosong:
                self.con.executemany("INSERT OR IGNORE INTO sel VALUES (?,?)", list(kosong))
                self.con.commit()
                baru -= kosong
            if not baru:
                return 0
        return self._baca(baru, progres, batal)

    def _baca(self, baru, progres, batal):
        if baca.jenis(self.sumber) not in ("KML", "KMZ"):
            return self._baca_umum(baru, progres, batal)
        nama = os.path.basename(self.sumber)
        size = max(1, os.path.getsize(self.sumber))
        src = kml_aman.buka(self.sumber)          # zip/XML safety checks (DOCTYPE, zip bomb, zip slip)
        t0 = time.time()
        idk = self.con.execute("SELECT coalesce(max(id),0) FROM kabel").fetchone()[0]
        ida = self.con.execute("SELECT coalesce(max(id),0) FROM atr").fetchone()[0]
        rows, rt, ar = [], [], []
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        n_pm = n_ambil = 0
        sisa = b""
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        # koordinat pertama tiap garis diuji terhadap sel kerja + 1 cincin lagi (>= 110 km dari titik kerja): kabel yang
        # melintasi area kerja tetapi berawal lebih jauh dari itu praktis tidak ada (radius analisis maks. 15 km)
        lebar = None if baru is None else {(cx + dx, cy + dy) for cx, cy in baru for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        isi = set()                      # semua sel yang berisi kabel di berkas ini (untuk melewati area kosong nanti)
        try:
            while True:
                if batal and batal():
                    raise KeyboardInterrupt("cancelled")
                blok = src.read(16 << 20)
                buf = sisa + blok
                akhir = len(buf) if not blok else buf.rfind(b"</Placemark>")
                if akhir < 0:
                    if len(buf) > BLOK_MAKS:
                        raise kml_aman.BerkasDitolak("one Placemark is larger than %d MB" % (BLOK_MAKS >> 20))
                    sisa = buf
                    continue
                if blok:
                    akhir += len(b"</Placemark>")
                kerja, sisa = buf[:akhir], buf[akhir:]
                # pemindaian C: koordinat pertama & terakhir setiap <coordinates>; Python hanya untuk yang di area
                posisi = []
                for rx in (_RX_KOORD,):
                    for m in rx.finditer(kerja):
                        x, y = float(m.group(1)), float(m.group(2))
                        if x < x0:
                            x0 = x
                        if x > x1:
                            x1 = x
                        if y < y0:
                            y0 = y
                        if y > y1:
                            y1 = y
                        sel_xy = _sel(x, y)
                        isi.add(sel_xy)
                        if lebar is None or sel_xy in lebar:
                            posisi.append(m.start())
                n_pm += kerja.count(b"</Placemark>")
                sudah = set()
                for p in sorted(posisi):
                    a = kerja.rfind(b"<Placemark", 0, p)
                    if a < 0 or a in sudah:
                        continue
                    sudah.add(a)
                    b = kerja.find(b"</Placemark>", p)
                    if b < 0:
                        continue
                    rec = self._parse(kerja[a:b + len(b"</Placemark>")])
                    if rec is None:
                        continue
                    n_ambil += 1
                    ida += 1
                    ar.append((ida,) + rec[0])
                    for cs in rec[1]:
                        for i in range(0, len(cs) - 1, POTONG - 1):
                            part = cs[i:i + POTONG]
                            if len(part) < 2:
                                continue
                            idk += 1
                            xs = [c[0] for c in part]
                            ys = [c[1] for c in part]
                            rows.append((idk, ida, _pack(part)))
                            rt.append((idk, min(xs), max(xs), min(ys), max(ys)))
                if len(rows) >= 20000:
                    self._simpan(ar, rows, rt)
                    ar, rows, rt = [], [], []
                if progres:
                    progres("Reading %s: %d cables checked, %d in the work area" % (nama, n_pm, n_ambil),
                            min(99, int(100.0 * src.n / (size * 11))))
                if not blok:
                    break
        finally:
            src.close()
        self._simpan(ar, rows, rt)
        if baru is None:
            self._set_meta({"lengkap": "1"})
        else:
            self.con.executemany("INSERT OR IGNORE INTO sel VALUES (?,?)", list(baru))
        if n_pm and x0 < 1e9:
            self._set_meta({"ekstent": "%.4f,%.4f,%.4f,%.4f" % (x0, y0, x1, y1), "placemark": n_pm,
                            "sel_isi": ";".join("%d:%d" % c for c in sorted(isi))})
        self._set_meta({"detik_terakhir": "%.1f" % (time.time() - t0)})
        self.con.commit()
        return n_ambil

    def _baca_umum(self, baru, progres, batal):
        """Inventaris dalam format selain KML/KMZ (GeoJSON, Shapefile, GeoPackage, ...): dibaca objek per objek."""
        t0 = time.time()
        idk = self.con.execute("SELECT coalesce(max(id),0) FROM kabel").fetchone()[0]
        ida = self.con.execute("SELECT coalesce(max(id),0) FROM atr").fetchone()[0]
        lebar = None if baru is None else {(cx + dx, cy + dy) for cx, cy in baru for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        rows, rt, ar = [], [], []
        x0 = y0 = 1e9
        x1 = y1 = -1e9
        n_pm = n_ambil = 0
        for pm in baca.placemarks(self.sumber):
            if batal and batal():
                raise KeyboardInterrupt("cancelled")
            lines = [cs for g, cs in pm["geoms"] if g == "LineString" and len(cs) >= 2]
            if not lines:
                continue
            n_pm += 1
            x, y = lines[0][0]
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            if lebar is not None and _sel(x, y) not in lebar:
                continue
            n_ambil += 1
            ida += 1
            ar.append((ida,) + self._rekam(pm["attrs"], pm["name"]))
            for cs in lines:
                for i in range(0, len(cs) - 1, POTONG - 1):
                    part = cs[i:i + POTONG]
                    if len(part) < 2:
                        continue
                    idk += 1
                    rows.append((idk, ida, _pack(part)))
                    rt.append((idk, min(c[0] for c in part), max(c[0] for c in part), min(c[1] for c in part),
                               max(c[1] for c in part)))
            if len(rows) >= 20000:
                self._simpan(ar, rows, rt)
                ar, rows, rt = [], [], []
        self._simpan(ar, rows, rt)
        if baru is None:
            self._set_meta({"lengkap": "1"})
        else:
            self.con.executemany("INSERT OR IGNORE INTO sel VALUES (?,?)", list(baru))
        if n_pm and x0 < 1e9:
            self._set_meta({"ekstent": "%.4f,%.4f,%.4f,%.4f" % (x0, y0, x1, y1), "placemark": n_pm})
        self._set_meta({"detik_terakhir": "%.1f" % (time.time() - t0)})
        self.con.commit()
        if progres:
            progres("Reading %s: %d cables, %d in the work area" % (os.path.basename(self.sumber), n_pm, n_ambil), 100)
        return n_ambil

    def _simpan(self, ar, rows, rt):
        if ar:
            self.con.executemany("INSERT INTO atr VALUES (?,?,?,?,?,?,?,?,?,?,?)", ar)
        if rows:
            self.con.executemany("INSERT INTO kabel VALUES (?,?,?)", rows)
            self.con.executemany("INSERT INTO idx VALUES (?,?,?,?,?)", rt)

    @staticmethod
    def _parse(frag):
        """One <Placemark> fragment -> ((attributes...), [line coordinates]) or None."""
        try:
            el = ET.fromstring(frag)  # nosec B314 - single fragment without DTD (prolog checked by kml_aman.buka)
        except ET.ParseError:
            return None
        a, lines, nama, desc, balon = {}, [], "", "", ""
        for x in el.iter():
            t = _ln(x.tag)
            if t == "description":
                desc = (x.text or "").strip()
            elif t == "BalloonStyle":
                balon = "".join((y.text or "") for y in x if _ln(y.tag) == "text")
            elif t == "SimpleData":
                a[x.get("name") or ""] = (x.text or "").strip()
            elif t == "Data":
                v = next((y for y in x if _ln(y.tag) == "value"), None)
                a[x.get("name") or ""] = ((v.text if v is not None else "") or "").strip()
            elif t == "LineString":
                for y in x:
                    if _ln(y.tag) == "coordinates":
                        cs = kml_aman._coords(y.text)
                        if len(cs) >= 2:
                            lines.append(cs)
            elif t == "name" and not nama:
                nama = (x.text or "").strip()
        if not lines:
            return None
        if desc or balon:
            a = atribut.lengkapi(a, desc, balon)
        return IndeksKabel._rekam(a, nama), lines

    @staticmethod
    def _rekam(a, nama):
        """Atribut keputusan dari kolom apa pun namanya (lihat atribut.SINONIM): nama, model, pemilik, produk, status,
        core cadangan, ukuran core, grup."""
        nm = atribut.nilai(a, "nama") or nama
        model = atribut.nilai(a, "model") or ""
        core, cpt = kabel.kapasitas_model(model, nm)
        if core is None:
            c2 = atribut.core_dari(a, nm)
            if c2:
                core, cpt = c2, 12 if c2 >= 12 else c2
        return (nm, model, atribut.nilai(a, "owner") or "", atribut.nilai(a, "produk") or "",
                atribut.nilai(a, "status") or "", atribut.spare_dari(a), core, cpt, atribut.nilai(a, "grup") or "", "")

    def di_bbox(self, bb):
        """bb=(minlon,minlat,maxlon,maxlat) -> list of cable dicts (consecutive chunks of one cable re-joined)."""
        q = ("SELECT a.id, a.nama, a.model, a.owner, a.product, a.status, a.spare, a.core, a.cpt, a.kota, a.grup, "
             "k.geom, k.id FROM idx i JOIN kabel k ON k.id = i.id JOIN atr a ON a.id = k.atr "
             "WHERE i.x1 >= ? AND i.x0 <= ? AND i.y1 >= ? AND i.y0 <= ? ORDER BY k.id")
        per = {}
        for r in self.con.execute(q, (bb[0], bb[2], bb[1], bb[3])):
            ll = _unpack(r[11])
            d = per.get(r[0])
            if d is not None and d["_akhir"] == r[12] - 1 and d["ll"][-1] == ll[0]:
                d["ll"].extend(ll[1:])
                d["_akhir"] = r[12]
                continue
            key = r[0] if d is None else "%s_%d" % (r[0], r[12])
            per[key] = {"id": "B%s" % key, "nama": r[1] or "", "model": r[2] or "", "owner": r[3] or "",
                        "product": r[4] or "", "status": r[5] or "", "spare": r[6], "core": r[7], "cpt": r[8],
                        "kota": r[9] or "", "grup": r[10] or "", "ll": ll, "sumber": "NASIONAL", "_akhir": r[12]}
        out = list(per.values())
        for d in out:
            d.pop("_akhir", None)
        return out
