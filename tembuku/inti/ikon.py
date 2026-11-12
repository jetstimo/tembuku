"""Ikon titik orisinal Tembuku, digambar dengan kode lalu disematkan di dalam KMZ (files/*.png).

Tidak ada ikon pihak ketiga yang ditautkan, sehingga KMZ tetap tampil tanpa internet dan bebas dari
ketergantungan merek lain. Bentuk dasar berwarna putih dengan tepi gelap; warna akhir diatur IconStyle."""
import math
import struct
import zlib

UKURAN = 32


def _png(px, n=UKURAN):
    raw = b"".join(b"\x00" + bytes(px[y * n * 4:(y + 1) * n * 4]) for y in range(n))

    def blok(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + blok(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + blok(b"IDAT", zlib.compress(raw, 9)) + blok(b"IEND", b""))


def _bintang(x, y):
    a = math.atan2(y, x)
    r = math.hypot(x, y)
    t = ((a - math.pi / 2) * 5 / (2 * math.pi)) % 1.0
    k = abs(t - 0.5) * 2
    return (r - (0.42 + 0.56 * k)) * 0.6


# fungsi jarak bertanda: < 0 di dalam bentuk; koordinat dinormalkan -1..1
BENTUK = {
    "tap": _bintang,
    "fdt": lambda x, y: max(abs(x), abs(y)) - 0.78,
    "otb": lambda x, y: max(abs(x), abs(y)) - 0.62,
    "closure": lambda x, y: abs(math.hypot(x, y) - 0.6) - 0.22,
    "pop": lambda x, y: max(abs(x) + (y + 0.85) * 0.55 - 0.85, -y - 0.85, y - 0.8),
    "slack": lambda x, y: abs(x) + abs(y) - 0.85,
    "tiang": lambda x, y: math.hypot(x, y) - 0.62,
}


def gambar(nama, n=UKURAN):
    f = BENTUK[nama]
    px = []
    for j in range(n):
        for i in range(n):
            x = (i + 0.5) / n * 2 - 1
            y = 1 - (j + 0.5) / n * 2
            d = f(x, y)
            tepi = 2.0 / n
            if d < -tepi * 1.5:
                px += [255, 255, 255, 255]
            elif d < 0:
                px += [40, 40, 40, 255]
            elif d < tepi:
                px += [40, 40, 40, int(255 * (1 - d / tepi))]
            else:
                px += [0, 0, 0, 0]
    return _png(px, n)


def semua():
    return {"files/%s.png" % k: gambar(k) for k in BENTUK}
