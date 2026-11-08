# -*- coding: utf-8 -*-
# Tembuku - teks dua bahasa untuk pesan ke pengguna.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Satu pesan, dua bahasa. Nilai string-nya bahasa Indonesia (dipakai laporan HTML, KMZ, CSV dan berkas pemeriksaan
input); atribut .en bahasa Inggris (dipakai antarmuka QGIS: panel, pemeriksaan input di jendela, legenda).
Karena turunan str, kode lama yang memperlakukan pesan sebagai teks biasa tetap berjalan, dan json.dumps menulis
versi Indonesia. Pedoman penulisan (bahasa awam, ISO 24495-1:2023 Plain language): keputusan atau tindakan di
depan, kalimat pendek, satuan selalu ditulis, tanpa kode internal atau nama kolom basis data."""


def en(x):
    """Versi Inggris dari sebuah pesan (teks biasa dikembalikan apa adanya)."""
    return getattr(x, "en", x)


def _en_arg(a):
    if isinstance(a, tuple):
        return tuple(en(x) for x in a)
    if isinstance(a, dict):
        return {k: en(v) for k, v in a.items()}
    return en(a)


class T(str):
    """Pesan dua bahasa. T("Kabel %d m", "Cable %d m") % 5 -> T("Kabel 5 m", "Cable 5 m")."""

    def __new__(cls, id_, en_=None):
        o = str.__new__(cls, id_)
        o.en = str(id_) if en_ is None else str(en_)
        return o

    def __mod__(self, args):
        return T(str.__mod__(str(self), args), self.en % _en_arg(args))

    def __add__(self, other):
        return T(str(self) + str(other), self.en + en(other))

    def __radd__(self, other):
        return T(str(other) + str(self), en(other) + self.en)

    def __reduce__(self):
        return (T, (str(self), self.en))

    def __deepcopy__(self, memo):
        return self

    def __copy__(self):
        return self


def gabung(pemisah, daftar):
    """Seperti pemisah.join(daftar) tetapi mempertahankan versi Inggris."""
    daftar = list(daftar)
    return T(pemisah.join(str(x) for x in daftar), pemisah.join(en(x) for x in daftar))


def angka(x, desimal=0):
    """Angka gaya Indonesia (1.234,5) untuk teks Indonesia."""
    s = ("{:,.%df}" % desimal).format(x)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def angka_en(x, desimal=0):
    return ("{:,.%df}" % desimal).format(x)


def m(x):
    """Panjang dalam meter, dua bahasa: '1.234 m' / '1,234 m'."""
    return T("%s m" % angka(round(x)), "%s m" % angka_en(round(x)))


def km(x_m):
    """Panjang dari meter ke km (satu desimal), dua bahasa."""
    return T("%s km" % angka(x_m / 1000.0, 1), "%s km" % angka_en(x_m / 1000.0, 1))


def kali(x):
    """Kelipatan, dua bahasa: '1,2x' / '1.2x'."""
    return T("%s×" % angka(x, 1 if x >= 10 else 2), "%s×" % angka_en(x, 1 if x >= 10 else 2))


def db(x):
    return T("%s dB" % angka(x, 1), "%s dB" % angka_en(x, 1))
