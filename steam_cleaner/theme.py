from __future__ import annotations

from PySide6 import QtGui
from PySide6.QtWidgets import QApplication


DARK_STYLESHEET = """
QWidget {
  background-color: #171b22;
  color: #e9edf2;
}
QLineEdit, QTableWidget, QComboBox, QTextEdit {
  background-color: #1f252f;
  border: 1px solid #323d4d;
  padding: 4px;
}
QPushButton {
  background-color: #2a3442;
  border: 1px solid #3d4d63;
  padding: 6px 10px;
}
QPushButton:hover {
  background-color: #364559;
}
QHeaderView::section {
  background-color: #242d39;
  border: 1px solid #3a4658;
  padding: 4px;
}
QTableWidget::item:selected {
  background-color: #314053;
  color: #eef2f7;
}
QTableView::indicator {
  width: 14px;
  height: 14px;
  border: 1px solid #5c6f87;
  background-color: #1f252f;
}
QTableView::indicator:checked {
  border: 1px solid #9fb3cc;
  background-color: #4f6784;
}
QCheckBox {
  spacing: 8px;
}
QCheckBox::indicator {
  width: 14px;
  height: 14px;
  border: 1px solid #5c6f87;
  background-color: #1f252f;
}
QCheckBox::indicator:checked {
  border: 1px solid #9fb3cc;
  background-color: #4f6784;
}
QStatusBar {
  background-color: #1f252f;
}
"""

LIGHT_STYLESHEET = """
QWidget {
  background-color: #f3f5f8;
  color: #171b22;
}
QLineEdit, QTableWidget, QComboBox, QTextEdit {
  background-color: #ffffff;
  border: 1px solid #c3c8d0;
  padding: 4px;
}
QPushButton {
  background-color: #dde3ea;
  border: 1px solid #b5becc;
  padding: 6px 10px;
}
QPushButton:hover {
  background-color: #d2d9e2;
}
QHeaderView::section {
  background-color: #e7ebf1;
  border: 1px solid #c3c8d0;
  padding: 4px;
}
QTableWidget::item:selected {
  background-color: #d9e2ee;
  color: #141a24;
}
QTableView::indicator {
  width: 14px;
  height: 14px;
  border: 1px solid #8190a4;
  background-color: #e7ebf1;
}
QTableView::indicator:checked {
  border: 1px solid #5f7390;
  background-color: #8ba2be;
}
QCheckBox::indicator {
  width: 14px;
  height: 14px;
  border: 1px solid #8190a4;
  background-color: #e7ebf1;
}
QCheckBox::indicator:checked {
  border: 1px solid #5f7390;
  background-color: #8ba2be;
}
QStatusBar {
  background-color: #e9edf2;
}
"""


def detect_system_dark_mode() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    color = app.palette().color(QtGui.QPalette.ColorRole.Window)
    return color.lightness() < 128


def apply_theme(theme_name: str) -> None:
    app = QApplication.instance()
    if app is None:
        return

    selected = theme_name.lower()
    if selected == "auto":
        selected = "dark" if detect_system_dark_mode() else "light"

    if selected == "dark":
        app.setStyleSheet(DARK_STYLESHEET)
    else:
        app.setStyleSheet(LIGHT_STYLESHEET)
