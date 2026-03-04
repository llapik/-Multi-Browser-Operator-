"""PyQt5 GUI for Multi-Browser Operator."""

import sys
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QGroupBox,
    QStatusBar,
    QMessageBox,
    QAbstractItemView,
)

from .engine import SyncEngine
from .window_manager import enumerate_windows, WindowInfo
from .config import load_config, save_config


def _create_icon(color: str = "#2196F3") -> QIcon:
    """Create a simple colored square icon."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 8, 8)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Arial", 28, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self._engine = SyncEngine()
        self._config = load_config()
        self._windows: list[WindowInfo] = []
        self._master_hwnd: Optional[int] = None

        self._init_ui()
        self._init_tray()
        self._init_timers()
        self._apply_config()

    # --- UI Setup ---

    def _init_ui(self):
        self.setWindowTitle("Multi-Browser Operator")
        self.setMinimumSize(700, 500)
        self.setWindowIcon(_create_icon())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Control bar ---
        ctrl_box = QGroupBox("Управление")
        ctrl_layout = QHBoxLayout(ctrl_box)

        self._btn_refresh = QPushButton("Обновить список окон")
        self._btn_refresh.clicked.connect(self._refresh_windows)
        ctrl_layout.addWidget(self._btn_refresh)

        self._btn_start = QPushButton("▶ Старт")
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #45a049; }"
        )
        self._btn_start.clicked.connect(self._toggle_sync)
        ctrl_layout.addWidget(self._btn_start)

        self._btn_pause = QPushButton("⏸ Пауза (F8)")
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._toggle_pause)
        ctrl_layout.addWidget(self._btn_pause)

        self._chk_scale = QCheckBox("Масштабировать координаты")
        self._chk_scale.setToolTip(
            "Пропорционально пересчитывать координаты при разных размерах окон"
        )
        self._chk_scale.toggled.connect(self._on_scale_changed)
        ctrl_layout.addWidget(self._chk_scale)

        layout.addWidget(ctrl_box)

        # --- Master window display ---
        master_box = QGroupBox("Ведущее окно (Master)")
        master_layout = QHBoxLayout(master_box)
        self._lbl_master = QLabel("Не выбрано")
        self._lbl_master.setStyleSheet("font-weight: bold; color: #1565C0;")
        master_layout.addWidget(self._lbl_master, 1)

        self._btn_set_master = QPushButton("Назначить выбранное")
        self._btn_set_master.clicked.connect(self._set_master_from_selection)
        master_layout.addWidget(self._btn_set_master)

        layout.addWidget(master_box)

        # --- Window table ---
        table_box = QGroupBox("Окна (отметьте ведомые / Slaves)")
        table_layout = QVBoxLayout(table_box)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Ведомое", "HWND", "Заголовок окна", "Класс"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        table_layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._btn_check_all = QPushButton("Выбрать все")
        self._btn_check_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_row.addWidget(self._btn_check_all)

        self._btn_uncheck_all = QPushButton("Снять все")
        self._btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))
        btn_row.addWidget(self._btn_uncheck_all)

        btn_row.addStretch()
        table_layout.addLayout(btn_row)

        layout.addWidget(table_box, 1)

        # --- Status bar ---
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._lbl_status = QLabel("Готово")
        self._lbl_events = QLabel("Событий: 0")
        self._statusbar.addWidget(self._lbl_status, 1)
        self._statusbar.addPermanentWidget(self._lbl_events)

        # Initial refresh
        self._refresh_windows()

    def _init_tray(self):
        self._tray = QSystemTrayIcon(_create_icon(), self)
        menu = QMenu()
        act_show = QAction("Показать", self)
        act_show.triggered.connect(self._show_from_tray)
        menu.addAction(act_show)

        self._tray_pause = QAction("Пауза", self)
        self._tray_pause.triggered.connect(self._toggle_pause)
        menu.addAction(self._tray_pause)

        menu.addSeparator()
        act_quit = QAction("Выход", self)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _init_timers(self):
        # Status update timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_status)
        self._timer.start(500)

    def _apply_config(self):
        self._chk_scale.setChecked(self._config.get("scale_coordinates", False))

    # --- Actions ---

    def _refresh_windows(self):
        self._windows = enumerate_windows()
        self._table.setRowCount(0)
        try:
            own_hwnd = int(self.winId())
        except Exception:
            own_hwnd = 0

        for win in self._windows:
            # Skip our own window
            if win.hwnd == own_hwnd:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Checkbox for slave selection — store the QCheckBox directly as
            # a property on the container widget to avoid fragile findChild()
            chk = QCheckBox()
            chk_widget = QWidget()
            chk_widget.setProperty("chk", chk)
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 0, chk_widget)

            # HWND
            hwnd_item = QTableWidgetItem(f"0x{win.hwnd:08X}")
            hwnd_item.setFlags(hwnd_item.flags() & ~Qt.ItemIsEditable)
            hwnd_item.setData(Qt.UserRole, win.hwnd)
            self._table.setItem(row, 1, hwnd_item)

            # Title
            title_item = QTableWidgetItem(win.title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 2, title_item)

            # Class
            cls_item = QTableWidgetItem(win.class_name)
            cls_item.setFlags(cls_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 3, cls_item)

        self._statusbar.showMessage(f"Найдено окон: {self._table.rowCount()}", 3000)

    def _set_master_from_selection(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Выбор", "Выберите строку в таблице для назначения ведущего окна.")
            return
        row = rows[0].row()
        hwnd_item = self._table.item(row, 1)
        hwnd = hwnd_item.data(Qt.UserRole)
        title = self._table.item(row, 2).text()
        self._master_hwnd = hwnd
        self._engine.set_master(hwnd)
        self._lbl_master.setText(f"0x{hwnd:08X} — {title}")

        # Uncheck the master from slaves if checked
        chk_widget = self._table.cellWidget(row, 0)
        if chk_widget:
            chk = chk_widget.property("chk")
            if chk:
                chk.setChecked(False)

    def _get_checked_slaves(self) -> list:
        slaves = []
        for row in range(self._table.rowCount()):
            chk_widget = self._table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.property("chk")
                if chk and chk.isChecked():
                    hwnd = self._table.item(row, 1).data(Qt.UserRole)
                    if hwnd != self._master_hwnd:
                        slaves.append(hwnd)
        return slaves

    def _set_all_checked(self, checked: bool):
        for row in range(self._table.rowCount()):
            chk_widget = self._table.cellWidget(row, 0)
            if chk_widget:
                chk = chk_widget.property("chk")
                if chk:
                    hwnd = self._table.item(row, 1).data(Qt.UserRole)
                    if hwnd != self._master_hwnd or not checked:
                        chk.setChecked(checked)

    def _toggle_sync(self):
        if self._engine.is_active:
            self._engine.stop()
            self._btn_start.setText("▶ Старт")
            self._btn_start.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; "
                "font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #45a049; }"
            )
            self._btn_pause.setEnabled(False)
            self._btn_refresh.setEnabled(True)
            self._lbl_status.setText("Остановлено")
        else:
            if self._master_hwnd is None:
                QMessageBox.warning(self, "Ошибка", "Сначала назначьте ведущее окно (Master).")
                return
            slaves = self._get_checked_slaves()
            if not slaves:
                QMessageBox.warning(self, "Ошибка", "Отметьте хотя бы одно ведомое окно (Slave).")
                return
            self._engine.set_slaves(slaves)
            self._engine.start()
            self._btn_start.setText("⏹ Стоп")
            self._btn_start.setStyleSheet(
                "QPushButton { background-color: #f44336; color: white; "
                "font-weight: bold; padding: 6px 16px; border-radius: 4px; }"
                "QPushButton:hover { background-color: #d32f2f; }"
            )
            self._btn_pause.setEnabled(True)
            self._btn_refresh.setEnabled(False)
            self._lbl_status.setText(
                f"Синхронизация: master → {len(slaves)} slave(s)"
            )

    def _toggle_pause(self):
        if not self._engine.is_active:
            return
        self._engine.toggle_pause()
        if self._engine.is_paused:
            self._btn_pause.setText("▶ Продолжить (F8)")
            self._lbl_status.setText("Пауза")
            self._tray_pause.setText("Продолжить")
        else:
            self._btn_pause.setText("⏸ Пауза (F8)")
            slaves = len(self._engine.get_slaves())
            self._lbl_status.setText(f"Синхронизация: master → {slaves} slave(s)")
            self._tray_pause.setText("Пауза")

    def _on_scale_changed(self, checked: bool):
        self._engine.scale_coords = checked
        self._config["scale_coordinates"] = checked
        save_config(self._config)

    def _update_status(self):
        self._lbl_events.setText(f"Событий: {self._engine.events_sent}")

    # --- Tray ---

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def closeEvent(self, event):
        if self._config.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Multi-Browser Operator",
                "Приложение свернуто в трей. Двойной клик для открытия.",
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            self._quit()

    def _quit(self):
        self._engine.stop()
        save_config(self._config)
        self._tray.hide()
        QApplication.quit()

    # --- Keyboard shortcut ---

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F8:
            self._toggle_pause()
        else:
            super().keyPressEvent(event)


def run_app():
    """Entry point for the GUI application."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Multi-Browser Operator")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
