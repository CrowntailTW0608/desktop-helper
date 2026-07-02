"""Desktop Helper 進入點：主圓圈、衛星、用量監控、系統匣"""

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from helper import config
from helper.bubble import Bubble
from helper.satellite import SatelliteRing
from helper.settings_ui import SettingsDialog
from helper.usage import UsageMonitor


def _tray_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#4a6fa5"))
    p.drawEllipse(2, 2, 28, 28)
    p.end()
    return QIcon(pm)


class HelperApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = config.load()
        self.settings = None

        self.bubble = Bubble()
        self._apply_gif_cfg()
        self._restore_position()

        self.ring = SatelliteRing()
        self.ring.set_links(self.cfg["links"])
        self.ring.settingsRequested.connect(self.open_settings)
        self.bubble.clicked.connect(
            lambda: self.ring.toggle(self.bubble.geometry().center())
        )
        self.bubble.moved.connect(self._save_position)
        self.bubble.dragMoved.connect(
            lambda: self.ring.reposition(self.bubble.geometry().center())
        )
        # 點擊小幫手以外的區域（切到其他視窗）時收合衛星（FR-13）
        app.applicationStateChanged.connect(self._on_app_state)

        self.monitor = UsageMonitor()
        self.monitor.updated.connect(self.bubble.set_usage)
        self.monitor.failed.connect(self.bubble.set_usage_error)
        self._apply_usage_cfg()

        self._build_tray()
        self.bubble.show()

    # ── 位置記憶（FR-6）──────────────────────────────────────────────────

    def _restore_position(self):
        pos = self.cfg["position"]
        point = QPoint(int(pos.get("x", 100)), int(pos.get("y", 100)))
        screen = self.app.screenAt(point) or self.app.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(point.x(), area.left()), area.right() - self.bubble.width())
        y = min(max(point.y(), area.top()), area.bottom() - self.bubble.height())
        self.bubble.move(x, y)

    def _save_position(self, x: int, y: int):
        self.cfg["position"] = {"x": x, "y": y}
        config.save(self.cfg)

    def _on_app_state(self, state):
        if state != Qt.ApplicationActive:
            self.ring.collapse()

    # ── 設定 ─────────────────────────────────────────────────────────────

    def open_settings(self):
        if self.settings is None:
            self.settings = SettingsDialog(self.cfg)
            self.settings.gifChanged.connect(self._apply_gif_cfg)
            self.settings.linksChanged.connect(
                lambda: self.ring.set_links(self.cfg["links"])
            )
            self.settings.usageChanged.connect(self._apply_usage_cfg)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _apply_gif_cfg(self):
        self.bubble.set_gif(self.cfg["gif_path"], self.cfg["gif_interval"])

    def _apply_usage_cfg(self):
        cu = self.cfg["claude_usage"]
        enabled = bool(cu["enabled"] and cu["session_key"] and cu["org_id"])
        self.bubble.set_usage_enabled(enabled)
        self.monitor.configure(enabled, cu["session_key"], cu["org_id"])

    # ── 系統匣（FR-21～23）───────────────────────────────────────────────

    def _build_tray(self):
        self.tray = QSystemTrayIcon(_tray_icon())
        self.tray.setToolTip("Desktop Helper")
        menu = QMenu()
        toggle = QAction("顯示/隱藏小幫手", menu)
        toggle.triggered.connect(self._toggle_bubble)
        settings = QAction("設定…", menu)
        settings.triggered.connect(self.open_settings)
        quit_action = QAction("結束程式", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(toggle)
        menu.addAction(settings)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _toggle_bubble(self):
        if self.bubble.isVisible():
            self.ring.collapse(animated=False)
            self.bubble.hide()
        else:
            self.bubble.show()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    helper = HelperApp(app)  # noqa: F841 — 保持存活直到事件迴圈結束
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
