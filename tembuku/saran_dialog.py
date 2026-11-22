# -*- coding: utf-8 -*-
# Tembuku - pop-up Saran Tembuku. Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0-or-later (lihat LICENSE).
"""Pop-up after a batch run: lists every FDT where Tembuku found a clearly better alternative than the rule-based design.
Nothing changes unless the designer ticks a suggestion and presses 'Use ticked suggestions'. The rule-based design is the
default (all boxes unticked), so pressing 'Keep the rule-based design' or closing the window keeps everything as it was."""
from qgis.PyQt import QtGui, QtWidgets

from . import qtc
from .inti.teks import en

KOLOM = ["Use", "FDT", "Rule-based design", "Tembuku's suggestion", "Gain", "Rule relaxed", "Consequence", "Confidence"]


def _rupa(x):
    return "{:,}".format(int(round(x or 0)))


def daftar_saran(hasil):
    return [h for h in hasil if h.get("saran") and not h["saran"].get("dipakai")]


class DialogSaran(QtWidgets.QDialog):
    def __init__(self, hasil, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tembuku's suggestions")
        self.resize(1080, 420)
        self.hasil = daftar_saran(hasil)
        lay = QtWidgets.QVBoxLayout(self)
        lb = QtWidgets.QLabel(
            "<b>For %d FDT(s) there is an option that looks clearly better than the rule-based design.</b><br>"
            "Some meet every rule and were only ranked lower; others bend one planning rule (shown under 'Rule "
            "relaxed'). All stay within every technical limit: free tube, signal budget, the 4 km rule, closure capacity "
            "and new-cable length. Nothing changes unless you tick it. Hover over a row to read why." % len(self.hasil))
        lb.setWordWrap(True)
        lay.addWidget(lb)
        self.tabel = QtWidgets.QTableWidget(len(self.hasil), len(KOLOM))
        self.tabel.setHorizontalHeaderLabels(KOLOM)
        self.tabel.setEditTriggers(qtc.NO_EDIT)
        self.tabel.setSelectionBehavior(qtc.SELECT_ROWS)
        self.tabel.verticalHeader().setVisible(False)
        cek = qtc.e(qtc.QT, "ItemFlag", "ItemIsUserCheckable")
        aktif = qtc.e(qtc.QT, "ItemFlag", "ItemIsEnabled")
        tidak = qtc.e(qtc.QT, "CheckState", "Unchecked")
        for r, h in enumerate(self.hasil):
            s = h["saran"]
            k = s["kandidat"]
            sel = h.get("terpilih")
            aturan = (sel.get("nama") or sel.get("id")) if sel else "New feeder from the POP"
            inf = k.get("kap_info") or {}
            if s["jenis"] == "HEMAT":
                untung = "%d%% cheaper (%s vs %s)" % (s["hemat_pct"], _rupa(s["biaya_saran"]), _rupa(s["biaya_aturan"]))
            else:
                untung = "Safer signal: %.1f dB spare" % (s["margin_saran"] or 0)
            vals = ["", h["fdt"]["kode"], aturan, "%s, tube T%s" % (k.get("nama") or k.get("id"), inf.get("tube") or "-"),
                    untung, "; ".join(en(x) for x in s["dilonggarkan"]) or "None (meets every rule)",
                    "; ".join(en(x) for x in s["akibat"]) or "-", "High" if s["yakin"] == "tinggi" else "Medium"]
            tip = "\n".join([en(s["ringkas"]), en(s["alasan"])] + [en(x) for x in s["akibat"]])
            for c, v in enumerate(vals):
                it = QtWidgets.QTableWidgetItem(v)
                it.setToolTip(tip)
                if c == 0:
                    it.setFlags(cek | aktif)
                    it.setCheckState(tidak)
                if c == 3:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if c == 6 and s["akibat"]:
                    it.setForeground(QtGui.QBrush(QtGui.QColor("#b45309")))
                self.tabel.setItem(r, c, it)
        self.tabel.horizontalHeader().setSectionResizeMode(qtc.TO_CONTENTS)
        self.tabel.horizontalHeader().setSectionResizeMode(6, qtc.STRETCH)
        lay.addWidget(self.tabel, 1)
        catatan = QtWidgets.QLabel("What you tick goes into the KMZ files and the report as your choice. You can still "
                                   "change any FDT later in the Tembuku panel by double-clicking another option.")
        catatan.setWordWrap(True)
        catatan.setStyleSheet("color:#5b6b78")
        lay.addWidget(catatan)
        bar = QtWidgets.QHBoxLayout()
        bar.addStretch(1)
        b_tetap = QtWidgets.QPushButton("Keep the rule-based design")
        b_pakai = QtWidgets.QPushButton("Use ticked suggestions")
        b_tetap.setDefault(True)
        b_tetap.clicked.connect(self.reject)
        b_pakai.clicked.connect(self.accept)
        bar.addWidget(b_tetap)
        bar.addWidget(b_pakai)
        lay.addLayout(bar)

    def dipilih(self):
        ya = qtc.e(qtc.QT, "CheckState", "Checked")
        return [h for r, h in enumerate(self.hasil) if self.tabel.item(r, 0).checkState() == ya]
