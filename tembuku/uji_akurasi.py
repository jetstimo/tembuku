# -*- coding: utf-8 -*-
# Tembuku - uji akurasi terhadap desain riil di Compile APD Feeder.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Setiap traksi di compile menjadi soal ujian: traksi itu, traksi sesudahnya di feeder yang sama, dan feeder bernomor
lebih besar di POP yang sama DISEMBUNYIKAN (keadaan saat desainer mengerjakannya); FDT-nya dianalisis Tembuku lalu
dibandingkan dengan desain desainer:
  * keputusan COLO / FEEDER BARU (desainer: ada Collo Cable = colo);
  * folder F<n>_T<k> yang diusulkan;
  * titik tap: jarak tap Tembuku ke ujung Collo Cable desainer yang terdekat ke FDT;
  * panjang kabel baru (cabang 48C untuk colo, semua kabel baru untuk feeder baru);
  * kesesuaian jalur: persen panjang jalur Tembuku yang berada <= 20 m dari kabel baru desainer.
Ini uji leave-one-out (validasi silang) - bukan bukti untuk kota lain; ambang rasio jalur dikalibrasi pada data ini."""
import re
import statistics

from .inti import geo


def _n(x):
    m = re.findall(r"\d+", str(x or ""))
    return int(m[0]) if m else 0


def soal(compiles):
    """-> daftar target FDT bertanda '_uji' (kunci kecuali + kunci jawaban desainer)."""
    out = []
    for c in compiles:
        for key, t in c["traksi"].items():
            own = [f for f in t["fdt"] if not f["colo_saudara"]]
            if not own:
                continue
            inf = t.get("info") or {}
            fn, tn = _n(inf.get("feeder") or t["feeder"]), _n(inf.get("t"))
            kec = set()
            for k2, t2 in c["traksi"].items():
                if k2[1] != key[1]:
                    continue
                i2 = t2.get("info") or {}
                f2, n2 = _n(i2.get("feeder") or t2["feeder"]), _n(i2.get("t"))
                if (f2 == fn and n2 >= tn) or f2 > fn:
                    kec.add(k2[3])
            f = dict(own[-1])
            f["cluster"], f["area"] = inf.get("cluster"), inf.get("area")
            f["berkas"] = c["berkas"]
            baru = [k["ll"] for k in t["kabel"] if k["jenis"] == "NEW_CABLE"]
            colo = [k["ll"] for k in t["colo"]]
            tap = None
            if colo:
                ujung = [ll[0] for ll in colo] + [ll[-1] for ll in colo]
                tap = min(ujung, key=lambda e: geo.haversine(e, f["ll"]))
            # semua kabel baru traksi = jalur baru tap->FDT (colo: desainer sering memperpanjang 96C lalu 48C) atau
            # POP->FDT (feeder baru); stub 1 m hasil gambar tidak berarti
            pj = sum(geo.panjang_deg(k["ll"]) for k in t["kabel"] if k["jenis"] == "NEW_CABLE")
            f["_uji"] = {"kecuali": kec, "traksi": t["kode"], "keputusan": "COLO" if colo else "FEEDER_BARU",
                         "feeder": fn, "t": tn, "tap": tap, "baru_m": round(pj), "kabel_baru": baru, "colo": colo,
                         "berkas": c["berkas"]}
            out.append(f)
    return out


def nilai(h):
    """Bandingkan hasil Tembuku dengan kunci jawaban desainer."""
    g = h["fdt"]["_uji"]
    kep = "COLO" if h["keputusan"] in ("COLO", "COLO_CEK", "COLO_MANUAL") else h["keputusan"]
    sel = h.get("terpilih")
    L = geo.Lokal(*h["lokal"])
    rute = sel["rute"] if sel else (h["feeder_baru"] if h["keputusan"] == "FEEDER_BARU" else None)
    tap_err = None
    if sel and g["tap"] and g["baru_m"] > 20:
        tap_err = round(geo.haversine(L.balik(sel["rute"]["titik"][0]), g["tap"]))
    sesuai = None
    if rute and g["kabel_baru"]:
        ref = [[L.ke(p) for p in ll] for ll in g["kabel_baru"]]
        pts = geo.rapatkan(rute["titik"], 10.0)
        if pts:
            dekat = 0
            for p in pts:
                if any(geo.terdekat_di_garis(p, xy)[0] <= 20.0 for xy in ref if len(xy) >= 2):
                    dekat += 1
            sesuai = round(100.0 * dekat / len(pts))
    n = h["penomoran"]
    # Desainer membuat feeder baru, dan kini di inventaris ada kabel yang lewat tepat di FDT itu: hampir pasti feeder
    # desain itu sendiri yang SUDAH DIBANGUN. Perbedaan ini bukan kesalahan; desain seperti ini tidak bisa diuji adil.
    dibangun = bool(g["keputusan"] == "FEEDER_BARU" and kep == "COLO" and sel and sel.get("sumber") != "COMPILE"
                    and sel["kabel_baru_m"] <= 50.0)
    return {"sudah_dibangun": dibangun, "fdt": h["fdt"]["kode"], "traksi": g["traksi"], "berkas": g["berkas"], "desainer": g["keputusan"],
            "tembuku": h["keputusan"], "cocok": kep == g["keputusan"],
            "folder_desainer": "F%d_T%d" % (g["feeder"], g["t"]), "folder_tembuku": "F%d_T%d" % (n["feeder"], n["t"]),
            "folder_cocok": (n["feeder"], n["t"]) == (g["feeder"], g["t"]), "tap_meleset_m": tap_err,
            "baru_desainer_m": g["baru_m"], "baru_tembuku_m": round(sel["kabel_baru_m"]) if sel else (
                round(rute["panjang_m"]) if rute else None), "jalur_sesuai_pct": sesuai,
            "garis_bantu_m": round(rute["bantu_m"]) if rute else None, "batas": bool(h.get("batas")),
            "desain_ll": [[[p[1], p[0]] for p in ll] for ll in g["kabel_baru"]],
            "colo_ll": [[[p[1], p[0]] for p in ll] for ll in g["colo"]]}


def ringkasan(nilai_list):
    n = len(nilai_list)
    if not n:
        return {}
    taps = [x["tap_meleset_m"] for x in nilai_list if x["tap_meleset_m"] is not None]
    ses = [x["jalur_sesuai_pct"] for x in nilai_list if x["jalur_sesuai_pct"] is not None]
    return {"n": n, "keputusan_cocok": sum(x["cocok"] for x in nilai_list),
            "folder_cocok": sum(x["folder_cocok"] for x in nilai_list),
            "tap_median_m": round(statistics.median(taps)) if taps else None,
            "tap_dalam_100m": sum(1 for v in taps if v <= 100), "tap_n": len(taps),
            "jalur_median_pct": round(statistics.median(ses)) if ses else None, "jalur_n": len(ses)}
