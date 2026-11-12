# -*- coding: utf-8 -*-
# Tembuku - geometri dasar. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Jarak & proyeksi lokal. Untuk jangkauan analisis < 30 km, proyeksi ekuirektangular lokal berpusat di FDT memberi
galat jarak << 0,1 % (cukup untuk desain; jarak akhir dilaporkan dengan haversine, radius bumi IUGG 6.371.008,8 m)."""
import math

R = 6371008.8


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, h)))


class Lokal(object):
    """Proyeksi lokal (meter) di sekitar titik pusat lon0, lat0."""

    def __init__(self, lon0, lat0):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = math.radians(1) * R * math.cos(math.radians(lat0))
        self.ky = math.radians(1) * R

    def ke(self, p):
        return ((p[0] - self.lon0) * self.kx, (p[1] - self.lat0) * self.ky)

    def balik(self, q):
        return (self.lon0 + q[0] / self.kx, self.lat0 + q[1] / self.ky)

    def bbox_deg(self, meter):
        return (self.lon0 - meter / self.kx, self.lat0 - meter / self.ky, self.lon0 + meter / self.kx,
                self.lat0 + meter / self.ky)


def panjang(xy):
    return sum(math.hypot(xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1]) for i in range(len(xy) - 1))


def panjang_deg(ll):
    return sum(haversine(ll[i], ll[i + 1]) for i in range(len(ll) - 1))


def proyeksi_segmen(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), t, q


def terdekat_di_garis(p, xy):
    """-> (jarak, indeks_segmen, t, titik, jarak_sepanjang_garis)."""
    best, acc = None, 0.0
    for i in range(len(xy) - 1):
        d, t, q = proyeksi_segmen(p, xy[i], xy[i + 1])
        sl = math.hypot(xy[i + 1][0] - xy[i][0], xy[i + 1][1] - xy[i][1])
        if best is None or d < best[0]:
            best = (d, i, t, q, acc + t * sl)
        acc += sl
    return best


def dekat_garis(p, xy, tol):
    """True bila p berjarak <= tol dari polyline xy (sama dengan terdekat_di_garis(p, xy)[0] <= tol, tetapi berhenti
    di segmen pertama yang cukup dekat dan melewati segmen yang kotaknya jauh)."""
    px, py, t2 = p[0], p[1], tol * tol
    for i in range(len(xy) - 1):
        a, b = xy[i], xy[i + 1]
        if (px < a[0] - tol and px < b[0] - tol) or (px > a[0] + tol and px > b[0] + tol) or \
                (py < a[1] - tol and py < b[1] - tol) or (py > a[1] + tol and py > b[1] + tol):
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / l2))
        ex, ey = px - (a[0] + t * dx), py - (a[1] + t * dy)
        if ex * ex + ey * ey <= t2:
            return True
    return False


def satuan(a, b):
    v = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / n, v[1] / n)


def rapatkan(xy, step):
    """Sisipkan titik agar tidak ada segmen > step meter (tap dapat di tengah bentang)."""
    if len(xy) < 2:
        return list(xy)
    out = [xy[0]]
    for i in range(len(xy) - 1):
        a, b = xy[i], xy[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


def titik_di(xy, ch):
    """Titik pada polyline (meter) di jarak ch dari awal (dijepit ke ujung)."""
    if not xy:
        return None
    acc = 0.0
    for a, b in zip(xy, xy[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > 0 and acc + d >= ch:
            t = max(0.0, (ch - acc) / d)
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        acc += d
    return xy[-1]


def potong_segmen(a, b, c, d):
    """Perpotongan segmen ab dan cd -> (t pada ab, sinus sudut) atau None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    lr, ls = math.hypot(*r), math.hypot(*s)
    if lr == 0 or ls == 0 or abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, abs(den) / (lr * ls)
    return None


def potong(ll, meter):
    """Potong polyline (lon,lat) pada jarak 'meter' dari awal -> (bagian_awal, sisa). Titik potong diinterpolasi."""
    if len(ll) < 2:
        return list(ll), []
    acc = 0.0
    for i in range(len(ll) - 1):
        d = haversine(ll[i], ll[i + 1])
        if acc + d >= meter and d > 0:
            t = (meter - acc) / d
            q = (ll[i][0] + (ll[i + 1][0] - ll[i][0]) * t, ll[i][1] + (ll[i + 1][1] - ll[i][1]) * t)
            return ll[:i + 1] + [q], [q] + ll[i + 1:]
        acc += d
    return list(ll), []
