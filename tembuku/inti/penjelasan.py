# -*- coding: utf-8 -*-
# Tembuku - penjelasan hasil untuk desainer. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later
# dengan syarat pasal 7 (lihat LICENSE).
"""Penjelasan per FDT dalam bahasa sehari-hari desainer: lima bagian tetap sehingga desainer selalu tahu di mana
mencari jawabannya.
  1. Keputusan      - apa yang dibangun dan di folder mana.
  2. Kenapa         - aturan dan angka yang menentukan.
  3. Pilihan lain   - alternatif lain dan kenapa tidak dipakai.
  4. Yang perlu dicek - hal yang sebaiknya dipastikan sebelum ditempel ke compile.
  5. Saran Tembuku  - bila ada pilihan lain yang jelas lebih hemat atau lebih aman.
Gaya: kalimat pendek, kata kerja aktif, angka secukupnya, tanpa huruf kapital semua. Semua kalimat T (Indonesia +
Inggris)."""
from . import saran as _saran
from .teks import T, gabung, m, km

_TAP = {"slack": T("slack yang sudah ada", "an existing slack"), "closure": T("closure yang sudah ada", "an existing closure"),
        "ujung": T("ujung kabel yang sudah ada", "the end of an existing cable"),
        "usulan": T("kabel baru FDT lain di proyek yang sama (closure baru di titik ini)",
                    "the new cable of another FDT in the same project (a new closure at this point)")}


def _km2(x_m):
    v = (x_m or 0) / 1000.0
    return T(('%.2f km' % v).replace('.', ','), '%.2f km' % v)


def _pct(x):
    return "%d%%" % round(100 * (x or 0))


def _rupa(x):
    return "{:,}".format(int(round(x or 0))).replace(",", ".")


def _db(x):
    return T(("%.1f" % (x or 0)).replace(".", ","), "%.1f" % (x or 0))


def _alasan_kandidat(k, sel, prm):
    """Satu kalimat: kenapa pilihan ini tidak dipakai."""
    nama = k.get("nama") or k.get("id")
    if k.get("gagal"):
        return T("%s tidak dipakai: %s.", "%s is not used: %s.") % (nama, k["gagal"][0])   # T utuh: panel Inggris
    if sel and k.get("biaya_relatif") and sel.get("biaya_relatif"):
        d = k["biaya_relatif"] / float(sel["biaya_relatif"]) - 1.0
        if d > 0.02:
            return T("%s sebenarnya bisa dipakai, tapi biayanya %s lebih mahal (kabel baru %s, numpang feeder %s).",
                     "%s could be used, but it costs %s more (new cable %s, riding the feeder %s).") % (
                nama, _pct(d), m(k.get("kabel_baru_m") or 0), m(k.get("colo_m") or 0))
        return T("%s juga bisa dipakai dengan biaya hampir sama; kalah tipis di urutan (titik sambung atau nomor feeder).",
                 "%s also works at almost the same cost; it lost narrowly on order (tap point or feeder number).") % nama
    return T("%s bisa dipakai, tapi bukan yang paling hemat.", "%s could be used, but it is not the cheapest.") % nama


