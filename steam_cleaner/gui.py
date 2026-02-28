from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .deletion import delete_game
from .models import GameEntry, GameState, MountPoint
from .scanner import scan_mount_point
from .theme import apply_theme, detect_system_dark_mode

LOGGER = logging.getLogger(__name__)


def utf8_safe_text(value: str) -> str:
    return str(value).encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def steam_is_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "steam"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


class ConfirmDeleteDialog(QDialog):
    def __init__(
        self,
        games: list[GameEntry],
        targets: list[Path],
        steam_running_now: bool,
        dry_run: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.games = games
        self.steam_running_now = steam_running_now
        self.setWindowTitle("Confirm Game Removal")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._hold_done = False
        self._hold_timer = QtCore.QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._finish_hold)

        self._allowed_inputs = {g.appid.lower() for g in games}
        self._allowed_inputs.update(g.name.lower() for g in games)

        top_text = "DRY RUN: No files will be deleted." if dry_run else "Deletion is permanent."
        if steam_running_now:
            top_text += " Steam appears to be running."
        confirm_hint_text = "Type a game name or appid to confirm, or hold button for 2 seconds:"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 16)
        main_layout.setSpacing(8)
        if len(games) == 1:
            title_text = utf8_safe_text(games[0].name)
            appid_text = f"App ID: {utf8_safe_text(games[0].appid)}"
            names_text = ""
        else:
            title_text = "Games selected for removal"
            appid_text = "App IDs: " + ", ".join(utf8_safe_text(game.appid) for game in games)
            names_text = "Games: " + ", ".join(utf8_safe_text(game.name) for game in games)

        title_label = QLabel(f"<span style='font-size:22px; font-weight:700;'>{title_text}</span>", self)
        title_label.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(title_label)

        appid_label = QLabel(f"<span style='font-size:12px; color:#888;'>{appid_text}</span>", self)
        appid_label.setTextFormat(Qt.TextFormat.RichText)
        main_layout.addWidget(appid_label)
        if names_text:
            names_label = QLabel(utf8_safe_text(names_text), self)
            names_label.setWordWrap(True)
            names_label.setStyleSheet("font-size: 12px; color: #888;")
            main_layout.addWidget(names_label)
        main_layout.addSpacing(14)

        main_layout.addWidget(QLabel(top_text))

        main_layout.addWidget(QLabel("Paths targeted for deletion:"))
        listing = QTextEdit(self)
        listing.setReadOnly(True)
        listing.setPlainText("\n".join(utf8_safe_text(p) for p in targets))
        main_layout.addWidget(listing)
        main_layout.addSpacing(12)

        main_layout.addWidget(QLabel(confirm_hint_text))

        self.confirm_input = QLineEdit(self)
        self.confirm_input.setPlaceholderText("Game name or appid")
        self.confirm_input.textChanged.connect(self._update_accept_state)
        main_layout.addWidget(self.confirm_input)

        self.hold_label = QLabel("Hold-to-confirm not completed", self)
        main_layout.addWidget(self.hold_label)

        self.hold_button = QPushButton("Hold to confirm (2s)", self)
        self.hold_button.pressed.connect(self._start_hold)
        self.hold_button.released.connect(self._cancel_hold)
        main_layout.addWidget(self.hold_button)

        if steam_running_now:
            self.steam_warning_checkbox = QCheckBox("I understand Steam is running and still want to proceed", self)
            self.steam_warning_checkbox.stateChanged.connect(self._update_accept_state)
            main_layout.addWidget(self.steam_warning_checkbox)
        else:
            self.steam_warning_checkbox = None

        button_row = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.accept_button = QPushButton("Confirm", self)
        self.accept_button.clicked.connect(self.accept)
        self.accept_button.setEnabled(False)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.accept_button)
        main_layout.addLayout(button_row)

        fm_title = QFontMetrics(title_label.font())
        fm_body = QFontMetrics(self.font())
        required_width = max(
            fm_title.horizontalAdvance(title_text),
            fm_body.horizontalAdvance(confirm_hint_text),
        )
        self.resize(max(560, required_width + 72), 540)

    def _start_hold(self) -> None:
        self._hold_done = False
        self.hold_label.setText("Holding...")
        self._hold_timer.start(2000)

    def _cancel_hold(self) -> None:
        if self._hold_done:
            return
        if self._hold_timer.isActive():
            self._hold_timer.stop()
            self.hold_label.setText("Hold canceled")
        self._update_accept_state()

    def _finish_hold(self) -> None:
        self._hold_done = True
        self.hold_label.setText("Hold-to-confirm completed")
        self._update_accept_state()
        if self.accept_button.isEnabled():
            self.accept_button.setFocus()

    def _update_accept_state(self) -> None:
        typed = self.confirm_input.text().strip().lower()
        text_ok = typed in self._allowed_inputs
        steam_ok = True
        if self.steam_warning_checkbox is not None:
            steam_ok = self.steam_warning_checkbox.isChecked()

        can_confirm = (text_ok and steam_ok) or (self._hold_done and steam_ok)
        self.accept_button.setEnabled(can_confirm)


