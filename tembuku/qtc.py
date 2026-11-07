# -*- coding: utf-8 -*-
# Tembuku - kompatibilitas Qt5 (QGIS 3) & Qt6 (QGIS 4). Copyright (C) 2026 Joseph Edward Timothy Siahaan. GPL-3.0+.
from qgis.PyQt import QtCore, QtGui, QtWidgets

try:                                    # Qt6 / QGIS 4
    from qgis.PyQt.QtGui import QAction  # noqa: F401
except ImportError:                     # Qt5 / QGIS 3
    from qgis.PyQt.QtWidgets import QAction  # noqa: F401


def e(cls, scope, name):
    """Enum yang sama di Qt5 (cls.Name) dan Qt6 (cls.Scope.Name)."""
    sc = getattr(cls, scope, None)
    if sc is not None and hasattr(sc, name):
        return getattr(sc, name)
    return getattr(cls, name)


def jalankan(dlg):
    return (dlg.exec if hasattr(dlg, "exec") else dlg.exec_)()


QT = QtCore.Qt
KANAN = e(QT, "DockWidgetArea", "RightDockWidgetArea")
TUNGGU = e(QT, "CursorShape", "WaitCursor")
SILANG = e(QT, "CursorShape", "CrossCursor")
RATA_KIRI = e(QT, "AlignmentFlag", "AlignLeft")
USER_ROLE = e(QT, "ItemDataRole", "UserRole")
NO_EDIT = e(QtWidgets.QAbstractItemView, "EditTrigger", "NoEditTriggers")
SELECT_ROWS = e(QtWidgets.QAbstractItemView, "SelectionBehavior", "SelectRows")
STRETCH = e(QtWidgets.QHeaderView, "ResizeMode", "Stretch")
TO_CONTENTS = e(QtWidgets.QHeaderView, "ResizeMode", "ResizeToContents")
BTN_OK = e(QtWidgets.QDialogButtonBox, "StandardButton", "Ok")
BTN_CANCEL = e(QtWidgets.QDialogButtonBox, "StandardButton", "Cancel")
ITEM_EDITABLE = e(QT, "ItemFlag", "ItemIsEditable")
