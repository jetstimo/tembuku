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
    for i, k in enumerate(h["kandidat"][:6]):
        kd.append({"no": i + 1, "nama": k["nama"] or k["id"], "label": k["label_colo"], "sumber": k["sumber"],
                   "owner": k.get("owner") or "", "model": k.get("model") or "", "kap": k["kapasitas"],
                   "ketkap": k["ket_kapasitas"], "baru": k["kabel_baru_m"], "colo": k["colo_m"], "cos": k["cos"],
                   "rasio": k.get("rasio_jalur"), "detour": k["detour"], "lolos": k["lolos"],
                   "gagal": k["gagal"], "catatan": k["catatan"], "db": k["budget"]["total_db"],
                   "vonis": str(mesin.vonis_kandidat(k)), "sudut": mesin.sudut_arah(k["cos"]), "searah": k.get("searah", True),
                   "margin": k["budget"]["margin_db"], "tap": _ll(L, [k["rute"]["titik"][0]])[0],
                   "kabel": [[round(p[1], 7), round(p[0], 7)] for p in k["ll_kabel"]],
                   "colo_ll": _ll(L, k["colo_xy"][::max(1, len(k["colo_xy"]) // 300)]) if k.get("colo_xy") else []})
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
            "berkas": f.get("berkas") or "", "nkabel": h.get("n_kabel_diperiksa", 0)}


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
.wrap{display:grid;grid-template-columns:380px 1fr;height:calc(100vh - 70px)}
aside{overflow:auto;border-right:1px solid var(--line)}
.lead{padding:14px 16px;border-bottom:1px solid var(--line);font-size:13px;color:var(--mut)}
.chips{display:flex;gap:6px;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid var(--line)}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 10px;cursor:pointer;font-size:12px;background:#fff}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.it{padding:10px 16px;border-bottom:1px solid var(--line);cursor:pointer}.it:hover{background:#f3efe2}
.it.on{background:#fff6dd;box-shadow:inset 4px 0 0 var(--emas)}
.it b{font-family:var(--display);font-weight:800}.tag{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;color:#fff;margin-left:6px}
.COLO{background:var(--teal)}.COLO_CEK{background:var(--amber)}.COLO_MANUAL{background:#7c3aed}.FEEDER_BARU{background:var(--blue)}.PERLU_MANUAL{background:var(--red)}
.BATAS{background:#7c3aed}
.leaflet-container{background:#f1eee4;font-family:var(--sans)}
main{display:grid;grid-template-rows:56% 44%;min-width:0}#peta{min-height:0}
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
</style></head><body>
<header><img src="data:image/svg+xml;base64,__LOGO__" alt=""><div><h1>Tembuku <span>&middot;</span> Laporan Desain Feeder</h1>
<small id="sub"></small></div></header>
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
const chips=[["ALL","Semua"],["COLO","Pakai feeder"],["COLO_CEK","Cek sisa tube"],["FEEDER_BARU","Feeder baru"],["PERLU_MANUAL","Manual"],["BATAS","Perlu ditinjau"]];
function rChips(){document.getElementById("chips").innerHTML=chips.map(c=>`<span class="chip ${filt==c[0]?"on":""}" data-f="${c[0]}">${c[1]}</span>`).join("");
document.querySelectorAll(".chip").forEach(e=>e.onclick=()=>{filt=e.dataset.f;rChips();rList()})}
function rList(){document.getElementById("list").innerHTML=D.map((d,i)=>({d,i})).filter(o=>filt=="ALL"||o.d.kep==filt||(filt=="BATAS"&&o.d.batas)).map(({d,i})=>
`<div class="it ${i==cur?"on":""}" data-i="${i}"><b>${esc(d.kode)}</b><span class="tag ${d.kep}">${NAMA[d.kep]}</span>${d.batas?'<span class="tag BATAS">perlu ditinjau</span>':""}
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
function show(i){cur=i;rList();const d=D[i];grp.clearLayers();
d.kandidat.forEach(k=>{L.polyline(k.kabel,{color:k.lolos?"#f59e0b":"#9ca3af",weight:k.lolos?4:2,opacity:.8}).bindTooltip(`#${k.no} ${esc(k.nama)} · ${esc(k.ketkap)}`).addTo(grp);
L.circleMarker(k.tap,{radius:5,color:"#111",fillColor:k.lolos?"#f59e0b":"#d1d5db",fillOpacity:1,weight:1}).bindTooltip("Titik sambung kandidat #"+k.no).addTo(grp)});
const sel=d.kandidat.find(k=>k.lolos||d.kep=="COLO_CEK");if(sel&&sel.colo_ll.length&&d.kep!="FEEDER_BARU")L.polyline(sel.colo_ll,{color:"#a855f7",weight:5,opacity:.7}).bindTooltip("Feeder yang dipakai: POP → titik sambung").addTo(grp);
d.seg.forEach(s=>L.polyline(s.ll,{color:W[s.k]||"#22c55e",weight:6,dashArray:s.k=="GARIS_BANTU"?"8 8":null}).bindTooltip(esc(s.n)).addTo(grp));
if(d.uji){d.uji.desain_ll.forEach(l=>L.polyline(l,{color:"#111",weight:3,dashArray:"6 6"}).bindTooltip("Desain desainer (kabel baru)").addTo(grp));
d.uji.colo_ll.forEach(l=>L.polyline(l,{color:"#111",weight:2,opacity:.5,dashArray:"2 6"}).bindTooltip("Desain desainer (colo cable)").addTo(grp))}
L.circleMarker(d.ll,{radius:9,color:"#fff",weight:3,fillColor:"#c2410c",fillOpacity:1}).bindTooltip("FDT "+esc(d.kode),{permanent:true,direction:"top"}).addTo(grp);
if(d.pop_ll)L.circleMarker(d.pop_ll,{radius:8,color:"#fff",weight:3,fillColor:"#1d4ed8",fillOpacity:1}).bindTooltip("POP "+esc(d.pop)).addTo(grp);
try{map.fitBounds(grp.getBounds().pad(.15))}catch(e){map.setView(d.ll,16)}
const nm=d.nomor;document.getElementById("det").innerHTML=`<h2>${esc(d.kode)} <span class="tag ${d.kep}">${NAMA[d.kep]}</span></h2>
<div class="kpi"><div>Folder compile<b>F${nm.feeder}_T${nm.t}</b></div><div>Kabel baru<b>${d.baru!=null?idn(d.baru)+" m":"-"}</b></div><div>Jika feeder baru dari POP<b>${d.fb!=null?idn(d.fb)+" m":"-"}</b></div>
<div>Splitter<b>${d.splitter?d.splitter+"x1x"+d.rasio:"-"}</b></div><div>Kabel yang diperiksa<b>${d.nkabel}</b></div><div>Data jalan<b>${d.jalan?"ada":"tidak ada"}</b></div></div>
${d.uji?`<div class="why" style="border-color:${d.uji.cocok?"#0e7c7b":"#c2410c"}"><b>Uji akurasi: keputusan ${d.uji.cocok?"SAMA":"BERBEDA"}.</b> Desainer: ${esc(NAMA[d.uji.desainer]||d.uji.desainer)} (${esc(d.uji.folder_desainer)}). Tembuku: ${esc(NAMA[d.uji.tembuku]||d.uji.tembuku)} (${esc(d.uji.folder_tembuku)}).${d.uji.tap_meleset_m!=null?" Titik sambung berselisih "+idn(d.uji.tap_meleset_m)+" m.":""} Kabel baru Tembuku ${d.uji.baru_tembuku_m!=null?idn(d.uji.baru_tembuku_m)+" m":"-"}, desainer ${idn(d.uji.baru_desainer_m)} m.${d.uji.jalur_sesuai_pct!=null?" Jalurnya "+d.uji.jalur_sesuai_pct+"% sama.":""}</div>`:""}
${d.alasan.map(a=>`<div class="why">${esc(a)}</div>`).join("")}${d.peringatan.map(a=>`<div class="warn">${esc(a)}</div>`).join("")}
${d.bantu>0?`<div class="warn">${idn(d.bantu)} m jalur masih berupa garis bantu lurus (tidak ada data jalan atau kabel di bagian itu): gambar ulang mengikuti tiang atau jalan.</div>`:""}
${d.kandidat.length?"":`<div class="why" style="border-color:#5a6280">Tidak ada kabel feeder di sekitar FDT yang bisa dijadikan kandidat.</div>`}${!d.kandidat.length?"":`<div style="font-size:12px;color:#5b6b78;margin:8px 0 2px">Feeder yang sudah ada di sekitar FDT dan hasil pemeriksaannya:</div>
<table><tr><th>#</th><th>Feeder</th><th>Sisa tube</th><th>Kabel baru ke FDT</th><th>Feeder dari POP ke titik sambung</th><th>Arah ke FDT</th><th title="Panjang jalur lewat feeder ini dibanding feeder baru dari POP">Panjang jalur vs feeder baru</th><th>Redaman sinyal</th><th>Hasil</th></tr>
${d.kandidat.map(k=>`<tr class="${k.lolos?"ok":"no"}"><td>${k.no}</td><td><b>${esc(k.nama)}</b><br>${esc(k.label)} ${esc(k.owner)} ${esc(k.model)}</td><td>${esc(KAP[k.kap]||k.kap)}<br><small>${esc(k.ketkap)}</small></td>
<td>${idn(k.baru)} m<br><small>${idn(k.detour,1)}× jarak lurus</small></td><td>${k.colo!=null?idn(k.colo)+" m":"tidak terlihat tersambung"}</td><td>${k.sudut==null?"-":(k.searah?"searah":"menjauh")+" ("+k.sudut+"°)"}</td><td>${k.rasio==null?"-":idn(k.rasio,2)+"×"}</td>
<td>${idn(k.db,1)} dB<br><small>sisa ${idn(k.margin,1)} dB</small></td><td>${k.lolos?"<b>"+esc(k.vonis)+"</b>":esc(k.vonis)}</td></tr>`).join("")}</table>`}`}
function csv(){const r=[["FDT","Keputusan","Perlu ditinjau","Folder compile (F/T)","Kabel baru (m)","Jika feeder baru dari POP (m)","POP","Alasan"]].concat(D.map(d=>[d.kode,NAMA[d.kep]||d.kep,d.batas?"ya":"",`F${d.nomor.feeder}_T${d.nomor.t}`,d.baru,d.fb,d.pop,d.alasan.join(" | ")]));
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
rChips();rList();if(D.length)show(0);else map.setView([-2.5,118],5);
</script></body></html>"""