class ManageLocationsDialog(QDialog):
    def __init__(self, mount_paths: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Locations")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Known mount points (select one or more to remove):"))

        self.locations_list = QListWidget(self)
        self.locations_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for mount_path in mount_paths:
            item = QListWidgetItem(mount_path)
            self.locations_list.addItem(item)
        layout.addWidget(self.locations_list)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.remove_button = QPushButton("Remove Selected", self)
        self.remove_button.clicked.connect(self.accept)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.remove_button)
        layout.addLayout(controls)

    def selected_mount_paths(self) -> list[str]:
        return [item.text() for item in self.locations_list.selectedItems()]


class TrashIconButton(QPushButton):
    hovered = QtCore.Signal(bool)

    def __init__(self, icon_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._source_icon = QIcon(str(icon_path))
        self._base_icon_size = QtCore.QSize(48, 48)
        self._pressed_icon_size = QtCore.QSize(52, 52)
        self._is_hovered = False
        self._is_pressed = False
        self.setFlat(True)
        self.setMinimumSize(48, 48)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._update_icon()

    def _make_alpha_icon(self, size: QtCore.QSize, alpha: float) -> QIcon:
        src = self._source_icon.pixmap(size)
        out = QPixmap(size)
        out.fill(Qt.GlobalColor.transparent)
        painter = QPainter(out)
        painter.setOpacity(alpha)
        painter.drawPixmap(0, 0, src)
        painter.end()
        return QIcon(out)

    def _update_icon(self) -> None:
        size = self._pressed_icon_size if self._is_pressed else self._base_icon_size
        alpha = 0.5 if not self.isEnabled() else (1.0 if self._is_hovered else 0.9)
        self.setIconSize(size)
        self.setIcon(self._make_alpha_icon(size, alpha))

    def enterEvent(self, event) -> None:
        self._is_hovered = True
        self._update_icon()
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._is_hovered = False
        self._is_pressed = False
        self._update_icon()
        self.hovered.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self._update_icon()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._is_pressed = False
        self._is_hovered = self.underMouse()
        self._update_icon()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._update_icon()


class RowSelectCheckBox(QCheckBox):
    hovered = QtCore.Signal(bool)

    def enterEvent(self, event) -> None:
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered.emit(False)
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Steam Library Cleaner")
        self.resize(1100, 700)

        self.mount_points: dict[str, MountPoint] = {}
        self.games_by_key: dict[tuple[str, str], GameEntry] = {}
        self.config_dir = Path.home() / ".config" / "steam-man"
        self.mounts_file = self.config_dir / "mount_points.json"
        self.current_theme = "Auto"
        self.allow_delete_while_steam_running = False
        self._sort_column = 1
        self._sort_order = Qt.SortOrder.AscendingOrder

        self._build_ui()
        self._load_saved_theme()
        apply_theme(self.current_theme.lower())
        if not self._handle_startup_steam_warning():
            QtCore.QTimer.singleShot(0, self.close)
            return
        self._load_saved_mount_points()
        self._refresh_table()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        toolbar_layout = QGridLayout()

        self.add_button = QPushButton("+")
        self.add_button.setToolTip("Add mount point")
        self.add_button.clicked.connect(self.on_add_mount_point)

        self.remove_selected_button = QPushButton("-")
        self.remove_selected_button.setToolTip("Remove selected games")
        self.remove_selected_button.clicked.connect(self.on_remove_selected)

        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.clicked.connect(self.on_rescan)

        self.locations_button = QPushButton("Locations")
        self.locations_button.setToolTip("Manage saved mount points")
        self.locations_button.clicked.connect(self.on_manage_locations)

        self.theme_box = QComboBox()
        self.theme_box.addItems(["Auto", "Light", "Dark"])
        self.theme_box.currentTextChanged.connect(self._on_theme_changed)

        self.dry_run_checkbox = QCheckBox("Dry run")
        self.optional_delete_checkbox = QCheckBox("Delete compatdata/shadercache/caches")
        self.optional_delete_checkbox.setChecked(True)

        toolbar_layout.addWidget(self.add_button, 0, 0)
        toolbar_layout.addWidget(self.remove_selected_button, 0, 1)
        toolbar_layout.addWidget(self.rescan_button, 0, 2)
        toolbar_layout.addWidget(self.locations_button, 0, 3)
        toolbar_layout.addWidget(QLabel("Theme"), 0, 4)
        toolbar_layout.addWidget(self.theme_box, 0, 5)
        toolbar_layout.addWidget(self.dry_run_checkbox, 0, 6)
        toolbar_layout.addWidget(self.optional_delete_checkbox, 0, 7)
        toolbar_layout.setColumnStretch(8, 1)

        layout.addLayout(toolbar_layout)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search (Game Name):"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type one or more terms to filter game names")
        self.search_box.textChanged.connect(self._apply_search_filter)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["", "Game Name", "Location", "Remove"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("QTableWidget::item:focus { outline: none; }")
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_table_header_clicked)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 44)
        header.setSortIndicator(self._sort_column, self._sort_order)
        layout.addWidget(self.table)

        self.setCentralWidget(central)

        status = QStatusBar(self)
        self.progress = QProgressBar(self)
        self.progress.setMinimum(0)
        self.progress.setMaximum(1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)

    def on_add_mount_point(self) -> None:
        dialog = QFileDialog(self, "Add SteamLibrary directory")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_dirs = dialog.selectedFiles()
        if not selected_dirs:
            return
        selected = selected_dirs[0]

        self._scan_and_merge(Path(selected), update_ui=True, persist_mounts=True)

    def on_rescan(self) -> None:
        if not self.mount_points:
            QMessageBox.information(self, "Rescan", "No mount points added.")
            return

        current_mounts = [Path(p) for p in self.mount_points.keys()]
        self.mount_points.clear()
        self.games_by_key.clear()

        for mount in current_mounts:
            self._scan_and_merge(mount, update_ui=False, persist_mounts=False)
        self._refresh_table()

    def on_remove_selected(self) -> None:
        selected_games = self._checked_games()
        if not selected_games:
            QMessageBox.information(self, "Remove", "No games selected.")
            return
        self._confirm_and_remove(selected_games)

    def on_manage_locations(self) -> None:
        if not self.mount_points:
            QMessageBox.information(self, "Locations", "No known mount points.")
            return

        dialog = ManageLocationsDialog(sorted(self.mount_points.keys()), parent=None)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_paths = dialog.selected_mount_paths()
        if not selected_paths:
            return

        for mount_path in selected_paths:
            self._remove_mount_point(mount_path)

        self._save_mount_points()
        self._refresh_table()

    def _scan_and_merge(self, mount_path: Path, update_ui: bool, persist_mounts: bool) -> None:
        self._set_busy(True, f"Scanning {mount_path}...")
        QApplication.processEvents()

        try:
            mount, games = scan_mount_point(mount_path)
        except Exception as exc:
            LOGGER.exception("Scan failed for mount %s", mount_path)
            self._set_busy(False)
            QMessageBox.critical(self, "Scan Failed", f"Could not scan {mount_path}:\n{exc}")
            return

        self.mount_points[str(mount.path)] = mount
        if persist_mounts:
            self._save_mount_points()
        for game in games:
            self.games_by_key[game.dedupe_key] = game

        self._set_busy(False)
        if update_ui:
            self._refresh_table()

    def _checked_games(self) -> list[GameEntry]:
        selected: list[GameEntry] = []
        for row in range(self.table.rowCount()):
            checkbox_container = self.table.cellWidget(row, 0)
            if checkbox_container is None:
                continue
            checkbox = checkbox_container.findChild(QCheckBox)
            if checkbox is None or not checkbox.isChecked():
                continue

            key = checkbox.property("dedupe_key")
            if not key:
                continue

            game = self.games_by_key.get(key)
            if game:
                selected.append(game)

        return selected

    def _confirm_and_remove(self, games: list[GameEntry]) -> None:
        include_optional = self.optional_delete_checkbox.isChecked()
        dry_run = self.dry_run_checkbox.isChecked()
        steam_running_now = steam_is_running() and not self.allow_delete_while_steam_running

        targets: list[Path] = []
        for game in games:
            targets.extend(game.all_deletion_targets(include_optional=include_optional))

        unique_targets = sorted({str(path): path for path in targets}.values(), key=lambda p: str(p))

        dialog = ConfirmDeleteDialog(
            games=games,
            targets=unique_targets,
            steam_running_now=steam_running_now,
            dry_run=dry_run,
            parent=None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        progress = QProgressDialog("Deleting games...", "Cancel", 0, len(games), self)
        progress.setWindowTitle("Delete Progress")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        failed_messages: list[str] = []
        removed_keys: list[tuple[str, str]] = []

        for idx, game in enumerate(games, start=1):
            progress.setLabelText(f"Processing {game.name} ({idx}/{len(games)})")
            progress.setValue(idx - 1)
            QApplication.processEvents()

            result = delete_game(
                game=game,
                include_optional=include_optional,
                dry_run=dry_run,
            )

            if result.success:
                if not dry_run:
                    removed_keys.append(game.dedupe_key)
                continue

            game.state = GameState.ERROR
            game.error_message = "; ".join(f"{f.path}: {f.error}" for f in result.failures)
            for failure in result.failures:
                failed_messages.append(f"{game.name} -> {failure.path}: {failure.error}")

        progress.setValue(len(games))

        for key in removed_keys:
            self.games_by_key.pop(key, None)

        self._refresh_table()

        if dry_run:
            QMessageBox.information(self, "Dry Run", f"Dry run complete. {len(games)} game(s) previewed.")
            return

        if failed_messages:
            QMessageBox.warning(
                self,
                "Deletion Completed with Errors",
                "Some deletions failed. Retry may be required.\n\n" + "\n".join(failed_messages),
            )
        else:
            QMessageBox.information(self, "Deletion Complete", f"Removed {len(removed_keys)} game(s).")

    def _refresh_table(self) -> None:
        filter_tokens = [token for token in self.search_box.text().strip().lower().split() if token]
        selected_keys = self._checked_key_set()

        entries = list(self.games_by_key.values())
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        if self._sort_column == 1:
            entries.sort(key=lambda game: utf8_safe_text(game.name).lower(), reverse=reverse)
        elif self._sort_column == 2:
            entries.sort(key=lambda game: utf8_safe_text(game.library_root).lower(), reverse=reverse)

        self.table.setRowCount(0)

        for game in entries:
            if filter_tokens:
                name_lower = utf8_safe_text(game.name).lower()
                if not all(token in name_lower for token in filter_tokens):
                    continue
            row = self.table.rowCount()
            self.table.insertRow(row)

            checkbox = RowSelectCheckBox()
            checkbox.setChecked(game.dedupe_key in selected_keys)
            checkbox.setProperty("dedupe_key", game.dedupe_key)
            checkbox.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            checkbox.hovered.connect(lambda is_hovered, row=row: self._on_delete_button_hover(row, is_hovered))
            checkbox_container = QWidget()
            checkbox_container.setAutoFillBackground(False)
            checkbox_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            checkbox_container.setStyleSheet("background: transparent; background-color: transparent; border: none;")
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(6, 0, 6, 0)
            checkbox_layout.setSpacing(0)
            checkbox_layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 0, checkbox_container)

            name_item = QTableWidgetItem(utf8_safe_text(game.display_name))
            if game.state != GameState.OK:
                name_item.setToolTip(game.error_message or game.state.value)
                name_item.setForeground(QBrush(self._broken_name_color()))
            name_item.setData(Qt.ItemDataRole.UserRole, game.dedupe_key)
            self.table.setItem(row, 1, name_item)

            location_item = QTableWidgetItem(utf8_safe_text(game.library_root))
            self.table.setItem(row, 2, location_item)

            icon_path = Path(__file__).resolve().parent.parent / "icons" / "xfce-trash_full.svg"
            delete_button = TrashIconButton(icon_path)
            delete_button.setToolTip("Remove this game")
            delete_button.hovered.connect(lambda is_hovered, row=row: self._on_delete_button_hover(row, is_hovered))
            delete_button.clicked.connect(self._make_delete_single(game.dedupe_key))
            button_container = QWidget()
            button_container.setAutoFillBackground(False)
            button_container.setStyleSheet("background: transparent; background-color: transparent; border: none;")
            button_layout = QVBoxLayout(button_container)
            button_layout.setContentsMargins(0, 2, 0, 2)
            button_layout.setSpacing(0)
            button_layout.addWidget(delete_button, alignment=Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 3, button_container)
            self.table.setRowHeight(row, 56)
        self._update_status()

    def _on_table_header_clicked(self, column: int) -> None:
        if column not in (1, 2):
            return
        if self._sort_column == column:
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = column
            self._sort_order = Qt.SortOrder.AscendingOrder

        self.table.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)
        self._refresh_table()

    def _on_delete_button_hover(self, row: int, is_hovered: bool) -> None:
        if is_hovered:
            if 0 <= row < self.table.rowCount():
                self.table.selectRow(row)
            return
        self._sync_hover_selection_with_cursor()

    def _sync_hover_selection_with_cursor(self) -> None:
        viewport = self.table.viewport()
        local_pos = viewport.mapFromGlobal(QCursor.pos())
        if viewport.rect().contains(local_pos):
            index = self.table.indexAt(local_pos)
            if index.isValid():
                self.table.selectRow(index.row())
            else:
                self.table.clearSelection()
        else:
            self.table.clearSelection()

    def _broken_name_color(self) -> QColor:
        selected_theme = self.current_theme.lower()
        is_dark = selected_theme == "dark" or (selected_theme == "auto" and detect_system_dark_mode())
        if is_dark:
            return QColor("#d8b27a")
        return QColor("#7a4a00")

    def _checked_key_set(self) -> set[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        for row in range(self.table.rowCount()):
            checkbox_container = self.table.cellWidget(row, 0)
            if checkbox_container is None:
                continue
            checkbox = checkbox_container.findChild(QCheckBox)
            if checkbox is None or not checkbox.isChecked():
                continue
            key = checkbox.property("dedupe_key")
            if key:
                keys.add(key)
        return keys

    def _make_delete_single(self, key: tuple[str, str]):
        def _delete_single() -> None:
            game = self.games_by_key.get(key)
            if not game:
                return
            self._confirm_and_remove([game])

        return _delete_single

    def _apply_search_filter(self) -> None:
        self._refresh_table()

    def _on_theme_changed(self, text: str) -> None:
        if text not in {"Auto", "Light", "Dark"}:
            return
        self.current_theme = text
        apply_theme(text.lower())
        self._save_mount_points()

    def _remove_mount_point(self, mount_path: str) -> None:
        mount = self.mount_points.pop(mount_path, None)
        if mount is None:
            return

        library_roots = {str(lib.root_path.resolve()) for lib in mount.detected_libraries}
        keys_to_remove: list[tuple[str, str]] = []
        for key, game in self.games_by_key.items():
            if str(game.library_root.resolve()) in library_roots:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.games_by_key.pop(key, None)

    def _handle_startup_steam_warning(self) -> bool:
        if not steam_is_running():
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Steam Is Running")
        msg.setText("Steam appears to be running.")
        msg.setInformativeText(
            "You can quit now for safer cleanup, or continue and allow delete operations while Steam is running."
        )
        quit_button = msg.addButton("Quit Application", QMessageBox.ButtonRole.RejectRole)
        continue_button = msg.addButton("Continue Anyway", QMessageBox.ButtonRole.AcceptRole)
        msg.setDefaultButton(quit_button)
        msg.exec()

        if msg.clickedButton() is continue_button:
            self.allow_delete_while_steam_running = True
            return True
        return False

    def _save_mount_points(self) -> None:
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "mount_points": sorted(self.mount_points.keys()),
                "theme": self.current_theme,
            }
            self.mounts_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("Failed to save mount points to %s: %s", self.mounts_file, exc)

    def _load_saved_mount_points(self) -> None:
        if not self.mounts_file.exists():
            return

        try:
            payload = json.loads(self.mounts_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to load mount points from %s: %s", self.mounts_file, exc)
            return

        mounts = payload.get("mount_points", [])
        if not isinstance(mounts, list):
            return

        for mount_str in mounts:
            if not isinstance(mount_str, str):
                continue
            mount_path = Path(mount_str).expanduser()
            if not mount_path.exists():
                LOGGER.info("Skipping missing saved mount point: %s", mount_path)
                continue
            self._scan_and_merge(mount_path, update_ui=False, persist_mounts=False)

    def _load_saved_theme(self) -> None:
        if not self.mounts_file.exists():
            self.theme_box.setCurrentText(self.current_theme)
            return
        try:
            payload = json.loads(self.mounts_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.theme_box.setCurrentText(self.current_theme)
            return

        saved_theme = payload.get("theme", "Auto")
        if saved_theme not in {"Auto", "Light", "Dark"}:
            saved_theme = "Auto"
        self.current_theme = saved_theme
        self.theme_box.blockSignals(True)
        self.theme_box.setCurrentText(saved_theme)
        self.theme_box.blockSignals(False)

    def _update_status(self) -> None:
        libraries = sum(len(mp.detected_libraries) for mp in self.mount_points.values())
        games_count = len(self.games_by_key)
        self.statusBar().showMessage(f"{libraries} libraries, {games_count} games found")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
            self.statusBar().showMessage(message)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self._update_status()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.table.viewport():
            if event.type() == QtCore.QEvent.Type.MouseMove:
                index = self.table.indexAt(event.pos())
                if index.isValid():
                    self.table.selectRow(index.row())
                else:
                    self.table.clearSelection()
            elif event.type() == QtCore.QEvent.Type.Leave:
                self.table.clearSelection()
        return super().eventFilter(watched, event)
