"""Trigger 資料夾監控：每 2 秒讀取 trigger json，Stop 彈吐司、PostToolUse 播放 GIF"""

import json
import os
import shutil

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QMovie, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

DEFAULT_TRIGGER_DIR = os.path.join(os.path.expanduser("~"), ".claude-triggers")
POLL_MS = 2000
TOAST_IMAGE = os.path.join(os.path.dirname(__file__), "assest", "toast.png")
TOOLUSE_GIF = os.path.join(os.path.dirname(__file__), "assest", "hammer-break (1).gif")


class TriggerWatcher(QObject):
    """輪詢 trigger 資料夾（每 2 秒），依 event 欄位分派訊號；處理過的檔案搬到 processed/。"""

    stopTriggered = Signal(dict)
    postToolUseTriggered = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._dir = DEFAULT_TRIGGER_DIR

    def configure(self, enabled: bool, trigger_dir: str) -> None:
        self._dir = trigger_dir or DEFAULT_TRIGGER_DIR
        if enabled:
            self._timer.start()
            self._poll()
        else:
            self._timer.stop()

    def _poll(self) -> None:
        if not os.path.isdir(self._dir):
            return
        for name in sorted(os.listdir(self._dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self._dir, name)
            if os.path.isfile(path):
                self._process(path)

    def _process(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        event = data.get("event")
        if event == "Stop":
            self.stopTriggered.emit(data)
        elif event == "PostToolUse":
            self.postToolUseTriggered.emit(data)

        processed_dir = os.path.join(self._dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)
        shutil.move(path, os.path.join(processed_dir, os.path.basename(path)))


class Toast(QWidget):
    """Stop 事件通知：吐司從主圓圈位置彈出，OutBounce 呈現「彈出→落地」的彈跳感，點擊消失。"""

    WIDTH, HEIGHT = 140, 130

    def __init__(self, text: str, land_pos: QPoint):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._text = text
        self._pixmap = QPixmap(TOAST_IMAGE)

        start_pos = QPoint(land_pos.x(), land_pos.y() + 60)
        self.move(start_pos)
        self.show()

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(650)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(land_pos)
        self._anim.setEasingCurve(QEasingCurve.OutBounce)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.WIDTH, self.HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            p.drawPixmap(
                (self.WIDTH - scaled.width()) // 2,
                (self.HEIGHT - scaled.height()) // 2,
                scaled,
            )

        # 文字疊在吐司內部下半部，加白色描邊確保在焦黃底色上仍清楚可讀
        text_rect = QRectF(10, self.HEIGHT * 0.15, self.WIDTH - 20, self.HEIGHT * 0.45)
        font = p.font()
        font.setBold(True)
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(text_rect.translated(dx, dy), Qt.AlignCenter | Qt.TextWordWrap, self._text)
        p.setPen(QColor("#3a2410"))
        p.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self._text)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._anim.stop()
            self.close()


class ToolUseEffect(QWidget):
    """PostToolUse 事件反應：主圓圈左下角播放 GIF 動畫，2 秒後自動隱藏。"""

    WIDTH, HEIGHT = 120, 120
    OFFSET_X, OFFSET_Y = -100, -150  # 相對主圓圈左下角的位移：負值往左／往上

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._movie = QMovie(TOOLUSE_GIF)
        self._movie.frameChanged.connect(lambda _: self.update())

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_timeout)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pm = self._movie.currentPixmap()
        if not pm.isNull():
            scaled = pm.scaled(
                self.WIDTH, self.HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            p.drawPixmap(
                (self.WIDTH - scaled.width()) // 2,
                (self.HEIGHT - scaled.height()) // 2,
                scaled,
            )

    def play(self, bubble_bottom_left: QPoint) -> None:
        self.move(
            bubble_bottom_left.x() + self.OFFSET_X,
            bubble_bottom_left.y() + self.OFFSET_Y,
        )
        self._hide_timer.stop()
        self._movie.stop()
        self._movie.start()
        self.show()
        self._hide_timer.start(2000)

    def _on_timeout(self) -> None:
        self._movie.stop()
        self.hide()
