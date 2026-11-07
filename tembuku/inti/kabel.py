# -*- coding: utf-8 -*-
# Tembuku - kapasitas kabel. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Membaca kapasitas kabel dari atribut kabel nasional dan nama folder/kabel compile.

Notasi 'core/tube' (24/2, 48/4, 96/8) mengikuti konstruksi loose-tube 12 core per tube (TIA-598-D, 12 warna per tube).
Tube bebas dihitung KONSERVATIF: floor(NUM_SPARE_ / core_per_tube) - sebagian tube yang terpakai tidak dihitung bebas.
NUM_SPARE_ kosong/bukan angka -> kapasitas TIDAK DIKETAHUI (bukan dianggap tersedia)."""
import re

_MODEL = re.compile(r"(\d{1,3})\s*/\s*(\d{1,2})\b")
_CORE = re.compile(r"(?<![\d.])(12|24|48|72|96|144|192|288|576)\s*(?:C|CORE|D|F)?\b", re.I)


def kapasitas_model(model, nama=""):
    """-> (core, core_per_tube) atau (None, None)."""
    m = _MODEL.search(model or "")
    if m:
        c, t = int(m.group(1)), int(m.group(2))
        if c > 0 and t > 0 and c % t == 0 and c <= 864:
            return c, c // t
    for s in (model or "", nama or ""):
        m = _CORE.search(s)
        if m:
            c = int(m.group(1))
            return c, 12 if c >= 12 else c
    return None, None


def angka(s):
    try:
        v = float(str(s).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return v if v == v and v >= 0 else None


def core_compile(folder, nama=""):
    """Core kabel compile dari folder 'New Cable 96C' atau nama '96C'/'96'."""
    for s in (folder or "", nama or ""):
        m = re.search(r"(\d{2,3})\s*C\b", s, re.I) or re.fullmatch(r"\s*(\d{2,3})\s*[cC]?\s*", s or "")
        if m and int(m.group(1)) in (12, 24, 48, 72, 96, 144, 192, 288, 576):
            return int(m.group(1))
    return None


_SPL = re.compile(r"(\d+)\s*[xX]\s*1\s*[xX:]\s*(\d+)")


def splitter(s):
    """'12x1x4' -> (12, 4)."""
    m = _SPL.search(s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)
