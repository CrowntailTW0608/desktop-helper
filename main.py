"""Desktop Helper 進入點：主圓圈、衛星、用量監控、系統匣"""

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from helper import config
from helper.bubble import MODE_LIVE2D, Bubble
from helper.icon import app_icon
from helper.satellite import SatelliteRing
from helper.settings_ui import SettingsDialog
from helper.trigger import (
    NotificationEffect,
    ThinkingEffect,
    Toast,
    ToolUseEffect,
    TriggerWatcher,
)
from helper.usage import UsageMonitor


class HelperApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = config.load()
        self.settings = None

        self.bubble = Bubble()
        self._apply_gif_cfg()
        self.bubble.set_live2d_character(self.cfg["live2d_character"])
        self.bubble.set_display_mode(self.cfg["display_mode"])
        self._restore_position()

        self.ring = SatelliteRing()
        self.ring.set_links(self.cfg["links"])
        self.ring.settingsRequested.connect(self.open_settings)
        self.bubble.clicked.connect(self._on_bubble_clicked)
        self.bubble.moved.connect(self._save_position)
        self._last_bubble_pos = self.bubble.pos()
        self.bubble.dragMoved.connect(self._on_bubble_dragged)
        # 點擊小幫手以外的區域（切到其他視窗）時收合衛星（FR-13）
        app.applicationStateChanged.connect(self._on_app_state)

        self.monitor = UsageMonitor()
        self.monitor.updated.connect(self.bubble.set_usage)
        self.monitor.failed.connect(self.bubble.set_usage_error)
        self.monitor.incidentsUpdated.connect(self.bubble.set_incidents)
        self._apply_usage_cfg()

        self.trigger_watcher = TriggerWatcher()
        self.trigger_watcher.stopTriggered.connect(self._on_stop_trigger)
        self.trigger_watcher.preToolUseTriggered.connect(self._on_pretooluse_trigger)
        self.trigger_watcher.postToolUseTriggered.connect(self._on_posttooluse_trigger)
        self.trigger_watcher.notificationTriggered.connect(self._on_notification_trigger)
        self.trigger_watcher.userPromptSubmitTriggered.connect(self._on_userpromptsubmit_trigger)
        self._toasts = []
        self._tooluse_effect = None
        self._notification_effect = None
        self._thinking_effect = None
        self._apply_trigger_cfg()

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

    # Live2D 弧形錨點的垂直微調：正值往下（更貼近角色頭部）、負值往上（離角色更遠）。
    LIVE2D_ARC_TOP_OFFSET = 90

    def _satellite_anchor(self) -> tuple[QPoint, str]:
        """Live2D 模式：以角色上緣為錨點展開弧形（像彩虹）；GIF 模式：以主圓圈中心環繞一整圈。"""
        rect = self.bubble.geometry()
        if self._live2d_mode():
            anchor_y = rect.top() + self.LIVE2D_ARC_TOP_OFFSET
            return QPoint(rect.center().x(), anchor_y), "arc"
        return rect.center(), "circle"

    def _on_bubble_dragged(self):
        """主圓圈被拖曳時，衛星選單、吐司、GIF 疊圖都跟著相對移動。"""
        new_pos = self.bubble.pos()
        delta = new_pos - self._last_bubble_pos
        self._last_bubble_pos = new_pos
        self.ring.reposition(self._satellite_anchor()[0])
        for toast in self._toasts:
            toast.shift(delta)
        if self._tooluse_effect and self._tooluse_effect.isVisible():
            self._tooluse_effect.move(self._tooluse_effect.pos() + delta)
        if self._notification_effect and self._notification_effect.isVisible():
            self._notification_effect.move(self._notification_effect.pos() + delta)
        if self._thinking_effect and self._thinking_effect.isVisible():
            self._thinking_effect.shift(delta)

    def _on_app_state(self, state):
        if state != Qt.ApplicationActive:
            self.ring.collapse()

    # ── 設定 ─────────────────────────────────────────────────────────────

    def open_settings(self):
        if self.settings is None:
            self.settings = SettingsDialog(self.cfg)
            self.settings.gifChanged.connect(self._apply_gif_cfg)
            self.settings.displayModeChanged.connect(self._apply_display_mode_cfg)
            self.settings.live2dCharacterChanged.connect(self._apply_live2d_character_cfg)
            self.settings.linksChanged.connect(
                lambda: self.ring.set_links(self.cfg["links"])
            )
            self.settings.usageChanged.connect(self._apply_usage_cfg)
            self.settings.triggerChanged.connect(self._apply_trigger_cfg)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def _apply_gif_cfg(self):
        self.bubble.set_gif(self.cfg["gif_path"], self.cfg["gif_interval"])

    def _apply_display_mode_cfg(self):
        self.bubble.set_display_mode(self.cfg["display_mode"])
        self.ring.reposition(self._satellite_anchor()[0])

    def _apply_live2d_character_cfg(self):
        self.bubble.set_live2d_character(self.cfg["live2d_character"])

    def _apply_usage_cfg(self):
        cu = self.cfg["claude_usage"]
        enabled = bool(cu["enabled"] and cu["session_key"] and cu["org_id"])
        self.bubble.set_usage_enabled(enabled)
        self.monitor.configure(enabled, cu["session_key"], cu["org_id"])

    def _apply_trigger_cfg(self):
        tr = self.cfg["trigger"]
        self.trigger_watcher.configure(tr["enabled"], tr["dir"])

    # ── Trigger 反應（Stop 彈吐司 / PostToolUse 播放 GIF）───────────────────

    def _live2d_mode(self) -> bool:
        return self.cfg["display_mode"] == MODE_LIVE2D

    def _on_bubble_clicked(self):
        anchor, mode = self._satellite_anchor()
        self.ring.toggle(anchor, mode)
        if self._live2d_mode():
            self.bubble.live2d_react("Clicked")

    def _on_stop_trigger(self, data: dict):
        if self._live2d_mode():
            self.bubble.live2d_react("Stop")
            return
        center = self.bubble.geometry().center()
        land_pos = QPoint(
            center.x() - Toast.WIDTH // 2, self.bubble.y() - Toast.HEIGHT + 50
        )
        project = data.get("project", "unknown")
        toast = Toast(f"{project}\n已完成", land_pos)
        toast.destroyed.connect(lambda: self._toasts.remove(toast) if toast in self._toasts else None)
        self._toasts.append(toast)
        self.bubble.raise_()

    def _on_pretooluse_trigger(self, _data: dict):
        if self._live2d_mode():
            self.bubble.live2d_react("PreToolUse")
            return
        if self._tooluse_effect is None:
            self._tooluse_effect = ToolUseEffect()
        rect = self.bubble.geometry()
        bottom_left = QPoint(rect.left(), rect.bottom())
        self._tooluse_effect.open(bottom_left)
        self.bubble.raise_()

    def _on_posttooluse_trigger(self, _data: dict):
        if self._live2d_mode():
            self.bubble.live2d_react("PostToolUse")
            return
        if self._tooluse_effect is not None:
            self._tooluse_effect.close_gif()

    def _on_userpromptsubmit_trigger(self, _data: dict):
        if self._live2d_mode():
            self.bubble.live2d_react("UserPromptSubmit")
            return
        if self._thinking_effect is None:
            self._thinking_effect = ThinkingEffect()
        rect = self.bubble.geometry()
        top_center = QPoint(rect.center().x(), rect.top())
        self._thinking_effect.open(top_center)
        self.bubble.raise_()

    def _on_notification_trigger(self, _data: dict):
        if self._notification_effect is None:
            self._notification_effect = NotificationEffect()
        self._notification_effect.play(self.bubble.geometry().center())
        self.bubble.raise_()

    # ── 系統匣（FR-21～23）───────────────────────────────────────────────

    def _build_tray(self):
        self.tray = QSystemTrayIcon(app_icon())
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