def susun(h, prm):
    kep = h.get("keputusan")
    sel = h.get("terpilih")
    fb = h.get("feeder_baru") or {}
    n = h.get("penomoran") or {}
    out = []
    # 1. keputusan
    b1 = []
    if kep in ("COLO", "COLO_CEK", "COLO_MANUAL") and sel:
        inf = sel.get("kap_info") or {}
        b1.append(T("Pakai Feeder %s yang sudah ada, tube T%s. Simpan di folder F%s_T%s.",
                    "Use the existing Feeder %s, tube T%s. Save it in folder F%s_T%s.") % (
            n.get("feeder"), n.get("t"), n.get("feeder"), n.get("t")))
        baru = sel.get("new_infra_m") or 0
        b1.append(T("Dari POP, serat numpang di kabel feeder sejauh %s. Dari titik sambung ke FDT ditarik kabel baru "
                    "%d core sepanjang %s, %s di tiang yang sudah ada%s.",
                    "From the POP the fibre rides the feeder cable for %s. From the tap point a new %d-fibre cable of "
                    "%s runs to the FDT, %s of it on existing poles%s.") % (
            m(sel.get("colo_m") or 0), sel.get("core_cabang") or 48, m(sel.get("kabel_baru_m") or 0),
            _pct(sel.get("colo_rasio")),
            (T("; sisanya %s perlu tiang baru", "; the other %s needs new poles") % m(baru)) if baru >= 10 else ""))
        ts = sel.get("tap_slack") or {}
        b1.append(T("Titik sambungnya di %s.", "The tap point is at %s.") % _TAP.get(ts.get("jenis"), T(
            "tengah kabel, karena di situ belum ada slack atau closure", "mid-cable, as there is no slack or closure there yet")))
        if inf.get("kelompok"):
            sisa = [t for t in (inf.get("bebas") or []) if t != inf.get("tube")]
            b1.append(T("Tube diambil dari jalur %s. Setelah ini, tube yang masih kosong di jalur itu: %s.",
                        "The tube comes from the %s path. After this, free tubes left on that path: %s.") % (
                inf["kelompok"], gabung(", ", ["T%d" % t for t in sisa]) or T("tidak ada lagi", "none")))
    elif kep == "FEEDER_BARU":
        b1.append(T("Buat feeder baru dari %s dan simpan di folder F%s_T%s.",
                    "Build a new feeder from %s and save it in folder F%s_T%s.") % (
            (h.get("pop") or {}).get("nama", "POP"), n.get("feeder"), n.get("t")))
        b1.append(T("Isinya: OTB 144 di POP, kabel 144 core sampai closure 144, lalu kabel %d core sampai FDT. Panjang "
                    "jalurnya sekitar %s.", "It consists of an OTB 144 at the POP, a 144-fibre cable to a closure 144, "
                    "then a %d-fibre cable to the FDT. The route is about %s.") % (
            fb.get("core") or 96, km(fb.get("panjang_est_m") or fb.get("panjang_m") or 0)))
    else:
        b1.append(T("FDT ini belum bisa dirancang otomatis, jadi perlu dirancang manual.",
                    "This FDT could not be designed automatically, so it needs to be designed by hand."))
    out.append([T("Keputusan", "Decision"), b1])
    # 2. kenapa
    b2 = []
    batas = float(prm.get("batas_48f_km", 4.0))
    oleh = h.get("dipilih_desainer")
    if oleh == "SARAN":
        b2.append(T("Desainer memilih Saran Tembuku. Aturan yang dilonggarkan dan akibatnya ada di bagian Saran Tembuku.",
                    "The designer chose Tembuku's suggestion. The rule that was relaxed and what it means are under "
                    "Tembuku's suggestion."))
    elif oleh == "MANUAL":
        b2.append(T("Pilihan ini dipilih sendiri oleh desainer di panel.", "The designer picked this option in the panel."))
    if sel and kep != "FEEDER_BARU":
        js = sel.get("jalur_serat_m") or 0
        if sel.get("gagal"):
            b2.append(T("Catatan untuk pilihan ini: %s.", "Note on this choice: %s.") % gabung("; ", sel["gagal"]))
        elif not oleh:
            b2.append(T("Feeder ini masih punya tube kosong. Sesuai arahan, tube kosong di feeder yang ada dipakai dulu "
                        "sebelum membangun feeder baru.", "This feeder still has a free tube. As agreed, free tubes in "
                        "existing feeders are used before building a new feeder."))
        inf2 = sel.get("kap_info") or {}
        if sel.get("core_dari") == "TUBE":
            nb = int(inf2.get("tube_dibawa") or 1)
            b2.append(T("Kabel baru ini membawa %d tube (%s), jadi %d core. Aturan utama: sampai %d tube cukup 48 core "
                        "(48 core = 4 tube), lebih dari itu 96 core. Jalur serat dari POP ke FDT %s.",
                        "This new cable carries %d tube(s) (%s), so it has %d fibres. Main rule: up to %d tubes a "
                        "48-fibre cable is enough (48 fibres = 4 tubes), more needs 96. The fibre route from the POP to "
                        "the FDT is %s.") % (
                nb, T("FDT ini", "this FDT") if nb <= 1 else T("FDT ini dan FDT lain di proyek yang sama",
                                                              "this FDT and the other FDTs of the same project"),
                sel.get("core_cabang") or 48, int(prm.get("batas_tube_kabel_48", 4)), _km2(js)))
        else:
            b2.append(T("Jalur serat dari POP ke FDT %s, jadi kabelnya %d core. Sampai %s cukup 48 core, lebih dari itu 96 "
                        "core.", "The fibre route from the POP to the FDT is %s, so the cable has %d fibres. Up to %s a "
                        "48-fibre cable is enough; beyond that it is 96.") % (
                _km2(js), sel.get("core_cabang") or 48, km(batas * 1000)))
        bud = sel.get("budget") or {}
        if bud:
            mg = bud.get("margin_db") or 0
            b2.append(T("Redaman sampai pelanggan %s dB, batasnya %s dB. Setelah disisihkan cadangan %s dB, masih ada sisa "
                        "%s dB, %s.", "Signal loss to the customer is %s dB against a %s dB limit. After keeping a %s dB "
                        "reserve, %s dB is left, %s.") % (
                _db((bud.get("total_db") or 0) - prm["margin_db"]), "%.0f" % prm["kelas_olt_db"], "%.0f" % prm["margin_db"],
                _db(mg), T("aman", "which is safe") if mg >= 1 else (
                    T("agak tipis, jadi sebaiknya diukur di lapangan", "a bit thin, so measure it on site") if mg >= 0 else
                    T("artinya cadangannya terpakai, jadi wajib diukur di lapangan",
                      "so the reserve is partly used and it must be measured on site"))))
        if sel.get("biaya_relatif"):
            b2.append(T("Biaya relatifnya %s%s. Hitungannya: numpang kabel %s m x1, numpang tiang %s m x20, tiang baru "
                        "%s m x100.", "Its relative cost is %s%s. Worked out as: riding cable %s m x1, riding poles %s m "
                        "x20, new poles %s m x100.") % (
                _rupa(sel["biaya_relatif"]), "" if oleh else T(", paling hemat di antara feeder yang memenuhi syarat",
                                                                ", the lowest of the feeders that qualify"),
                _rupa(sel.get("colo_m")), _rupa(sel.get("colo_pole_m")), _rupa(sel.get("new_infra_m"))))
        if sel.get("memutar"):
            bfb = _saran.biaya_feeder_baru(fb, prm) if fb else None
            if bfb and sel.get("biaya_relatif") and sel["biaya_relatif"] < bfb:
                b2.append(T("Jalurnya memang lebih panjang daripada feeder baru langsung dari POP, tapi biayanya tetap "
                            "lebih hemat (%s dibanding %s) dan tube kosong yang ada jadi terpakai.",
                            "Its route is longer than a new feeder straight from the POP, but it still costs less (%s "
                            "against %s) and puts an existing free tube to use.") % (_rupa(sel["biaya_relatif"]), _rupa(bfb)))
            else:
                b2.append(T("Jalurnya lebih panjang daripada feeder baru langsung dari POP. Tetap dipakai karena sesuai "
                            "arahan, tube kosong di feeder yang ada didahulukan.",
                            "Its route is longer than a new feeder straight from the POP. It is still used because, as "
                            "agreed, free tubes in existing feeders come first."))
    elif kep == "FEEDER_BARU":
        nf = len({(k.get("pop_folder"), k.get("feeder_int") or k.get("id")) for k in h.get("kandidat") or []})
        b2.append((T("Ada %d feeder di sekitar FDT, tapi tidak ada yang memenuhi syarat. Alasan masing-masing ada di "
                     "bagian Pilihan lain.", "There are %d feeders around the FDT, but none qualifies. The reason for "
                     "each is under Other options.") % nf) if nf else
                  T("Tidak ada feeder yang ada di sekitar FDT.", "There is no existing feeder around the FDT."))
        if fb:
            b2.append(T("Jalur feeder barunya %s, jadi kabel ke FDT %d core. Sampai %s cukup 48 core, lebih dari itu 96 "
                        "core.", "The new feeder route is %s, so the cable to the FDT has %d fibres. Up to %s a 48-fibre "
                        "cable is enough; beyond that it is 96.") % (
                _km2(fb.get("panjang_est_m") or 0), fb.get("core") or 96, km(batas * 1000)))
        pr = (h.get("fdt") or {}).get("_proyek_sisa")
        if pr and pr > 1:
            b2.append(T("FDT ini satu proyek dengan %d FDT lain di berkas yang sama. Feeder yang ada baru dipakai kalau "
                        "tube kosongnya cukup untuk semuanya, supaya satu proyek tidak terpecah.",
                        "This FDT is in one project with %d other FDT(s) in the same file. An existing feeder is used only "
                        "if it has enough free tubes for all of them, so the project is not split.") % (pr - 1))
    out.append([T("Kenapa", "Why"), b2])
    # 3. pilihan lain
    b3 = []
    lihat = set()
    for k in h.get("kandidat") or []:
        if k is sel:
            continue
        kunci = (k.get("feeder_int"), k.get("pop_folder"), bool(k.get("gagal")))
        if kunci in lihat:
            continue
        lihat.add(kunci)
        b3.append(_alasan_kandidat(k, sel, prm))
        if len(b3) >= 4:
            break
    if kep != "FEEDER_BARU" and fb:
        b3.append(T("Feeder baru dari POP: jalurnya sekitar %s dengan biaya relatif %s, belum termasuk OTB dan kabel 144 "
                    "core.", "A new feeder from the POP: about %s of route at a relative cost of %s, not counting the OTB "
                    "and the 144-fibre cable.") % (km(fb.get("panjang_est_m") or 0), _rupa(_saran.biaya_feeder_baru(fb, prm))))
    if not b3:
        b3.append(T("Tidak ada pilihan lain di sekitar FDT.", "There are no other options around the FDT."))
    out.append([T("Pilihan lain", "Other options"), b3])
    # 4. yang perlu dicek
    b4 = [p for p in (h.get("peringatan") or [])]
    if not b4:
        b4.append(T("Tidak ada catatan khusus. Cukup lihat sekali lagi jalurnya di peta sebelum ditempel ke compile.",
                    "Nothing special. Just look over the route on the map once more before pasting it into the "
                    "compilation."))
    out.append([T("Yang perlu dicek", "What to check"), b4])
    # 5. saran
    s = h.get("saran")
    if s:
        b5 = [s["ringkas"], s["alasan"]]
        b5 += [T("Yang perlu ditimbang: %s.", "Worth weighing: %s.") % a for a in s.get("akibat") or []]
        b5.append(T("Tingkat keyakinan %s. Keputusan tetap di tangan desainer; desain di atas tidak berubah kecuali saran "
                    "ini dipilih.", "Confidence is %s. The designer decides; the design above stays as it is unless this "
                    "suggestion is chosen.") % (T("tinggi", "high") if s["yakin"] == "tinggi" else T("sedang", "medium")))
        out.append([T("Saran Tembuku", "Tembuku's suggestion"), b5])
    return out
