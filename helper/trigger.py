"""Trigger 資料夾監控：每 2 秒讀取 trigger json，Stop 彈吐司、PostToolUse 伸腳"""

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
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

DEFAULT_TRIGGER_DIR = os.path.join(os.path.expanduser("~"), ".claude-triggers")
POLL_MS = 2000


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

    WIDTH, HEIGHT = 160, 90

    def __init__(self, text: str, land_pos: QPoint):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._text = text

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

        body = QRectF(20, 30, self.WIDTH - 40, self.HEIGHT - 40)
        path = QPainterPath()
        path.moveTo(body.left(), body.bottom())
        path.lineTo(body.left(), body.top() + 14)
        path.quadTo(body.left(), body.top(), body.left() + 14, body.top())
        path.lineTo(body.right() - 14, body.top())
        path.quadTo(body.right(), body.top(), body.right(), body.top() + 14)
        path.lineTo(body.right(), body.bottom())
        path.closeSubpath()
        p.setPen(QPen(QColor("#a8601c"), 2))
        p.setBrush(QColor("#e8b463"))
        p.drawPath(path)

        inner = body.adjusted(8, 8, -8, -4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f3d9a4"))
        p.drawRoundedRect(inner, 6, 6)

        p.setPen(QPen(QColor(255, 255, 255, 200), 2))
        p.setBrush(Qt.NoBrush)
        for dx in (-10, 10):
            x = body.center().x() + dx
            p.drawLine(int(x), int(body.top() - 6), int(x - 3), int(body.top() - 16))

        p.setPen(QColor("#3a2410"))
        font = p.font()
        font.setBold(True)
        font.setPointSize(9)
        p.setFont(font)
        p.drawText(inner, Qt.AlignCenter | Qt.TextWordWrap, self._text)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._anim.stop()
            self.close()


class Leg(QWidget):
    """PostToolUse 事件反應：獨立小視窗腳從主圓圈底部伸出，2 秒後自動縮回。"""

    LEG_W, LEG_H = 14, 28
    ANIM_MS = 150

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.LEG_W, self.LEG_H)
        self._anim = None
        self._hidden_pos = QPoint(0, 0)
        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.timeout.connect(self._retract)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4a6fa5"))
        p.drawRoundedRect(QRectF(2, 0, self.LEG_W - 4, self.LEG_H - 6), 4, 4)
        p.setBrush(QColor("#3a3a3a"))
        p.drawEllipse(QRectF(0, self.LEG_H - 10, self.LEG_W, 10))

    def pop(self, bubble_bottom_center: QPoint) -> None:
        self._hidden_pos = bubble_bottom_center - QPoint(self.LEG_W // 2, self.LEG_H)
        shown_pos = bubble_bottom_center - QPoint(self.LEG_W // 2, self.LEG_H - 18)

        self._retract_timer.stop()
        if self._anim:
            self._anim.stop()

        self.move(self._hidden_pos)
        self.show()
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setStartValue(self._hidden_pos)
        self._anim.setEndValue(shown_pos)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()
        self._retract_timer.start(2000)

    def _retract(self) -> None:
        if self._anim:
            self._anim.stop()
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(self._hidden_pos)
        self._anim.setEasingCurve(QEasingCurve.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()
