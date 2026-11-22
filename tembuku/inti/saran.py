# -*- coding: utf-8 -*-
# Tembuku - Saran Tembuku (penasihat desain). Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later
# dengan syarat pasal 7 (lihat LICENSE).
"""Penasihat desain: sesudah keputusan sesuai aturan dibuat, SEMUA alternatif dinilai ulang dengan aturan yang lebih
longgar, lalu Tembuku menyarankan alternatif yang jelas lebih baik. Keputusan sesuai aturan tidak diubah: desainer
memilih sendiri (pop-up di QGIS, kotak saran di laporan).

Prinsip (agar dapat diandalkan):
  * tertutup dan stabil: tanpa internet atau model bahasa; masukan yang sama selalu memberi saran yang sama;
  * terukur: memakai model biaya atasan sendiri (colo cable 1, colo pole 20, new infra 100 per meter) dan redaman
    sinyal; setiap saran membawa angka pembanding dan alasan dalam bahasa awam;
  * batas keras tidak pernah dilonggarkan: tube harus kosong, sinyal di bawah batas kelas GPON, closure tidak penuh,
    kabel baru tidak terlalu panjang atau berbelok, kabel 48 core tidak lebih dari batas jarak (arahan 4 km);
  * yang boleh dilonggarkan hanya aturan lunak: koridor feeder sendiri, utara/selatan, arah feeder, jalur memutar;
  * ambang saran dikalibrasi pada desain yang sudah disetujui (lihat DASAR_KEPUTUSAN.md bagian 0a)."""
from . import geo
from .teks import T, gabung, m, km

# alasan tolak -> kode. Yang tidak dikenali dianggap KERAS (aman).
_POLA = (("tidak ada tube kosong", "TUBE", True), ("sudah penuh", "TUBE", True),
         ("sinyal terlalu lemah", "SINYAL", True), ("closure existing", "CLOSURE", True),
         ("terlalu berbelok", "BELOK", True), ("kabel barunya terlalu panjang", "PANJANG", True),
         ("untuk kabel 48 core", "JARAK48", True),
         ("hampir tidak melewati jalur tiang", "KORIDOR", False), ("menjauhi FDT", "ARAH", False),
         ("FDT ada di", "UTARA_SELATAN", False), ("jalurnya memutar", "MEMUTAR", False))
NAMA_ATURAN = {"KORIDOR": T("aturan cabang harus lewat jalur tiang feeder itu sendiri",
                            "the rule that a branch follows the feeder's own pole line"),
               "ARAH": T("aturan arah feeder ke FDT (paling jauh 60°)", "the rule on feeder direction (60° at most)"),
               "UTARA_SELATAN": T("aturan utara/selatan POP", "the north/south-of-the-POP rule"),
               "MEMUTAR": T("aturan jalur tidak boleh terlalu memutar", "the rule against long detours")}
AMBANG_HEMAT = 0.20       # saran hemat: biaya relatif paling sedikit 20 % lebih murah (dikalibrasi, lihat dokumen)
AMBANG_AMAN_DB = 1.0      # saran aman: margin cadangan utuh dengan sisa >= 1 dB ...
AMBANG_AMAN_BIAYA = 1.10  # ... dan biaya paling banyak 10 % lebih mahal


def kode_tolak(k):
    """-> (kode lunak, ada_keras) dari daftar alasan tolak kandidat."""
    lunak, keras = [], False
    for g in k.get("gagal") or []:
        s = str(g)
        hit = next(((kd, kr) for pola, kd, kr in _POLA if pola in s), None)
        if hit is None or hit[1]:
            keras = True
        elif hit[0] not in lunak:
            lunak.append(hit[0])
    return lunak, keras


def biaya_feeder_baru(fb, prm):
    """Biaya relatif feeder baru dengan model yang sama dengan kandidat: ruas di tiang existing x biaya_colo_pole,
    sisanya (termasuk garis bantu dengan faktor panjang nyatanya) x biaya_new_infra."""
    if not fb:
        return None
    tiang = sum(geo.panjang(s[2]) for s in fb.get("segmen") or [] if s[0] in ("TIANG_NASIONAL", "TIANG_COMPILE"))
    lain = max(0.0, float(fb.get("panjang_est_m") or fb.get("panjang_m") or 0.0) - tiang)
    return tiang * float(prm.get("biaya_colo_pole", 20.0)) + lain * float(prm.get("biaya_new_infra", 100.0))


def _layak(k):
    """Alternatif yang boleh disarankan: tube ada, tidak ada alasan tolak keras."""
    if k.get("kapasitas") not in ("LOLOS",):
        return None
    lunak, keras = kode_tolak(k)
    if keras or "KORIDOR" in lunak:
        # kalibrasi 1.6.0 (253 desain disetujui): saran yang melonggarkan aturan koridor 0 dari 2 cocok dengan desainer,
        # jadi aturan koridor tidak dilonggarkan oleh penasihat
        return None
    return lunak


