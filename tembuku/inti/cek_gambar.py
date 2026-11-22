# -*- coding: utf-8 -*-
# Tembuku - pemeriksaan gambar kabel masukan. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later
# dengan syarat pasal 7 (lihat LICENSE).
"""Deteksi gambar kabel yang salah bentuk di inventaris kabel dan compile desain feeder (1.6.0).

Kebijakan: PERINGATAN, bukan tolak. Kabel yang gambarnya salah tetap ada di lapangan dan tube-nya tetap nyata; menolaknya
berarti membangun feeder baru (new infra x100) padahal ada feeder dengan tube kosong. Yang berbahaya adalah panjangnya:
garis lurus lebih pendek dari jalur nyata, sehingga aturan 4 km dan redaman bisa terlalu optimistis - itu diperiksa per
FDT di mesin.rapikan_gambar_data (dampak terhadap keputusan).

Jenis temuan (ambang dari bentang tiang nyata 40-50 m):
  LOMPAT  satu ruas lurus >= 2 km: hampir pasti gambar rusak/salah titik;
  LURUS   satu ruas lurus >= 300 m yang tidak menempel jalan (dicek ke OpenStreetMap bila ada): memotong bangunan;
  BALIK   berbalik arah tajam (> 150 derajat) dengan kedua lengan >= 15 m: taji/V;
  PULANG  jalur pergi >= 60 m lalu kembali ke titik yang sama (< 8 m): garis dobel pergi-pulang."""
import math

AMBANG_LURUS_M = 300.0
AMBANG_LOMPAT_M = 2000.0
NAMA = {"LOMPAT": "garis lurus yang sangat panjang, kemungkinan ada titik yang salah letak",
        "LURUS": "garis lurus panjang yang tidak mengikuti jalan",
        "BALIK": "belokan tajam yang berbalik arah seperti huruf V",
        "PULANG": "garis yang pergi lalu kembali di jalur yang sama"}
NAMA_EN = {"LOMPAT": "a very long straight line, probably a misplaced point",
           "LURUS": "a long straight line that follows no road",
           "BALIK": "a sharp V-shaped turn back",
           "PULANG": "a line that goes out and comes back the same way"}


def _xy(ll):
    lat0 = ll[0][1]
    c = math.cos(math.radians(lat0))
    return [((p[0] - ll[0][0]) * 111320.0 * c, (p[1] - ll[0][1]) * 110574.0) for p in ll]


def _dp(P, tol):
    """Douglas-Peucker (iteratif) -> indeks titik yang dipertahankan."""
    if len(P) < 3:
        return list(range(len(P)))
    simpan = [False] * len(P)
    simpan[0] = simpan[-1] = True
    tumpuk = [(0, len(P) - 1)]
    while tumpuk:
        a, b = tumpuk.pop()
        ax, ay = P[a]
        bx, by = P[b]
        L = math.hypot(bx - ax, by - ay)
        jauh, ij = -1.0, None
        for i in range(a + 1, b):
            px, py = P[i]
            d = (abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / L) if L > 1e-9 else math.hypot(px - ax, py - ay)
            if d > jauh:
                jauh, ij = d, i
        if ij is not None and jauh > tol:
            simpan[ij] = True
            tumpuk += [(a, ij), (ij, b)]
    return [i for i, s in enumerate(simpan) if s]


def periksa(ll, dekat_jalan=None):
    """ll: [(lon, lat), ...]. dekat_jalan(lon, lat) -> bool (opsional). -> [{jenis, m, ll}] paling banyak satu per jenis
    (yang terparah)."""
    if not ll or len(ll) < 2:
        return []
    P = _xy(ll)
    idx = _dp(P, 3.0)
    S = [P[i] for i in idx]
    SL = [ll[i] for i in idx]
    out = {}

    def catat(jenis, m, titik):
        if jenis not in out or m > out[jenis]["m"]:
            out[jenis] = {"jenis": jenis, "m": round(m), "ll": (round(titik[0], 7), round(titik[1], 7))}

    for i in range(len(S) - 1):
        d = math.hypot(S[i + 1][0] - S[i][0], S[i + 1][1] - S[i][1])
        tengah = ((SL[i][0] + SL[i + 1][0]) / 2.0, (SL[i][1] + SL[i + 1][1]) / 2.0)
        if d >= AMBANG_LOMPAT_M:
            catat("LOMPAT", d, tengah)
        elif d >= AMBANG_LURUS_M:
            if dekat_jalan is not None:
                n = max(3, int(d // 30.0))
                kena = sum(1 for j in range(1, n) if dekat_jalan(SL[i][0] + (SL[i + 1][0] - SL[i][0]) * j / n,
                                                                SL[i][1] + (SL[i + 1][1] - SL[i][1]) * j / n))
                if kena >= 0.8 * (n - 1):
                    continue        # garis lurus di sepanjang jalan lurus: wajar
            catat("LURUS", d, tengah)
    for i in range(1, len(S) - 1):
        a = (S[i][0] - S[i - 1][0], S[i][1] - S[i - 1][1])
        b = (S[i + 1][0] - S[i][0], S[i + 1][1] - S[i][1])
        la, lb = math.hypot(*a), math.hypot(*b)
        if la < 15 or lb < 15:
            continue
        cosv = (a[0] * b[0] + a[1] * b[1]) / (la * lb)
        if cosv < math.cos(math.radians(150)):
            catat("BALIK", min(la, lb), SL[i])
    for i in range(len(S)):
        jauh = 0.0
        for j in range(i + 1, len(S)):
            d = math.hypot(S[j][0] - S[i][0], S[j][1] - S[i][1])
            jauh = max(jauh, d)
            if jauh >= 60 and d < 8:
                catat("PULANG", jauh, SL[i])
                break
        if "PULANG" in out:
            break
    return sorted(out.values(), key=lambda x: -x["m"])


class JalanDekat:
    """Uji cepat 'titik ini dekat jalan OSM' (grid ~15 m dari titik jalan yang dirapatkan 10 m)."""

    def __init__(self, jalan, r_m=15.0):
        self.s = 0.000135 * r_m / 15.0
        self.grid = set()
        for j in jalan or []:
            ll = j.get("ll") or []
            for a, b in zip(ll, ll[1:]):
                d = math.hypot((b[0] - a[0]) * 111320.0, (b[1] - a[1]) * 110574.0)
                n = max(1, int(d // 10.0))
                for k in range(n + 1):
                    x, y = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n
                    self.grid.add((int(math.floor(x / self.s)), int(math.floor(y / self.s))))

    def __call__(self, lon, lat):
        gx, gy = int(math.floor(lon / self.s)), int(math.floor(lat / self.s))
        return any((gx + i, gy + j) in self.grid for i in (-1, 0, 1) for j in (-1, 0, 1))

    def __bool__(self):
        return bool(self.grid)
