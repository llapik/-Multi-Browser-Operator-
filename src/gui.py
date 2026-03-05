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
    QComboBox,
    QSpinBox,
    QLineEdit,
)

from .engine import SyncEngine
from .window_manager import enumerate_windows, WindowInfo
from .config import load_config, save_config
from .browser_launcher import BrowserLauncher


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
        self._launcher = BrowserLauncher()
        self._config = load_config()
        self._windows: list = []
        self._master_hwnd: Optional[int] = None
        self._last_dead_removed: int = 0  # tracks engine's dead-slave counter

        self._init_ui()
        self._init_tray()
        self._init_timers()
        self._apply_config()

    # --- UI Setup ---

    def _init_ui(self):
        self.setWindowTitle("Multi-Browser Operator")
        self.setMinimumSize(760, 580)
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

        # --- Browser launcher ---
        layout.addWidget(self._build_launcher_box())

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

    def _build_launcher_box(self) -> QGroupBox:
        """Build the browser launcher group box."""
        box = QGroupBox("Открыть браузеры (инкогнито, независимые сессии)")
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        outer = QVBoxLayout(box)
        outer.addLayout(row1)
        outer.addLayout(row2)

        # --- Row 1: browser, count, URL ---
        row1.addWidget(QLabel("Браузер:"))
        self._cmb_browser = QComboBox()
        self._cmb_browser.setMinimumWidth(160)
        browsers = BrowserLauncher.available_browsers()
        if browsers:
            self._cmb_browser.addItems(browsers)
        else:
            self._cmb_browser.addItem("Браузеры не найдены")
            self._cmb_browser.setEnabled(False)
        row1.addWidget(self._cmb_browser)

        row1.addWidget(QLabel("Кол-во:"))
        self._spn_count = QSpinBox()
        self._spn_count.setRange(1, 50)
        self._spn_count.setValue(5)
        self._spn_count.setFixedWidth(60)
        row1.addWidget(self._spn_count)

        row1.addWidget(QLabel("URL:"))
        self._txt_url = QLineEdit()
        self._txt_url.setPlaceholderText("https://... (необязательно)")
        row1.addWidget(self._txt_url, 1)

        # --- Row 2: buttons and status ---
        self._btn_launch = QPushButton("Открыть")
        self._btn_launch.setToolTip(
            "Запустить N браузеров в режиме инкогнито.\n"
            "Каждый получит отдельную папку профиля — куки и пароли не пересекаются."
        )
        self._btn_launch.setStyleSheet(
            "QPushButton { background-color: #1565C0; color: white; "
            "font-weight: bold; padding: 5px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1976D2; }"
            "QPushButton:disabled { background-color: #90A4AE; }"
        )
        self._btn_launch.clicked.connect(self._launch_browsers)
        if not browsers:
            self._btn_launch.setEnabled(False)
        row2.addWidget(self._btn_launch)

        self._btn_close_browsers = QPushButton("Закрыть все браузеры")
        self._btn_close_browsers.setEnabled(False)
        self._btn_close_browsers.clicked.connect(self._close_browsers)
        row2.addWidget(self._btn_close_browsers)

        self._chk_clean_sessions = QCheckBox("Очистить сессии при закрытии")
        self._chk_clean_sessions.setToolTip(
            "Удалить папки профилей при нажатии «Закрыть все».\n"
            "Если снято — данные сохраняются для следующего запуска."
        )
        row2.addWidget(self._chk_clean_sessions)

        row2.addStretch()

        self._lbl_launcher = QLabel("")
        self._lbl_launcher.setStyleSheet("color: #555;")
        row2.addWidget(self._lbl_launcher)

        return box

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
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_status)
        self._timer.start(500)

    def _apply_config(self):
        self._chk_scale.setChecked(self._config.get("scale_coordinates", False))
        self._chk_clean_sessions.setChecked(
            self._config.get("clean_sessions_on_close", False)
        )

    # --- Actions ---

    def _refresh_windows(self):
        self._windows = enumerate_windows()
        self._table.setRowCount(0)
        try:
            own_hwnd = int(self.winId())
        except Exception:
            own_hwnd = 0

        for win in self._windows:
            if win.hwnd == own_hwnd:
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Checkbox for slave selection — stored as a Qt property to avoid
            # fragile findChild() hierarchy lookups
            chk = QCheckBox()
            chk_widget = QWidget()
            chk_widget.setProperty("chk", chk)
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 0, chk_widget)

            hwnd_item = QTableWidgetItem(f"0x{win.hwnd:08X}")
            hwnd_item.setFlags(hwnd_item.flags() & ~Qt.ItemIsEditable)
            hwnd_item.setData(Qt.UserRole, win.hwnd)
            self._table.setItem(row, 1, hwnd_item)

            title_item = QTableWidgetItem(win.title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 2, title_item)

            cls_item = QTableWidgetItem(win.class_name)
            cls_item.setFlags(cls_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 3, cls_item)

        self._statusbar.showMessage(f"Найдено окон: {self._table.rowCount()}", 3000)

    def _set_master_from_selection(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Выбор",
                "Выберите строку в таблице для назначения ведущего окна.")
            return
        row = rows[0].row()
        hwnd = self._table.item(row, 1).data(Qt.UserRole)
        title = self._table.item(row, 2).text()
        self._master_hwnd = hwnd
        self._engine.set_master(hwnd)
        self._lbl_master.setText(f"0x{hwnd:08X} — {title}")

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
            self._lbl_status.setStyleSheet("")
            self._last_dead_removed = 0
        else:
            if self._master_hwnd is None:
                QMessageBox.warning(self, "Ошибка",
                    "Сначала назначьте ведущее окно (Master).")
                return
            slaves = self._get_checked_slaves()
            if not slaves:
                QMessageBox.warning(self, "Ошибка",
                    "Отметьте хотя бы одно ведомое окно (Slave).")
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

    # --- Browser launcher actions ---

    def _launch_browsers(self):
        browser = self._cmb_browser.currentText()
        count = self._spn_count.value()
        url = self._txt_url.text().strip()

        launched = self._launcher.launch(browser, count, url)
        if launched == 0:
            QMessageBox.warning(self, "Ошибка",
                f"Не удалось запустить «{browser}».\n"
                "Проверьте, установлен ли браузер.")
            return

        total = self._launcher.launched_count
        self._lbl_launcher.setText(f"Активно: {total}")
        self._btn_close_browsers.setEnabled(True)

        # Refresh window list after browsers have had time to open
        QTimer.singleShot(2500, self._refresh_windows)

    def _close_browsers(self):
        clean = self._chk_clean_sessions.isChecked()
        self._launcher.close_all()
        if clean:
            self._launcher.cleanup_sessions(remove_dirs=True)
        self._lbl_launcher.setText("Закрыто")
        self._btn_close_browsers.setEnabled(False)
        self._config["clean_sessions_on_close"] = clean
        save_config(self._config)

    # --- Status ---

    def _update_status(self):
        self._lbl_events.setText(f"Событий: {self._engine.events_sent}")

        if not self._engine.is_active:
            return

        # Warn if the master window was destroyed while sync is running
        if self._master_hwnd is not None and not self._engine.is_master_valid():
            self._lbl_status.setText("⚠ Ведущее окно закрыто! Остановите синхронизацию.")
            self._lbl_status.setStyleSheet("color: #c62828; font-weight: bold;")
            return

        # Warn when dead slave HWNDs were auto-purged
        dead = self._engine.dead_removed
        if dead != self._last_dead_removed:
            newly_purged = dead - self._last_dead_removed
            self._last_dead_removed = dead
            remaining = self._engine.slave_count()
            self._statusbar.showMessage(
                f"⚠ Удалено {newly_purged} закрытых slave-окон "
                f"(осталось {remaining}). Нажмите «Обновить» для повторного выбора.",
                6000,
            )
            # If all slaves are gone, stop automatically
            if remaining == 0:
                self._toggle_sync()
                self._lbl_status.setStyleSheet("")

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
        self._launcher.close_all()
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