def nilai(h, semua, prm):
    """Isi h['saran'] (atau None). semua = seluruh kandidat (sebelum dipangkas 12). -> kandidat yang disarankan/None."""
    h["saran"] = None
    if h.get("keputusan") not in ("COLO", "COLO_CEK", "FEEDER_BARU"):
        return None
    sel = h.get("terpilih")
    if h["keputusan"] == "FEEDER_BARU":
        b0 = biaya_feeder_baru(h.get("feeder_baru"), prm)
        m0 = None
        nama0 = T("feeder baru dari POP", "a new feeder from the POP")
    else:
        b0 = sel.get("biaya_relatif") if sel else None
        m0 = (sel.get("budget") or {}).get("margin_db") if sel else None
        nama0 = sel.get("nama") or sel.get("id")
    if not b0:
        return None
    terbaik = None
    for k in semua:
        if k is sel or (sel and k.get("fisik") == sel.get("fisik") and k.get("tap_simpul") == sel.get("tap_simpul")):
            continue
        lunak = _layak(k)
        if lunak is None:
            continue
        if sel and k.get("feeder_int") == sel.get("feeder_int") and k.get("pop_folder") == sel.get("pop_folder") \
                and not lunak:
            continue        # feeder yang sama dan lolos semua aturan: sudah dipertimbangkan oleh urutan biasa
        mg = (k.get("budget") or {}).get("margin_db")
        if mg is None or (mg < 0 and (m0 is None or mg < m0)):
            continue        # tidak boleh lebih buruk sinyalnya bila cadangan sudah tidak utuh
        b = k.get("biaya_relatif")
        if not b:
            continue
        hemat = 1.0 - b / b0
        jenis = None
        if hemat >= AMBANG_HEMAT:
            jenis = "HEMAT"
        elif m0 is not None and m0 < 0 and mg >= AMBANG_AMAN_DB and b <= b0 * AMBANG_AMAN_BIAYA:
            jenis = "AMAN"
        if jenis and (terbaik is None or (jenis, -b) > (terbaik[0], -terbaik[2])):
            terbaik = (jenis, k, b, hemat, lunak, mg)
    if terbaik is None:
        return None
    jenis, k, b, hemat, lunak, mg = terbaik
    inf = k.get("kap_info") or {}
    akibat = []
    if len(inf.get("bebas") or []) == 1 + int(prm.get("cadangan_tube", 0)):
        akibat.append(T("ini tube kosong terakhir di jalur %s feeder tersebut, jadi FDT berikutnya di sana perlu feeder "
                        "baru", "this is the last free tube on that feeder's %s path, so the next FDT there will need a "
                        "new feeder") % (inf.get("kelompok") or ""))
    if k.get("memutar"):
        akibat.append(T("jalurnya lebih panjang daripada feeder baru langsung dari POP", "its route is longer than a new "
                        "feeder straight from the POP"))
    yakin = "tinggi" if (jenis == "HEMAT" and hemat >= 0.35 and not akibat) else "sedang"
    if jenis == "HEMAT":
        ringkas = T("Lebih hemat %d%% kalau memakai %s (tube T%s) daripada %s.",
                    "%d%% cheaper with %s (tube T%s) instead of %s.") % (
            round(100 * hemat), k.get("nama") or k.get("id"), inf.get("tube") or "-", nama0)
    else:
        ringkas = T("Sinyal lebih aman kalau memakai %s (tube T%s): sisa redaman %s dB dengan biaya hampir sama.",
                    "A safer signal with %s (tube T%s): %s dB to spare for almost the same cost.") % (
            k.get("nama") or k.get("id"), inf.get("tube") or "-", ("%.1f" % mg).replace(".", ","))
    h["saran"] = {
        "jenis": jenis, "yakin": yakin, "ringkas": ringkas,
        "kandidat": k, "biaya_aturan": round(b0), "biaya_saran": round(b), "hemat_pct": round(100 * hemat),
        "margin_aturan": m0, "margin_saran": mg,
        "kabel_baru_aturan": (sel or {}).get("kabel_baru_m") if sel else round((h.get("feeder_baru") or {}).get("panjang_m") or 0),
        "kabel_baru_saran": k.get("kabel_baru_m"), "colo_saran": k.get("colo_m"),
        "dilonggarkan": [NAMA_ATURAN.get(x, x) for x in lunak], "kode_dilonggarkan": lunak, "akibat": akibat,
        "dipakai": False,
        "alasan": T("Desain sesuai aturan memakai %s dengan biaya relatif %s. Pilihan ini biayanya %s: kabel baru %s, "
                    "numpang feeder %s, sisa redaman %s dB.%s",
                    "The rule-based design uses %s at a relative cost of %s. This option costs %s: new cable %s, riding "
                    "the feeder %s, %s dB to spare.%s") % (
            nama0, "{:,}".format(round(b0)).replace(",", "."), "{:,}".format(round(b)).replace(",", "."),
            m(k.get("kabel_baru_m") or 0), m(k.get("colo_m") or 0), ("%.1f" % mg).replace(".", ","),
            (T(" Pilihan ini tidak memenuhi %s, tapi tidak melanggar batas teknis apa pun.",
               " It does not meet %s, but it breaks no technical limit.") % gabung("; ", [
                NAMA_ATURAN.get(x, x) for x in lunak])) if lunak else T(
                " Pilihan ini memenuhi semua aturan; desain sesuai aturan memilih yang lain karena urutan prioritas "
                "(jalur yang tidak memutar dan titik sambung di slack atau closure didahulukan), bukan karena biaya.",
                " This option meets every rule; the rule-based design chose the other one because of the priority order "
                "(routes without a detour and taps at a slack or closure come first), not because of cost."))}
    return k


def ringkasan_teks(h):
    s = h.get("saran")
    return str(s["ringkas"]) if s else ""


__all__ = ["nilai", "kode_tolak", "biaya_feeder_baru", "km"]
