# -*- coding: utf-8 -*-
# Tembuku - graf jaringan & Dijkstra. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later.
"""Graf tak berarah dalam meter (proyeksi lokal). Simpul berimpit (< 0,3 m) digabung. Dijkstra memakai heapq
(Dijkstra 1959); biaya = panjang x faktor jenis tepi. Grid hash 30 m untuk pencarian tetangga terdekat."""
import heapq
import math

from . import geo

INF = float("inf")


class Graf(object):
    def __init__(self, sel=30.0):
        self.xy, self.adj, self.refs = [], [], []
        self._kunci, self._grid, self.sel = {}, {}, sel

    def simpul(self, p, ref=None):
        k = (round(p[0] / 0.3), round(p[1] / 0.3))
        i = self._kunci.get(k)
        if i is None:
            i = len(self.xy)
            self._kunci[k] = i
            self.xy.append(p)
            self.adj.append([])
            self.refs.append(set())
            self._grid.setdefault((int(p[0] // self.sel), int(p[1] // self.sel)), []).append(i)
        if ref is not None:
            self.refs[i].add(ref)
        return i

    def tepi(self, a, b, jenis, ref, faktor):
        if a == b:
            return
        L = math.hypot(self.xy[a][0] - self.xy[b][0], self.xy[a][1] - self.xy[b][1])
        self.adj[a].append((b, L, L * faktor, jenis, ref))
        self.adj[b].append((a, L, L * faktor, jenis, ref))

    def garis(self, xy, jenis, ref, faktor, rapat=None):
        pts = geo.rapatkan(xy, rapat) if rapat else xy
        ids = [self.simpul(p, ref if jenis == "KABEL" else None) for p in pts]
        for a, b in zip(ids, ids[1:]):
            self.tepi(a, b, jenis, ref, faktor)
        return ids

    def dekat(self, p, r, saring=None):
        px, py = p[0], p[1]
        cx, cy, n = int(px // self.sel), int(py // self.sel), int(math.ceil(r / self.sel))
        out = []
        xy, grid, r2 = self.xy, self._grid, r * r
        for gx in range(cx - n, cx + n + 1):
            for gy in range(cy - n, cy + n + 1):
                sel = grid.get((gx, gy))
                if not sel:
                    continue
                for i in sel:
                    q = xy[i]
                    dx, dy = q[0] - px, q[1] - py
                    if dx * dx + dy * dy <= r2 and (saring is None or saring(i)):   # cek jarak dulu, saring belakangan
                        out.append((math.hypot(dx, dy), i))
        out.sort()
        return out

    def dijkstra(self, src, jenis_boleh=None, maks=INF):
        dist = [INF] * len(self.xy)
        prev = [None] * len(self.xy)
        dist[src] = 0.0
        h = [(0.0, src)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist[u] or d > maks:
                continue
            for v, _L, c, jenis, ref in self.adj[u]:
                if jenis_boleh is not None and jenis not in jenis_boleh:
                    continue
                nd = d + c
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = (u, jenis, ref)
                    heapq.heappush(h, (nd, v))
        return dist, prev

    def jalur(self, prev, tujuan):
        """-> daftar (simpul, jenis_tepi_masuk, ref) dari sumber ke tujuan."""
        out = []
        cur = tujuan
        while cur is not None:
            p = prev[cur]
            out.append((cur, p[1] if p else None, p[2] if p else None))
            cur = p[0] if p else None
        out.reverse()
        return out
