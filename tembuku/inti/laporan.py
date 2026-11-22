# -*- coding: utf-8 -*-
# Tembuku - laporan HTML interaktif offline.
# Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later dengan syarat pasal 7 (lihat LICENSE).
"""Satu berkas HTML mandiri (Leaflet & font tertanam): ringkasan semua FDT, filter keputusan, peta per FDT (kandidat,
titik tap, jalur per jenis infrastruktur, garis bantu), alasan keputusan dalam bahasa awam, ekspor CSV.
Keamanan: semua data masuk sebagai JSON ter-escape (tidak ada HTML dari KMZ yang dirender), tanpa skrip eksternal."""
import base64
import datetime
import json
import os

from . import geo, mesin, osm, peta_dasar, validasi
from . import saran as _saran

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _aset(rel):
    p = os.path.join(HERE, "assets", rel)
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as fh:
        return fh.read()


def _json(o):
    # semua '<', '>' dan '&' dikodekan (\u003c ...) agar teks dari berkas KMZ tidak pernah bisa keluar dari blok <script>
    return (json.dumps(o, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def _ll(L, xy):
    return [[round(L.balik(p)[1], 7), round(L.balik(p)[0], 7)] for p in xy]


def ringkas(h):
    L = geo.Lokal(*h["lokal"])
    sel = h.get("terpilih")
    fb = h.get("feeder_baru")
    rute = sel["rute"] if sel else (fb if h["keputusan"] == "FEEDER_BARU" else None)
    seg = [{"k": s[0], "n": mesin.label_kelas(s[0]), "ll": _ll(L, s[2])} for s in rute["segmen"]] if rute else []
    kd = []
    s = h.get("saran")
    tampil = list(enumerate(h["kandidat"][:6]))
    if s:
        tampil += [(i, k) for i, k in enumerate(h["kandidat"]) if k is s["kandidat"] and i >= 6]
    for i, k in tampil:
        kd.append({"no": i + 1, "nama": k["nama"] or k["id"], "label": k["label_colo"], "sumber": k["sumber"],
                   "biaya": round(k["biaya_relatif"]) if k.get("biaya_relatif") else None, "pilih": k is sel,
                   "saran": bool(s and k is s["kandidat"]), "tube": (k.get("kap_info") or {}).get("tube"),
                   "model": k.get("model") or "", "kap": k["kapasitas"],
                   "ketkap": k["ket_kapasitas"], "baru": k["kabel_baru_m"], "colo": k["colo_m"], "cos": k["cos"],
                   "rasio": k.get("rasio_jalur"), "detour": k["detour"], "lolos": k["lolos"],
                   "gagal": k["gagal"], "catatan": k["catatan"], "db": k["budget"]["total_db"],
                   "vonis": str(mesin.vonis_kandidat(k)), "sudut": mesin.sudut_arah(k["cos"]), "searah": k.get("searah", True),
                   "margin": k["budget"]["margin_db"], "tap": _ll(L, [k["rute"]["titik"][0]])[0],
                   "kabel": [[round(p[1], 7), round(p[0], 7)] for p in k["ll_kabel"]],
                   "colo_ll": _ll(L, _cg[::max(1, len(_cg) // 300)]) if (_cg := k.get("colo_gambar_xy") or k.get("colo_xy"))
                   else []})
    f = h["fdt"]
    return {"kode": f["kode"], "ll": [f["ll"][1], f["ll"][0]], "kep": h["keputusan"], "batas": bool(h.get("batas")),
            "alasan": h["alasan"], "peringatan": h["peringatan"], "pop": h["pop"]["nama"] if h["pop"] else "-",
            "pop_ll": [h["pop"]["ll"][1], h["pop"]["ll"][0]] if h["pop"] else None, "jarak_pop": h["jarak_pop_m"],
            "seg": seg, "kandidat": kd, "fb": round(fb["panjang_m"]) if fb else None,
            "fb_est": round(fb["panjang_est_m"]) if fb else None,
            "baru": sel["kabel_baru_m"] if sel else (round(fb["panjang_m"]) if fb and h["keputusan"] == "FEEDER_BARU"
                                                    else None),
            "bantu": round(rute["bantu_m"]) if rute else 0, "jalan": h.get("ada_jalan", False),
            "nomor": h["penomoran"], "splitter": f.get("splitter"), "rasio": f.get("rasio") or 4, "premises": f.get("premises"),
            "berkas": f.get("berkas") or "", "nkabel": h.get("n_kabel_diperiksa", 0),
            # 1.6.0: dasbor keputusan, penjelasan lima bagian, Saran Tembuku
            "pj": [[t, list(isi)] for t, isi in (h.get("penjelasan") or [])],
            "saran": None if not s else {
                "ringkas": s["ringkas"], "alasan": s["alasan"], "jenis": s["jenis"], "yakin": s["yakin"],
                "hemat": s["hemat_pct"], "b0": s["biaya_aturan"], "b1": s["biaya_saran"], "m0": s["margin_aturan"],
                "m1": s["margin_saran"], "longgar": s["dilonggarkan"], "akibat": s["akibat"], "dipakai": s.get("dipakai"),
                "no": next((i + 1 for i, k in enumerate(h["kandidat"]) if k is s["kandidat"]), None),
                "nama": s["kandidat"].get("nama") or s["kandidat"].get("id"),
                "tube": (s["kandidat"].get("kap_info") or {}).get("tube")},
            "oleh": h.get("dipilih_desainer") or "", "penting": h.get("penting") or [],
            "janggal": bool(h.get("pakai_kabel_janggal")),
            "biaya": round(sel["biaya_relatif"]) if sel and sel.get("biaya_relatif") else (
                round(_saran.biaya_feeder_baru(fb, {}) or 0) if fb and h["keputusan"] == "FEEDER_BARU"
                else None),
            "biaya_fb": round(_saran.biaya_feeder_baru(fb, {}) or 0) if fb else None,
            "colo": sel.get("colo_m") if sel else None, "infra": round(sel.get("new_infra_m") or 0) if sel else None,
            "pole": round(sel.get("colo_pole_m") or 0) if sel else None,
            "core": (sel.get("core_cabang") if sel else (fb or {}).get("core")),
            "jalur": (sel.get("jalur_serat_m") if sel else round((fb or {}).get("panjang_est_m") or 0) or None),
            "db": (sel.get("budget") or {}).get("total_db") if sel else None,
            "margin": (sel.get("budget") or {}).get("margin_db") if sel else None,
            "rapi": (sel or (fb if h["keputusan"] == "FEEDER_BARU" else None) or {}).get("gambar_diperbaiki_m") or 0}


KAMUS = [
    ("FDT", "Fiber Distribution Terminal: kotak pembagi di area pelanggan yang perlu disambung ke POP."),
    ("POP", "Point of Presence: titik pusat jaringan (OLT) tempat feeder berawal."),
    ("Feeder", "Kabel utama dari POP menuju FDT."),
    ("Tube", "Selongsong berisi beberapa core di dalam kabel; satu FDT memakai satu tube utuh."),
    ("Core", "Satu helai serat optik di dalam tube."),
    ("Titik tap", "Titik pada feeder yang ada tempat kabel baru disambung (closure) menuju FDT."),
    ("Titik sambung (tap)", "Titik di feeder yang sudah ada tempat kabel baru disambung (dengan closure) menuju FDT."),
    ("Colo", "Menumpang kabel atau tiang yang sudah ada, bukan membangun baru."),
    ("Pakai feeder yang ada", "FDT disambung ke feeder yang sudah ada; cukup tarik kabel baru dari titik sambung ke FDT."),
    ("Pakai feeder yang ada - cek sisa tube", "Arah dan jaraknya cocok, tetapi sisa tube feeder tidak tercatat di data. "
     "Pastikan dulu masih ada tube kosong."),
    ("Feeder baru dari POP", "Tidak ada feeder yang cocok; tarik feeder baru langsung dari POP."),
    ("Perlu dirancang manual", "Data tidak cukup (misalnya POP terlalu jauh); desainer harus merancang sendiri."),
    ("Perlu ditinjau", "Memakai feeder yang ada dan membuat feeder baru hampir sama baiknya; periksa keduanya sebelum "
     "memutuskan."),
    ("Arah feeder", "Seberapa lurus feeder mengarah ke FDT dilihat dari POP. 0° = tepat searah; makin besar makin "
     "menjauh. Batas bawaan 60°."),
    ("Panjang jalur dibanding feeder baru", "(Panjang feeder yang dipakai dari POP ke titik sambung + kabel baru) dibagi "
     "panjang feeder baru langsung dari POP. 1,0x = sama panjang. Di atas batas (bawaan 1,24x) jalurnya dianggap "
     "terlalu memutar."),
    ("Redaman sinyal (link budget)", "Total pelemahan sinyal cahaya dari POP sampai pelanggan, dalam dB. Harus di bawah "
     "batas perangkat (28 dB untuk GPON kelas B+)."),
    ("Garis bantu", "Ruas lurus sementara karena tidak ada data jalan atau kabel di situ; wajib digambar ulang mengikuti "
     "tiang atau jalan."),
    ("New Infra", "Ruas yang butuh tiang atau jalur baru."),
    ("Slack", "Gulungan cadangan kabel untuk penyambungan di kemudian hari."),
    ("Closure", "Kotak sambungan kabel serat optik."),
    ("OTB", "Optical Termination Box: titik awal kabel di POP."),
    ("Compile desain feeder", "KMZ kumpulan desain feeder yang sedang dikerjakan, tersusun per POP, Feeder dan traksi."),
    ("Traksi (F/T)", "Satu ruas desain di compile: F = nomor feeder dari POP, T = nomor traksi di feeder itu."),
    ("Inventaris kabel", "KMZ seluruh kabel jaringan yang sudah terpasang, beserta jumlah core cadangannya."),
]


def _h(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def tulis(hasil, path, meta):
    meta = dict(meta or {})
    meta.setdefault("istilah", KAMUS)
    meta.setdefault("nama", {k: str(v) for k, v in mesin.NAMA_KEPUTUSAN.items()})
    meta.setdefault("tingkat", dict(validasi.NAMA_TINGKAT))
    meta.setdefault("atrib_jalan", osm.ATRIBUSI)
    meta.setdefault("esri_meta", peta_dasar.ESRI_META)
    meta.setdefault("umur_maks", peta_dasar.UMUR_PERINGATAN)
    data = [ringkas(h) for h in hasil]
    uji = (meta or {}).get("uji") or {}
    per = {(b["fdt"], b["traksi"]): b for b in uji.get("baris", [])}
    for d, h in zip(data, hasil):
        g = h["fdt"].get("_uji")
        if g:
            d["uji"] = per.get((h["fdt"]["kode"], g["traksi"]))
    css = _aset("map/leaflet.css").decode("utf-8") if _aset("map/leaflet.css") else ""
    js = _aset("map/leaflet.js").decode("utf-8") if _aset("map/leaflet.js") else ""
    fonts = ""
    for nm, w in (("inter-400", 400), ("inter-600", 600), ("poppins-700", 700)):
        b = _aset("fonts/%s.woff" % nm)
        if b:
            fam = "Poppins" if nm.startswith("poppins") else "Inter"
            fonts += "@font-face{font-family:%s;font-weight:%d;src:url(data:font/woff;base64,%s) format('woff')}" % (
                fam, w, base64.b64encode(b).decode())
    pjs = _aset("fonts/plus-jakarta-sans-latin-wght.woff2")
    if pjs:     # Plus Jakarta Sans (Tokotype, Jakarta) - SIL OFL 1.1, lihat assets/fonts/OFL-PlusJakartaSans.txt
        fonts += ("@font-face{font-family:'Plus Jakarta Sans';font-style:normal;font-weight:200 800;"
                  "src:url(data:font/woff2;base64,%s) format('woff2')}" % base64.b64encode(pjs).decode())
    logo = _aset("../icon.svg") or b""
    html = (TEMPLATE.replace("/*FONTS*/", fonts).replace("/*LEAFLETCSS*/", css).replace("/*LEAFLETJS*/", js)
            .replace("__DATA__", _json(data)).replace("__META__", _json(meta))
            .replace("__LOGO__", base64.b64encode(logo).decode()).replace("__ATRIB__", _h(osm.ATRIBUSI))
            .replace("__LBL_COMPILE__", _h(mesin.label_kelas(mesin.TIANG_COMPILE)))
            .replace("__LBL_NASIONAL__", _h(mesin.label_kelas(mesin.TIANG_NASIONAL))))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def tanggal():
    return datetime.datetime.now().strftime("%d-%m-%Y %H:%M")


TEMPLATE = r"""<!DOCTYPE html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tembuku - Laporan Feeder</title><style>/*FONTS*/
/*LEAFLETCSS*/
:root{--ink:#141a46;--mut:#5a6280;--line:#e4e2da;--bg:#f7f4ec;--teal:#0f766e;--amber:#b7791f;--red:#b4232c;
--blue:#2b3a8f;--nila:#141a46;--emas:#f5b83d;--sinar:#2dd4bf;
--sans:"Plus Jakarta Sans",Inter,system-ui,sans-serif;--display:"Plus Jakarta Sans",Poppins,Inter,sans-serif}
*{box-sizing:border-box}body{margin:0;font:14px/1.55 var(--sans);color:var(--ink);background:var(--bg)}
header{display:flex;gap:14px;align-items:center;padding:12px 22px;color:#fff;position:relative;overflow:hidden;
background:radial-gradient(circle at 92% 50%,#f5b83d33 0,#f5b83d00 28%),linear-gradient(120deg,#1c2463,#090c2b)}
header:after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;
background:linear-gradient(90deg,#2dd4bf,#22d3ee 45%,#f5b83d 70%,#b4232c)}
header img{width:44px;height:44px}header h1{font:800 20px var(--display);letter-spacing:.2px;margin:0}
header h1 span{color:var(--emas)}header small{opacity:.78}
/* kawung motif from Javanese batik, drawn very faintly behind the list */
aside{background-color:#fffdf8;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='40'%3E%3Cg fill='none' stroke='%23141a46' stroke-opacity='.05' stroke-width='1.2'%3E%3Cellipse cx='20' cy='9' rx='5' ry='8'/%3E%3Cellipse cx='20' cy='31' rx='5' ry='8'/%3E%3Cellipse cx='9' cy='20' rx='8' ry='5'/%3E%3Cellipse cx='31' cy='20' rx='8' ry='5'/%3E%3C/g%3E%3C/svg%3E")}
html,body{height:100%}body{display:flex;flex-direction:column;overflow:hidden}header{flex:none}
.wrap{display:grid;grid-template-columns:minmax(260px,380px) minmax(0,1fr);flex:1 1 auto;min-height:0;height:auto}
aside{overflow:auto;border-right:1px solid var(--line);min-height:0;min-width:0}
@media (max-width:820px){body{overflow:auto;height:auto}.wrap{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto}
aside{max-height:45vh;border-right:0;border-bottom:1px solid var(--line)}main{height:92vh}header{padding:10px 16px}
header h1{font-size:17px}.det{padding:12px 16px}table{display:block;overflow-x:auto}}
.lead{padding:14px 16px;border-bottom:1px solid var(--line);font-size:13px;color:var(--mut)}
.chips{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;cursor:pointer;font-size:12px;background:#fff}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.chip.kosong:not(.on){opacity:.5}
.it{padding:10px 16px;border-bottom:1px solid var(--line);cursor:pointer}.it:hover{background:#f3efe2}
.it.on{background:#fff6dd;box-shadow:inset 4px 0 0 var(--emas)}
.it b{font-family:var(--display);font-weight:800}.tag{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;color:#fff;margin-left:6px}
.COLO{background:var(--teal)}.COLO_CEK{background:var(--amber)}.COLO_MANUAL{background:#7c3aed}.FEEDER_BARU{background:var(--blue)}.PERLU_MANUAL{background:var(--red)}
.BATAS{background:#7c3aed}
.leaflet-container{background:#f1eee4;font-family:var(--sans)}
main{display:grid;grid-template-rows:minmax(0,56fr) minmax(0,44fr);min-width:0;min-height:0;overflow:hidden}
#peta{min-height:0;height:100%;width:100%}
.det{overflow:auto;padding:14px 20px;background:#fff;border-top:1px solid var(--line)}
.det h2{font:800 18px var(--display);margin:0 0 4px}.why{background:#eef7f5;border-left:4px solid var(--teal);padding:8px 12px;margin:8px 0;border-radius:4px}
.warn{background:#fff7e6;border-left:4px solid var(--amber);padding:6px 12px;margin:6px 0;border-radius:4px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:8px}th,td{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}tr.ok td:first-child{border-left:3px solid var(--teal)}tr.no{color:#777}
.kpi{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0}
.muted{color:var(--mut);font-size:12px}.kpi div{background:var(--bg);border-radius:8px;padding:6px 10px;font-size:12px}
.kpi b{display:block;font:800 16px var(--display)}
details{border-bottom:1px solid var(--line);padding:8px 16px;font-size:12.5px}summary{cursor:pointer;font-weight:600}
.t-FATAL{color:#b91c1c}.t-DIKOREKSI{color:#0e7c7b}.t-PERINGATAN{color:#b45309}.t-INFO{color:#5b6b78}
.infopeta{background:#fffffff2;padding:4px 9px;border-radius:6px;font-size:12px;box-shadow:0 1px 4px #0003;max-width:420px}
.infopeta.awas{background:#fff4e5;border-left:4px solid #c2410c;font-weight:600}
.leg{position:absolute;z-index:500;right:10px;bottom:22px;background:#fffffff2;padding:8px 10px;border-radius:8px;font-size:12px;box-shadow:0 1px 4px #0003}
.leg i{display:inline-block;width:22px;height:4px;margin-right:6px;vertical-align:middle}
button{font:600 12px Inter;border:1px solid var(--ink);background:#fff;border-radius:6px;padding:4px 10px;cursor:pointer}
footer{font-size:11px;color:var(--mut);padding:8px 16px}
.tabs{margin-left:auto;display:flex;gap:6px;position:relative;z-index:1}
.tabs button{background:#ffffff14;color:#fff;border-color:#ffffff55;font-size:13px;padding:6px 14px}
.tabs button.on{background:var(--emas);color:var(--ink);border-color:var(--emas)}
#dash{flex:1 1 auto;overflow:auto;padding:16px 22px 30px;min-height:0}
body.dash .wrap{display:none}body:not(.dash) #dash{display:none}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.card b{display:block;font:800 22px var(--display);line-height:1.2}.card small{color:var(--mut);font-size:11.5px}
.card.aksen{border-color:#7c3aed;background:#faf8ff}.card.awas{border-color:#e7b25a;background:#fffaf0}
.pnl{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-top:14px;min-width:0}
.pnl h3{font:800 15px var(--display);margin:0 0 2px}.pnl .muted{margin-bottom:8px}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}@media(max-width:1000px){.grid2{grid-template-columns:minmax(0,1fr)}}
.risk{display:flex;gap:10px;align-items:flex-start;padding:7px 4px;border-bottom:1px solid var(--line);cursor:pointer}.risk:hover{background:#f7f4ec}
.lvl{flex:none;width:11px;height:11px;border-radius:50%;margin-top:5px}
.barbox{background:#f1eee4;border-radius:4px;width:110px;height:9px;display:inline-block;vertical-align:middle;margin-right:6px;position:relative}
.barbox i{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.tb{display:inline-grid;grid-template-columns:repeat(12,24px);gap:2px}.tb span{height:21px;border-radius:3px;font-size:9.5px;text-align:center;line-height:21px;border:1px solid #d6d2c4}
.tb .lama{background:#cbd5e1;color:#475569}.tb .baru{background:var(--emas);border-color:#b7791f;font-weight:700}.tb .kosong{background:#fff;border-color:#5fb3a3;color:#0f766e}
.tb .g48{margin-left:0}.tb span:nth-child(9){margin-left:6px}
.sar{background:#f5f3ff;border-left:4px solid #7c3aed;padding:8px 12px;margin:8px 0;border-radius:4px}
.sar.pakai{background:#eefbf5;border-color:#0f766e}
.pj h4{margin:12px 0 4px;font:700 13.5px var(--display)}.pj ul{margin:0;padding-left:18px}.pj li{margin:2px 0}
.SARAN{background:#7c3aed}
th.urut{cursor:pointer}th.urut:hover{color:var(--ink)}
.cmp div{display:flex;align-items:center;gap:8px;font-size:12px;margin:3px 0}.cmp span.nm{width:210px;flex:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cmp .b{height:12px;border-radius:3px}
</style></head><body class="dash">
<header><img src="data:image/svg+xml;base64,__LOGO__" alt=""><div><h1>Tembuku <span>&middot;</span> Laporan Desain Feeder</h1>
<small id="sub"></small></div><div class="tabs"><button id="t-dash" class="on" onclick="tab(1)">Dasbor keputusan</button><button id="t-det" onclick="tab(0)">Detail per FDT</button></div></header>
<section id="dash"></section>
<div class="wrap"><aside><div class="lead" id="lead"></div><div id="uji"></div><div id="cek"></div><div class="chips" id="chips"></div><div id="list"></div>
<footer>__ATRIB__. Usulan otomatis &mdash; wajib ditinjau desainer sebelum dimasukkan ke compile desain feeder.
<br><button onclick="csv()">Unduh CSV ringkasan</button></footer></aside>
<main><div id="peta" style="position:relative"><div class="leg"><div><i style="background:#0e7c7b"></i>__LBL_COMPILE__</div>
<div><i style="background:#00b4d8"></i>__LBL_NASIONAL__</div><div><i style="background:#22c55e"></i>Tiang/jalur baru (New Infra)</div>
<div><i style="background:#b9b4a6"></i>Jalan (OpenStreetMap)</div>
<div><i style="background:#ef4444;height:2px;border-top:2px dashed #ef4444"></i>Garis bantu (gambar ulang)</div>
<div><i style="background:#f59e0b"></i>Feeder kandidat</div><div><i style="background:#a855f7"></i>Feeder yang dipakai (POP &rarr; titik sambung)</div></div></div>
<div class="det" id="det"></div></main></div>
<script>/*LEAFLETJS*/</script>
<script>
const D=__DATA__,M=__META__;const NAMA=M.nama||{};const TK=M.tingkat||{};
const idn=(x,d)=>x==null?"-":Number(x).toLocaleString("id-ID",{minimumFractionDigits:d||0,maximumFractionDigits:d||0});
const KAP={LOLOS:"Ada tube kosong",PENUH:"Penuh",BELUM_TERVERIFIKASI:"Belum pasti",BUKAN_FEEDER:"Bukan feeder"};
const W={TIANG_COMPILE:"#0e7c7b",TIANG_NASIONAL:"#00b4d8",NEW_INFRA:"#22c55e",GARIS_BANTU:"#ef4444"};
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let filt="ALL",cur=0;
document.getElementById("sub").textContent=`${D.length} FDT · ${M.waktu} · ${M.alat}`;
const n=k=>D.filter(d=>d.kep===k).length;
const nb=D.filter(d=>d.batas).length;
document.getElementById("lead").innerHTML=`<b>Ringkasan:</b> <b>${n("COLO")}</b> pakai feeder yang ada, <b>${n("COLO_CEK")}</b> pakai feeder yang ada tetapi sisa tube perlu dicek, <b>${n("FEEDER_BARU")}</b> feeder baru dari POP, <b>${n("PERLU_MANUAL")}</b> perlu dirancang manual`+
(nb?`, <b>${nb}</b> perlu ditinjau karena dua pilihannya hampir seimbang.`:".")+
`<br><b>Langkah Anda:</b> klik tiap FDT di daftar, baca alasannya, lalu cek jalurnya di peta. Dahulukan yang bertanda <i>perlu ditinjau</i>, <i>cek sisa tube</i> atau <i>perlu dirancang manual</i>.`;
const chips=[["ALL","Semua"],["COLO","Pakai feeder"],["COLO_CEK","Cek sisa tube"],["FEEDER_BARU","Feeder baru"],["PERLU_MANUAL","Manual"],["BATAS","Perlu ditinjau"],["SARAN","Ada Saran Tembuku"]];
const cocok=(d,f)=>f=="ALL"||d.kep==f||(f=="BATAS"&&d.batas)||(f=="SARAN"&&!!d.saran);
function rChips(){document.getElementById("chips").innerHTML=chips.map(c=>{const j=D.filter(d=>cocok(d,c[0])).length;
return `<span class="chip ${filt==c[0]?"on":""}${j?"":" kosong"}" data-f="${c[0]}" title="${j} FDT">${c[1]} (${j})</span>`}).join("");
document.querySelectorAll(".chip").forEach(e=>e.onclick=()=>{filt=e.dataset.f;rChips();rList()})}
function rList(){const pilih=D.map((d,i)=>({d,i})).filter(o=>cocok(o.d,filt));
if(!pilih.length){const nm=(chips.find(c=>c[0]==filt)||["",""])[1];document.getElementById("list").innerHTML=
`<div style="padding:14px 16px;color:#5b6b78;font-size:13px">Tidak ada FDT dengan kategori <b>${esc(nm)}</b> di laporan ini. Pilih <b>Semua</b> untuk melihat semua FDT.</div>`;return}
document.getElementById("list").innerHTML=pilih.map(({d,i})=>
`<div class="it ${i==cur?"on":""}" data-i="${i}"><b>${esc(d.kode)}</b><span class="tag ${d.kep}">${NAMA[d.kep]}</span>${d.batas?'<span class="tag BATAS">perlu ditinjau</span>':""}${d.saran?`<span class="tag SARAN">${d.saran.dipakai?"saran dipakai":"ada saran"}</span>`:""}
<div style="font-size:12px;color:#5b6b78">${d.baru!=null?("kabel baru "+idn(d.baru)+" m · "):""}${esc(d.pop)} (${idn(d.jarak_pop)} m)</div></div>`).join("");
document.querySelectorAll(".it").forEach(e=>e.onclick=()=>show(+e.dataset.i))}
const map=L.map("peta",{preferCanvas:true,maxZoom:20});map.attributionControl.setPrefix("Leaflet");
/* Peta dasar: jalan OSM tertanam (tetap tampil tanpa internet). Satelit hanya bila pengguna memasukkannya dengan
   akun/kuncinya sendiri: Copernicus per kuartal (jendela waktu dihitung SAAT laporan dibuka, jadi selalu kuartal
   terbaru) dan Esri (tanggal pemotretan di tengah peta dibaca otomatis dari layanan metadata resmi Esri). */
const jalan=L.layerGroup((M.jalan||[]).map(l=>L.polyline(l,{color:"#b9b4a6",weight:2.5,interactive:false})));
const kosong=L.layerGroup();
function jendela(){const d=new Date();let y=d.getUTCFullYear(),m=d.getUTCMonth()+1-12;while(m<=0){y--;m+=12}
 const q=Math.floor((m-1)/3)*3+1;return y+"-"+String(q).padStart(2,"0")+"-01/"+d.toISOString().slice(0,10)}
const dasar={"Jalan OpenStreetMap (tersimpan, offline)":kosong};let esriL=null,cdseL=null;
for(const p of (M.peta_ekstra||[])){let u=String(p.url||"");if(!/^https:\/\//.test(u))continue;
 if(p.jenis==="cdse")u=u.replace(/TIME=[^&]*/,"TIME="+jendela());
 const t=L.tileLayer(u,{maxZoom:20,maxNativeZoom:p.zmax||19,attribution:esc(p.atrib)});dasar[p.nama]=t;
 if(p.jenis==="esri")esriL=t;if(p.jenis==="cdse")cdseL=t}
kosong.addTo(map);if((M.jalan||[]).length){jalan.addTo(map);map.attributionControl.addAttribution(esc(M.atrib_jalan))}
L.control.layers(dasar,{"Garis jalan OpenStreetMap":jalan},{position:"topleft",collapsed:true}).addTo(map);
const info=L.control({position:"bottomleft"});info.onAdd=()=>{const d=L.DomUtil.create("div","infopeta");d.id="infopeta";d.style.display="none";return d};info.addTo(map);
function setInfo(t,awas){const d=document.getElementById("infopeta");if(d){d.textContent=t;d.style.display=t?"block":"none";d.classList.toggle("awas",!!awas)}}
let tglKunci="",metaSvc="";const EM=M.esri_meta||"https://metadata.maptiles.arcgis.com/arcgis/rest/services/",UM=M.umur_maks||12;
async function tglEsri(){if(!esriL||!map.hasLayer(esriL)||!map._loaded)return;const c=map.getCenter(),k=c.lat.toFixed(3)+","+c.lng.toFixed(3);
 if(k===tglKunci)return;tglKunci=k;setInfo("Membaca tanggal pemotretan citra...");
 try{if(!metaSvc){const d=await fetch(EM+"?f=json").then(r=>r.json());
   const s=(d.services||[]).map(x=>String(x.name).match(/^World_Imagery_Metadata_(\d{4})_r(\d+)$/)).filter(Boolean)
    .sort((a,b)=>(+a[1]-+b[1])||(+a[2]-+b[2]));metaSvc=s.length?s[s.length-1][0]:""}
  if(!metaSvc){setInfo("Tanggal pemotretan citra tidak terbaca");return}
  const x=c.lng,y=c.lat,q=EM+metaSvc+"/MapServer/identify?geometry="+x+","+y+"&geometryType=esriGeometryPoint&sr=4326&layers=all&tolerance=0&mapExtent="+
   (x-.01)+","+(y-.01)+","+(x+.01)+","+(y+.01)+"&imageDisplay=400,400,96&returnGeometry=false&f=json";
  const j=await fetch(q).then(r=>r.json());const a=((j.results||[])[0]||{}).attributes||{};
  const m=String(a.SRC_DATE2||"").match(/^(\d+)\/(\d+)\/(\d{4})$/);if(!m){setInfo("Tanggal pemotretan di titik ini tidak tersedia");return}
  const b=+m[1],h=+m[2],t=+m[3],now=new Date(),um=Math.max(0,(now.getUTCFullYear()-t)*12+(now.getUTCMonth()+1-b)-(now.getUTCDate()<h?1:0));
  const tg=t+"-"+String(b).padStart(2,"0")+"-"+String(h).padStart(2,"0"),s="Citra detail di tengah peta dipotret "+tg+" ("+um+" bulan lalu)";
  setInfo(um>UM?s+": rumah/jalan yang dibangun sesudahnya TIDAK terlihat. Bandingkan dengan OSM, Copernicus, atau survei.":s,um>UM)
 }catch(e){tglKunci="";setInfo("Tanggal pemotretan butuh internet")}}
map.on("baselayerchange",e=>{setInfo("");if(e.layer===esriL){tglKunci="";tglEsri()}
 if(e.layer===cdseL)setInfo("Satelit bebas awan Copernicus: kuartal terbaru, bagian yang masih berawan diisi kuartal sebelumnya ("+jendela().replace("/"," s.d. ")+")")});
map.on("moveend",tglEsri);
let grp=L.featureGroup().addTo(map);
/* ukuran peta dibaca ulang sebelum zoom: tanpa ini peta yang dibuat saat tata letak belum selesai tampil terpotong
   (zoom terlalu jauh, kanvas bergeser). Juga dijalankan ulang tiap ukuran jendela/panel berubah. */
function pas(){map.invalidateSize(false);const b=grp.getLayers().length?grp.getBounds():null;
 if(b&&b.isValid())map.fitBounds(b.pad(.15),{maxZoom:18,animate:false});else if(D[cur])map.setView(D[cur].ll,16)}
let _pt=null;const _ulang=()=>{clearTimeout(_pt);_pt=setTimeout(pas,120)};
if(window.ResizeObserver)new ResizeObserver(_ulang).observe(document.getElementById("peta"));
window.addEventListener("resize",_ulang);window.addEventListener("load",()=>setTimeout(pas,50));
function show(i){cur=i;rList();const d=D[i];grp.clearLayers();
d.kandidat.forEach(k=>{L.polyline(k.kabel,{color:k.lolos?"#f59e0b":"#9ca3af",weight:k.lolos?4:2,opacity:.8}).bindTooltip(`#${k.no} ${esc(k.nama)} · ${esc(k.ketkap)}`).addTo(grp);
L.circleMarker(k.tap,{radius:5,color:"#111",fillColor:k.lolos?"#f59e0b":"#d1d5db",fillOpacity:1,weight:1}).bindTooltip("Titik sambung kandidat #"+k.no).addTo(grp)});
const sel=d.kandidat.find(k=>k.pilih)||d.kandidat.find(k=>k.lolos||d.kep=="COLO_CEK");if(sel&&sel.colo_ll.length&&d.kep!="FEEDER_BARU")L.polyline(sel.colo_ll,{color:"#a855f7",weight:5,opacity:.7}).bindTooltip("Feeder yang dipakai: POP → titik sambung").addTo(grp);
d.seg.forEach(s=>L.polyline(s.ll,{color:W[s.k]||"#22c55e",weight:6,dashArray:s.k=="GARIS_BANTU"?"8 8":null}).bindTooltip(esc(s.n)).addTo(grp));
if(d.uji){d.uji.desain_ll.forEach(l=>L.polyline(l,{color:"#111",weight:3,dashArray:"6 6"}).bindTooltip("Desain desainer (kabel baru)").addTo(grp));
d.uji.colo_ll.forEach(l=>L.polyline(l,{color:"#111",weight:2,opacity:.5,dashArray:"2 6"}).bindTooltip("Desain desainer (colo cable)").addTo(grp))}
L.circleMarker(d.ll,{radius:9,color:"#fff",weight:3,fillColor:"#c2410c",fillOpacity:1}).bindTooltip("FDT "+esc(d.kode),{permanent:true,direction:"top"}).addTo(grp);
if(d.pop_ll)L.circleMarker(d.pop_ll,{radius:8,color:"#fff",weight:3,fillColor:"#1d4ed8",fillOpacity:1}).bindTooltip("POP "+esc(d.pop)).addTo(grp);
pas();
const nm=d.nomor;document.getElementById("det").innerHTML=`<h2>${esc(d.kode)} <span class="tag ${d.kep}">${NAMA[d.kep]}</span></h2>
<div class="kpi"><div>Folder compile<b>F${nm.feeder}_T${nm.t}</b></div><div>Kabel baru<b>${d.baru!=null?idn(d.baru)+" m":"-"}</b></div><div>Jika feeder baru dari POP<b>${d.fb!=null?idn(d.fb)+" m":"-"}</b></div>
<div>Splitter<b>${d.splitter?d.splitter+"x1x"+d.rasio:"-"}</b></div><div>Kabel yang diperiksa<b>${d.nkabel}</b></div><div>Data jalan<b>${d.jalan?"ada":"tidak ada"}</b></div></div>
${d.uji?`<div class="why" style="border-color:${d.uji.cocok?"#0e7c7b":"#c2410c"}"><b>Uji akurasi: keputusan ${d.uji.cocok?"SAMA":"BERBEDA"}.</b> Desainer: ${esc(NAMA[d.uji.desainer]||d.uji.desainer)} (${esc(d.uji.folder_desainer)}). Tembuku: ${esc(NAMA[d.uji.tembuku]||d.uji.tembuku)} (${esc(d.uji.folder_tembuku)}).${d.uji.tap_meleset_m!=null?" Titik sambung berselisih "+idn(d.uji.tap_meleset_m)+" m.":""} Kabel baru Tembuku ${d.uji.baru_tembuku_m!=null?idn(d.uji.baru_tembuku_m)+" m":"-"}, desainer ${idn(d.uji.baru_desainer_m)} m.${d.uji.jalur_sesuai_pct!=null?" Jalurnya "+d.uji.jalur_sesuai_pct+"% sama.":""}</div>`:""}
${detPj(d)}
${d.bantu>0?`<div class="warn">${idn(d.bantu)} m jalur masih berupa garis bantu lurus (tidak ada data jalan atau kabel di bagian itu): gambar ulang mengikuti tiang atau jalan.</div>`:""}
${d.kandidat.length?"":`<div class="why" style="border-color:#5a6280">Tidak ada kabel feeder di sekitar FDT yang bisa dijadikan kandidat.</div>`}${!d.kandidat.length?"":`<div style="font-size:12px;color:#5b6b78;margin:8px 0 2px">Feeder yang sudah ada di sekitar FDT dan hasil pemeriksaannya:</div>
${cmp(d)}
<table><tr><th>#</th><th>Feeder</th><th>Sisa tube</th><th>Kabel baru ke FDT</th><th>Feeder dari POP ke titik sambung</th><th>Arah ke FDT</th><th title="Panjang jalur lewat feeder ini dibanding feeder baru dari POP">Panjang jalur vs feeder baru</th><th title="Model atasan: colo cable x1, colo pole x20, new infra x100 per meter">Biaya relatif</th><th>Redaman sinyal</th><th>Hasil</th></tr>
${d.kandidat.map(k=>`<tr class="${k.lolos?"ok":"no"}"${k.saran?' style="background:#f5f3ff"':""}><td>${k.no}</td><td><b>${esc(k.nama)}</b>${k.pilih?' <span class="tag COLO">dipakai</span>':""}${k.saran?' <span class="tag SARAN">Saran Tembuku</span>':""}<br>${esc(k.label)} ${esc(k.model)}</td><td>${esc(KAP[k.kap]||k.kap)}<br><small>${esc(k.ketkap)}</small></td>
<td>${idn(k.baru)} m<br><small>${idn(k.detour,1)}× jarak lurus</small></td><td>${k.colo!=null?idn(k.colo)+" m":"tidak terlihat tersambung"}</td><td>${k.sudut==null?"-":(k.searah?"searah":"menjauh")+" ("+k.sudut+"°)"}</td><td>${k.rasio==null?"-":idn(k.rasio,2)+"×"}</td><td>${k.biaya==null?"-":idn(k.biaya)}</td>
<td>${idn(k.db,1)} dB<br><small>sisa ${idn(k.margin,1)} dB</small></td><td>${k.lolos?"<b>"+esc(k.vonis)+"</b>":esc(k.vonis)}</td></tr>`).join("")}</table>`}`}
/* ---------- 1.6.0: penjelasan lima bagian, Saran Tembuku, perbandingan biaya, dasbor ---------- */
const OLEH={SARAN:"Desainer memakai Saran Tembuku",MANUAL:"Dipilih sendiri oleh desainer"};
function sarBox(d,kecil){const s=d.saran;if(!s)return"";
 return `<div class="sar ${s.dipakai?"pakai":""}"><b>${s.dipakai?"✓ Saran Tembuku dipakai.":"💡 "+esc(s.ringkas)}</b><br>${esc(s.alasan)}`+
 (s.akibat.length?`<br><b>Yang perlu ditimbang:</b> ${s.akibat.map(esc).join("; ")}.`:"")+
 (kecil?"":`<br><span class="muted">Keyakinan ${s.yakin=="tinggi"?"tinggi":"sedang"}. Saran ini tetap dalam batas teknis: tube kosong, redaman, aturan 4 km, kapasitas closure dan panjang kabel baru semuanya aman. ${s.dipakai?"":"Untuk memakainya, centang di jendela Saran Tembuku di QGIS, atau klik dua kali pilihan #"+(s.no||"-")+" di panel Tembuku."}</span>`)+`</div>`}
function detPj(d){let h="";if(d.oleh)h+=`<div class="why" style="border-color:#7c3aed"><b>${esc(OLEH[d.oleh]||d.oleh)}.</b></div>`;
 h+=sarBox(d);
 if(!d.pj||!d.pj.length)return h+d.alasan.map(a=>`<div class="why">${esc(a)}</div>`).join("")+d.peringatan.map(a=>`<div class="warn">${esc(a)}</div>`).join("");
 const gaya=["why","why","","warn",""];
 h+=`<div class="pj">`+d.pj.map((b,j)=>j==4?"":`<h4>${j+1}. ${esc(b[0])}</h4>`+(j==2?`<ul>${b[1].map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:b[1].map(x=>`<div class="${gaya[j]||"why"}"${j==1?' style="border-color:#2b3a8f;background:#f1f3fb"':""}>${esc(x)}</div>`).join(""))).join("")+`</div>`;
 return h}
function cmp(d){const r=d.kandidat.filter(k=>k.biaya&&(k.lolos||k.saran||k.pilih)).map(k=>({n:"#"+k.no+" "+k.nama+(k.tube?" T"+k.tube:""),b:k.biaya,c:k.pilih?"#0f766e":(k.saran?"#7c3aed":"#c9c3b2")}));
 if(d.biaya_fb)r.push({n:"Feeder baru dari POP",b:d.biaya_fb,c:d.kep=="FEEDER_BARU"?"#2b3a8f":"#9aa3c7"});
 if(r.length<2)return"";const mx=Math.max(...r.map(x=>x.b));
 return `<div style="font-size:12px;color:#5b6b78;margin:10px 0 2px">Perbandingan biaya relatif (makin pendek makin hemat). Hijau: yang dipakai. Ungu: Saran Tembuku.</div><div class="cmp">`+
 r.sort((a,b)=>a.b-b.b).map(x=>`<div><span class="nm" title="${esc(x.n)}">${esc(x.n)}</span><i class="b" style="width:${Math.max(2,Math.round(300*x.b/mx))}px;background:${x.c}"></i><span>${idn(x.b)}</span></div>`).join("")+`</div>`}
function risiko(d){const r=[];
 if(d.kep=="PERLU_MANUAL")r.push([100,"Perlu dirancang manual: "+(d.alasan[0]||"")]);
 if(d.margin!=null&&d.margin<0)r.push([60,`Redaman sudah memakai cadangan (sisa ${idn(d.margin,1)} dB), sebaiknya diukur di lapangan`]);
 else if(d.margin!=null&&d.margin<1)r.push([25,`Sisa redaman tipis (${idn(d.margin,1)} dB)`]);
 if(d.kep=="COLO_CEK")r.push([45,"Pastikan dulu tube-nya memang masih kosong"]);
 if(d.batas)r.push([40,"Dua pilihan hampir sama bagusnya, coba lihat keduanya"]);
 if(d.bantu>0)r.push([30,`Ada ${idn(d.bantu)} m garis bantu lurus yang perlu digambar ulang`]);
 if(d.saran&&!d.saran.dipakai)r.push([d.saran.yakin=="tinggi"?35:20,"Saran Tembuku: "+d.saran.ringkas]);
 if(d.rapi)r.push([15,`${idn(d.rapi)} m kabel existing digambar ulang mengikuti jalan, cek sebentar`]);
 if(d.kep=="COLO_MANUAL")r.push([20,"Pilihan desainer, baca catatannya"]);
 (d.penting||[]).forEach(p=>r.push([60,p]));
 if(d.janggal)r.push([20,"Memakai kabel existing yang gambarnya kurang rapi"]);
 if(d.peringatan.length)r.push([5*Math.min(4,d.peringatan.length),d.peringatan.length+" catatan"]);
 return r}
function tab(dash){document.body.classList.toggle("dash",!!dash);document.getElementById("t-dash").classList.toggle("on",!!dash);document.getElementById("t-det").classList.toggle("on",!dash);if(!dash)setTimeout(pas,30)}
function buka(i){tab(0);filt="ALL";rChips();show(i)}
let urut={k:"risk",a:-1};
function rDash(){const el=document.getElementById("dash");if(!D.length){el.innerHTML="<p>Tidak ada FDT.</p>";return}
 const R=D.map((d,i)=>{const r=risiko(d);return{d,i,r,s:r.reduce((a,x)=>a+x[0],0)}});
 const sum=(f)=>D.reduce((a,d)=>a+(+f(d)||0),0);
 const b48=sum(d=>d.core==48?d.baru:0),b96=sum(d=>d.core==96?d.baru:0),bl=sum(d=>d.core!=48&&d.core!=96?d.baru:0);
 const nSar=D.filter(d=>d.saran).length,nRisk=R.filter(x=>x.s>=25).length,T=M.temuan||[],nCek=T.filter(t=>t.tingkat=="PERINGATAN"||t.tingkat=="FATAL").length;
 const mg=D.map(d=>d.margin).filter(x=>x!=null),mmin=mg.length?Math.min(...mg):null;
 let h=`<div class="cards">
<div class="card"><small>FDT dirancang</small><b>${D.length}</b><small>${n("COLO")+n("COLO_CEK")+n("COLO_MANUAL")} pakai feeder yang ada · ${n("FEEDER_BARU")} feeder baru · ${n("PERLU_MANUAL")} manual</small></div>
<div class="card"><small>Kabel baru total</small><b>${idn(sum(d=>d.baru))} m</b><small>${b48?"48C "+idn(b48)+" m ":""}${b96?"· 96C "+idn(b96)+" m":""}${bl?" · lain "+idn(bl)+" m":""}</small></div>
<div class="card"><small>Numpang feeder (colo cable)</small><b>${idn(sum(d=>d.colo))} m</b><small>serat lewat kabel feeder yang sudah ada</small></div>
<div class="card"><small>Perlu tiang baru</small><b>${idn(sum(d=>d.infra))} m</b><small>New Infra</small></div>
<div class="card"><small>Biaya relatif total</small><b>${idn(sum(d=>d.biaya))}</b><small>numpang kabel x1, numpang tiang x20, tiang baru x100</small></div>
<div class="card ${mmin!=null&&mmin<0?"awas":""}"><small>Sisa redaman terkecil</small><b>${mmin==null?"-":idn(mmin,1)+" dB"}</b><small>setelah cadangan 3 dB</small></div>
<div class="card aksen"><small>Saran Tembuku</small><b>${nSar}</b><small>pilihan yang lebih hemat atau lebih aman</small></div>
<div class="card ${nRisk?"awas":""}"><small>Perlu perhatian</small><b>${nRisk}</b><small>FDT dengan catatan penting · ${nCek} catatan data</small></div>
<div class="card ${T.some(t=>t.kategori=="Gambar kabel"&&t.tingkat=="PERINGATAN")?"awas":""}"><small>Gambar kabel kurang rapi</small><b>${(()=>{const s=T.find(t=>t.kategori=="Gambar kabel"&&/^Ada \d+ kabel di sekitar FDT/.test(t.pesan));return s?parseInt(s.pesan.slice(4)):0})()}</b><small>di compile atau inventaris, tetap dipakai</small></div></div>`;
 const top=R.filter(x=>x.r.length).sort((a,b)=>b.s-a.s);
 h+=`<div class="grid2"><div class="pnl"><h3>Yang perlu Anda cek dulu</h3><div class="muted">Yang paling penting di atas. Klik salah satu untuk membuka detailnya.</div>`+
 (top.length?top.slice(0,30).map(x=>{const lv=x.s>=60?"#b4232c":x.s>=25?"#d97706":"#5fb3a3";return `<div class="risk" onclick="buka(${x.i})"><span class="lvl" style="background:${lv}"></span><div><b>${esc(x.d.kode)}</b> <span class="tag ${x.d.kep}">${NAMA[x.d.kep]}</span><br><span style="font-size:12.5px">${x.r.sort((a,b)=>b[0]-a[0]).map(r=>esc(r[1])).join(" · ")}</span></div></div>`}).join(""):
 `<div class="why">Tidak ada catatan penting. Tetap tinjau jalur tiap FDT di peta sebelum ditempel ke compile.</div>`)+`</div>`;
 const S=D.map((d,i)=>({d,i})).filter(o=>o.d.saran);
 h+=`<div class="pnl"><h3>Saran Tembuku</h3><div class="muted">Selain desain sesuai aturan, Tembuku juga mencoba pilihan yang melonggarkan aturan arah, koridor atau utara/selatan. Yang jauh lebih hemat atau lebih aman muncul di sini. Desain sesuai aturan tetap dipakai kecuali Anda memilih sarannya.</div>`+
 (S.length?S.map(o=>`<div style="cursor:pointer" onclick="buka(${o.i})"><b>${esc(o.d.kode)}</b>${sarBox(o.d,true)}</div>`).join(""):
 `<div class="why">Tidak ada saran kali ini. Untuk semua FDT, desain sesuai aturan sudah pilihan yang paling masuk akal. Saran baru muncul kalau ada yang minimal 20% lebih hemat, atau sinyalnya lebih aman dengan biaya hampir sama.</div>`)+`</div></div>`;
 const GK=T.filter(t=>t.kategori=="Gambar kabel");
 if(GK.length)h+=`<div class="pnl"><h3>Gambar kabel yang kurang rapi di data masukan</h3><div class="muted">Bentang tiang biasanya 40–50 m, jadi garis lurus ratusan meter atau belokan berbalik arah biasanya tanda gambarnya disederhanakan atau ada titik yang salah. Kabelnya tetap dipakai karena tube-nya memang ada. Kalau dipakai FDT, Tembuku menggambarnya ulang mengikuti jalan dan memberi tahu bila panjang sebenarnya mengubah ukuran kabel atau redaman. Koordinatnya bisa ditempel di pencarian Google Earth untuk merapikan gambar aslinya.</div>`+
 GK.map(t=>`<div class="${t.tingkat=="PERINGATAN"?"warn":"why"}" style="${t.tingkat=="PERINGATAN"?"":"border-color:#9aa3c7;background:#f6f7fb"}">${t.berkas?"<b>"+esc(t.berkas)+"</b>: ":""}${esc(t.pesan)}</div>`).join("")+`</div>`;
 h+=`<div class="pnl"><h3>Perbandingan semua FDT</h3><div class="muted">Klik judul kolom untuk mengurutkan, klik baris untuk membuka detail.</div><div style="overflow-x:auto"><table id="tbl"></table></div></div>`;
 const G=M.tube||[];
 if(G.length)h+=`<div class="pnl"><h3>Peta tube feeder</h3><div class="muted">Isi tube setiap feeder di POP yang dipakai. Abu-abu = sudah terpakai desain sebelumnya, emas = dipakai FDT di laporan ini, putih = masih kosong. T1–T8 jalur kabel 96 core, T9–T12 jalur cabang 48 core.</div>
<table><tr><th>POP</th><th>Feeder</th><th>T1 … T12</th><th>Kosong</th></tr>${G.map(g=>{let k=0;const c=[];for(let t=1;t<=12;t++){const v=g.tube[t];if(!v)k++;
 c.push(`<span class="${!v?"kosong":v=="lama"?"lama":"baru"}" title="T${t}: ${!v?"kosong":v=="lama"?"terpakai desain sebelumnya":"dipakai "+esc(v)}">${t}</span>`)}
 return `<tr><td>${esc(g.pop)}</td><td><b>F${g.feeder}</b></td><td><div class="tb">${c.join("")}</div></td><td>${k?k+" tube":""}${k==0?'<span class="tag PERLU_MANUAL" style="margin:0">penuh</span>':k==1?' <span class="tag COLO_CEK">hampir penuh</span>':""}</td></tr>`}).join("")}</table></div>`;
 el.innerHTML=h;rTbl(R)}
function rTbl(R){R=R||D.map((d,i)=>{const r=risiko(d);return{d,i,r,s:r.reduce((a,x)=>a+x[0],0)}});
 const K=[["kode","FDT",x=>x.d.kode],["kep","Keputusan",x=>NAMA[x.d.kep]],["ft","Folder",x=>x.d.nomor.feeder*100+x.d.nomor.t],["core","Kabel",x=>x.d.core],["baru","Kabel baru (m)",x=>x.d.baru],["colo","Colo (m)",x=>x.d.colo],["infra","New infra (m)",x=>x.d.infra],["biaya","Biaya relatif",x=>x.d.biaya],["margin","Sisa redaman (dB)",x=>x.d.margin],["risk","Perhatian",x=>x.s]];
 const mx=f=>Math.max(1,...R.map(x=>+f(x)||0));const mb=mx(x=>x.d.baru),mc=mx(x=>x.d.biaya);
 const ks=K.find(k=>k[0]==urut.k)||K[9];R.sort((a,b)=>{const p=ks[2](a),q=ks[2](b);return (p==q?0:(p==null?1:q==null?-1:(p>q?1:-1)))*urut.a});
 const bar=(v,m,c)=>v==null?"-":`<span class="barbox"><i style="width:${Math.round(100*v/m)}%;background:${c}"></i></span>${idn(v)}`;
 document.getElementById("tbl").innerHTML=`<tr>${K.map(k=>`<th class="urut" onclick="urut={k:'${k[0]}',a:urut.k=='${k[0]}'?-urut.a:1};rTbl()">${k[1]}${urut.k==k[0]?(urut.a>0?" ▲":" ▼"):""}</th>`).join("")}</tr>`+
 R.map(x=>{const d=x.d,m=d.margin;return `<tr style="cursor:pointer" onclick="buka(${x.i})"><td><b>${esc(d.kode)}</b>${d.saran?' <span class="tag SARAN">saran</span>':""}</td><td><span class="tag ${d.kep}">${NAMA[d.kep]}</span></td><td>F${d.nomor.feeder}_T${d.nomor.t}</td><td>${d.core?d.core+"C":"-"}</td>
<td>${bar(d.baru,mb,"#0f766e")}</td><td>${d.colo==null?"-":idn(d.colo)}</td><td>${d.infra==null?"-":idn(d.infra)}</td><td>${bar(d.biaya,mc,"#2b3a8f")}</td>
<td style="color:${m==null?"inherit":m<0?"#b4232c":m<1?"#b7791f":"#0f766e"};font-weight:600">${m==null?"-":idn(m,1)}</td><td>${x.s?`<span class="lvl" style="display:inline-block;margin:0 4px 0 0;background:${x.s>=60?"#b4232c":x.s>=25?"#d97706":"#5fb3a3"}"></span>${x.r.length}`:"-"}</td></tr>`}).join("")}
function csv(){const r=[["FDT","Keputusan","Perlu ditinjau","Folder compile (F/T)","Kabel (core)","Kabel baru (m)","Colo cable (m)","New infra (m)","Biaya relatif","Sisa redaman (dB)","Jika feeder baru dari POP (m)","POP","Saran Tembuku","Alasan"]].concat(D.map(d=>[d.kode,NAMA[d.kep]||d.kep,d.batas?"ya":"",`F${d.nomor.feeder}_T${d.nomor.t}`,d.core,d.baru,d.colo,d.infra,d.biaya,d.margin,d.fb,d.pop,d.saran?d.saran.ringkas:"",d.alasan.join(" | ")]));
const t=r.map(x=>x.map(v=>`"${String(v==null?"":v).replace(/"/g,'""')}"`).join(",")).join("\n");const a=document.createElement("a");
a.href=URL.createObjectURL(new Blob(["﻿"+t],{type:"text/csv"}));a.download="tembuku_ringkasan.csv";a.click()}
(function(){const U=M.uji;if(!U||!U.ringkasan)return;const r=U.ringkasan;
document.getElementById("uji").innerHTML=`<details open><summary>UJI AKURASI: dibandingkan dengan desain desainer (${r.n} traksi)</summary>
<div class="kpi"><div>Keputusan sama<b>${r.keputusan_cocok}/${r.n}</b></div><div>Folder F/T sama<b>${r.folder_cocok}/${r.n}</b></div>
<div>Selisih titik sambung (tengah)<b>${r.tap_median_m==null?"-":idn(r.tap_median_m)+" m"}</b></div><div>Titik sambung &le;100 m<b>${r.tap_dalam_100m}/${r.tap_n}</b></div>
<div>Jalur sama (tengah)<b>${r.jalur_median_pct==null?"-":r.jalur_median_pct+"%"}</b></div></div>
<div style="font-size:11.5px;color:#5b6b78">Cara uji: setiap traksi (dan traksi sesudahnya) disembunyikan, lalu dirancang ulang oleh Tembuku dan dibandingkan dengan desain aslinya. Garis hitam putus-putus di peta = desain desainer.</div></details>`})();
(function(){const T=M.temuan||[];const c={};T.forEach(t=>c[t.tingkat]=(c[t.tingkat]||0)+1);
let h=`<details ${c.FATAL||c.PERINGATAN?"open":""}><summary>Pemeriksaan data masukan: ${c.DIKOREKSI||0} dikoreksi otomatis, ${c.PERINGATAN||0} perlu dicek, ${c.INFO||0} catatan</summary>`+
(T.length?T.map(t=>`<div class="t-${t.tingkat}">● <b>${esc(TK[t.tingkat]||t.tingkat)}</b> ${t.berkas?esc(t.berkas)+": ":""}${esc(t.pesan)}${t.saran?` <i>→ ${esc(t.saran)}</i>`:""}</div>`).join(""):"<div>Semua berkas terbaca dengan benar.</div>")+`</details>`;
const B=M.berkas||{},BK=M.bukti||{};h+=`<details><summary>Berkas yang dibaca dan alasannya</summary><div class="muted">Jenis setiap berkas dikenali dari isinya (bentuk objek, kolom data, susunan folder), bukan dari nama berkasnya.</div>${Object.keys(B).map(k=>`<div><b>${esc(k)}</b>:<ul>${B[k].map(f=>`<li>${esc(f)}${BK[f]?` <i class="muted">— ${esc(BK[f])}</i>`:""}</li>`).join("")}</ul></div>`).join("")}</details>`;
const P=M.parameter||{};h+=`<details><summary>Dasar keputusan dan nilai yang dipakai</summary><table><tr><th>Pengaturan</th><th>Nilai</th><th>Jenis</th><th>Dasar</th></tr>${Object.keys(P).map(k=>`<tr><td>${esc(k)}</td><td><b>${esc(P[k][0])}</b></td><td>${esc(P[k][1])}</td><td>${esc(P[k][2])}</td></tr>`).join("")}</table></details>`;
h+=`<details><summary>Kamus istilah</summary><table>${(M.istilah||[]).map(x=>`<tr><td><b>${esc(x[0])}</b></td><td>${esc(x[1])}</td></tr>`).join("")}</table></details>`;
document.getElementById("cek").innerHTML=h})();
rChips();rList();if(D.length)show(0);else map.setView([-2.5,118],5);rDash();
</script></body></html>"""
