# -*- coding: utf-8 -*-
# Tembuku - pengenal atribut berdasarkan makna (bukan nama kolom persis).
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Setiap operator, vendor dan aplikasi menamai kolom secara berbeda: 'NUM_SPARE_', 'SPARE CORE', 'Sisa Core',
'core_kosong' semuanya berarti core cadangan. Modul ini memetakan nama kolom ke MAKNA-nya:

  * nama kolom dinormalkan (huruf besar, hanya huruf dan angka): 'Spare Core' = 'SPARE_CORE' = 'sparecore';
  * dicocokkan dengan daftar sinonim per makna (Indonesia dan Inggris, istilah umum industri FTTH);
  * atribut dibaca dari ExtendedData KML, dan juga dari tabel di keterangan (description) dan balon (BalloonStyle),
    tempat banyak aplikasi GIS (ArcGIS, QGIS, Google Earth) menyimpan atribut saat ekspor ke KMZ.

Istilah padanan antar-operator yang dikenali: FDT = ODC (Optical Distribution Cabinet); FAT = ODP; POP = STO / CO
(Central Office) / lokasi OLT."""
import html
import re

# makna -> sinonim (bentuk normal: huruf besar, tanpa spasi/tanda baca). Urutan = prioritas.
SINONIM = {
    "nama": ["NAME", "NAMA", "CABLENAME", "NAMAKABEL", "CABLEID", "IDKABEL", "LABEL", "KODE", "CODE", "NAMOBJ2"],
    "model": ["MODEL", "CABLETYPE", "TYPEKABEL", "TIPEKABEL", "JENISKABEL", "SPEC", "SPESIFIKASI", "CABLEMODEL",
              "TYPE", "TIPE", "JENIS"],
    "core": ["CORE", "CORES", "JUMLAHCORE", "JMLCORE", "NUMCORE", "NUMCORES", "COREJUMLAH", "FIBERCOUNT",
             "FIBRECOUNT", "NUMFIBER", "NUMFIBRE", "FIBERS", "FIBRES", "COUNTFIBER", "CORECOUNT", "TOTALCORE",
             "KAPASITAS", "KAPASITASCORE", "CAPACITY", "CABLESIZE", "UKURANKABEL", "UKURAN", "SIZE", "JUMLAHSERAT"],
    "spare": ["NUMSPARE", "SPARE", "SPARECORE", "SPARECORES", "CORESPARE", "SISACORE", "CORESISA", "SISA",
              "FREECORE", "FREECORES", "COREFREE", "IDLECORE", "COREIDLE", "AVAILABLECORE", "COREAVAILABLE",
              "AVAILABLE", "COREKOSONG", "KOSONG", "CORETERSEDIA", "TERSEDIA", "CADANGAN", "CORECADANGAN"],
    "terpakai": ["USED", "COREUSED", "USEDCORE", "TERPAKAI", "CORETERPAKAI", "OCCUPIED", "COREOCCUPIED", "UTILIZED"],
    "owner": ["OWNER", "PEMILIK", "OPERATOR", "ASSETOWNER", "PEMILIKASET", "MITRA", "VENDOR", "PROVIDER"],
    "produk": ["PRODUCT", "PRODUK", "PRODUCTTYPE", "LAYANAN", "SERVICE", "SERVICETYPE", "PERUNTUKAN", "SEGMEN",
               "SEGMENT", "NETWORKTYPE", "JENISJARINGAN"],
    "status": ["STATUS", "KONDISI", "STATE", "LIFECYCLE", "STATUSKABEL", "OPERATIONALSTATUS"],
    "grup": ["NAMOBJ", "GROUP", "GRUP", "PROJECT", "PROYEK", "PROJECTNAME", "AREA", "WILAYAH", "REGION"],
    "splitter": ["SPLITTERS", "SPLITTER", "SPLIT", "SPL", "RASIOSPLITTER", "SPLITTERRATIO", "PASSIVESPLITTER",
                 "KONFIGURASISPLITTER"],
    "premises": ["PREMISES", "HOMEPASS", "HOMEPASSED", "HP", "JUMLAHHP", "JMLHP", "TOTALHP", "HOMES", "RUMAH",
                 "PELANGGAN", "CUSTOMER", "CUSTOMERS", "SUBSCRIBERS", "PORT"],
    "kode_fdt": ["FDTFATCODE", "FDTCODE", "KODEFDT", "FDTID", "IDFDT", "FDTNAME", "NAMAFDT", "FDT", "ODCCODE",
                 "KODEODC", "ODCID", "ODCNAME", "NAMAODC", "ODC"],
    "lat": ["LAT", "LATITUDE", "LINTANG"],
    "lon": ["LONG", "LON", "LNG", "LONGITUDE", "BUJUR"],
    "pop": ["SITEID", "SITE", "OLT", "OLTNAME", "NAMAOLT", "OLTID", "HOSTNAME", "STO", "NAMASTO", "KODESTO",
            "POP", "POPNAME", "NAMAPOP", "POPID", "NENAME", "CENTRALOFFICE", "CO"],
}
_PRIO = {k: {s: i for i, s in enumerate(v)} for k, v in SINONIM.items()}


def norm(k):
    return re.sub(r"[^A-Z0-9]", "", str(k or "").upper())


def cari(attrs, makna):
    """-> (nilai, nama_kolom_asli) untuk makna tertentu, atau (None, None). Nilai kosong/'-' dilewati."""
    pr = _PRIO[makna]
    calon = []
    for k, v in (attrs or {}).items():
        n = norm(k)
        if n in pr and str(v).strip() not in ("", "-", "--", "N/A", "NA", "NULL", "None"):
            calon.append((pr[n], k, v))
    if not calon:
        return None, None
    _p, k, v = min(calon)
    return v, k


def nilai(attrs, makna, default=None):
    return cari(attrs, makna)[0] if cari(attrs, makna)[0] is not None else default


def ada(attrs, makna):
    return cari(attrs, makna)[0] is not None


_TAG = re.compile(r"<[^>]+>")
_BARIS_TABEL = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_SEL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
_KV = re.compile(r"^\s*([A-Za-z][\w .()/-]{0,40}?)\s*[:=]\s*(.+?)\s*$")


def _bersih(s):
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def dari_teks(teks):
    """Atribut dari teks keterangan/balon: tabel HTML 2 kolom (<td>kunci</td><td>nilai</td>) atau baris 'kunci: nilai'.
    Placeholder balon Google Earth ($[nama]) diabaikan."""
    out = {}
    if not teks or len(teks) > 200000:
        return out
    if "<t" in teks.lower():
        for baris in _BARIS_TABEL.findall(teks):
            sel = [_bersih(x) for x in _SEL.findall(baris)]
            if len(sel) == 2 and sel[0] and len(sel[0]) <= 50 and not sel[1].startswith("$["):
                out.setdefault(sel[0], sel[1])
    else:
        for baris in re.split(r"<br\s*/?>|\n", teks, flags=re.I):
            m = _KV.match(_bersih(baris))
            if m and not m.group(2).startswith("$["):
                out.setdefault(m.group(1).strip(), m.group(2).strip())
    return out


def lengkapi(attrs, *teks):
    """Tambahkan atribut dari teks keterangan/balon tanpa menimpa atribut ExtendedData yang sudah ada."""
    hasil = dict(attrs or {})
    ada_norm = {norm(k) for k in hasil}
    for t in teks:
        for k, v in dari_teks(t).items():
            if norm(k) not in ada_norm:
                hasil[k] = v
                ada_norm.add(norm(k))
    return hasil


# ---------------------------------------------------------------------------- tanda isi (untuk pengenal peran)
UKURAN_CORE = (12, 24, 48, 72, 96, 144, 192, 288, 576)
RX_CORE_TEKS = re.compile(r"(?<![\d.])(12|24|48|72|96|144|192|288|576)\s*(?:C|CORE|CORES|F|FO|D)\b", re.I)
RX_MODEL_CT = re.compile(r"(\d{1,3})\s*/\s*(\d{1,2})\b")


def angka(v):
    try:
        x = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def core_dari(attrs, *teks):
    """Ukuran kabel (core) dari atribut bermakna 'core', model 'n/t', atau teks seperti '96C' / '96 core'."""
    v = angka(nilai(attrs, "core"))
    if v and int(v) in UKURAN_CORE:
        return int(v)
    m = RX_MODEL_CT.search(str(nilai(attrs, "model") or ""))
    if m and int(m.group(1)) in UKURAN_CORE:
        return int(m.group(1))
    for t in (str(nilai(attrs, "model") or ""),) + tuple(teks):
        m = RX_CORE_TEKS.search(t or "")
        if m:
            return int(m.group(1))
    return None


def spare_dari(attrs):
    """Core cadangan: kolom bermakna 'spare', atau core - terpakai bila keduanya ada. None bila tidak tercatat."""
    v = angka(nilai(attrs, "spare"))
    if v is not None and v >= 0:
        return v
    c, u = angka(nilai(attrs, "core")), angka(nilai(attrs, "terpakai"))
    if c is not None and u is not None and 0 <= u <= c:
        return c - u
    return None


RX_KATA_FDT = re.compile(r"(^|[^A-Z])(FDT|ODC)([^A-Z]|$)")
RX_KATA_POP = re.compile(r"(^|[^A-Z])(POP|OLT|STO|CENTRAL OFFICE)([^A-Z]|$)")
RX_KATA_AKSESORI = re.compile(r"(^|[^A-Z])(FAT|ODP|CLOSURE|SLACK|OTB|ODF|HANGER|TIANG|POLE|HH|MH|HANDHOLE|MANHOLE|"
                              r"JOINT|JC|SPLICE)([^A-Z]|$)")
