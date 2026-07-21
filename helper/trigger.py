"""Trigger 資料夾監控：每 2 秒讀取 trigger json，Stop 彈吐司、PostToolUse 播放 GIF"""

import json
import os

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
from PySide6.QtGui import QColor, QFontMetrics, QMovie, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

DEFAULT_TRIGGER_DIR = os.path.join(os.path.expanduser("~"), ".claude-triggers")
POLL_MS = 2000
TOAST_IMAGE = os.path.join(os.path.dirname(__file__), "assest", "toast.png")
TOOLUSE_GIF = os.path.join(os.path.dirname(__file__), "assest", "hammer-break (1).gif")
NOTIFICATION_GIF = os.path.join(os.path.dirname(__file__), "assest", "nut.gif")
THINKING_GIF = os.path.join(os.path.dirname(__file__), "assest", "emm-thinking.gif")
SMOKE_GIF = os.path.join(os.path.dirname(__file__), "assest", "smoke.gif")


class TriggerWatcher(QObject):
    """輪詢 trigger 資料夾（每 2 秒），依 event 欄位分派訊號；處理過的檔案搬到 processed/。"""

    stopTriggered = Signal(dict)
    preToolUseTriggered = Signal(dict)
    postToolUseTriggered = Signal(dict)
    notificationTriggered = Signal(dict)
    userPromptSubmitTriggered = Signal(dict)
    preCompactTriggered = Signal(dict)

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
        paths = [
            os.path.join(self._dir, name)
            for name in os.listdir(self._dir)
            if name.endswith(".json")
        ]
        paths = [p for p in paths if os.path.isfile(p)]
        # 檔名時間戳只到秒，PreToolUse/PostToolUse 若落在同一秒會被字串排序打亂順序
        # （"PostToolUse" 字母序排在 "PreToolUse" 前面），改用實際修改時間排序才是真正的寫入順序。
        for path in sorted(paths, key=os.path.getmtime):
            self._process(path)

    def _process(self, path: str) -> None:
        processed_dir = os.path.join(self._dir, "processed")
        try:
            os.makedirs(processed_dir, exist_ok=True)
        except OSError:
            return
        claimed_path = os.path.join(processed_dir, os.path.basename(path))
        try:
            # 先搬（os.replace 是原子操作）才讀，確保同一個 trigger 檔案只會被一支行程處理到；
            # 若背景不小心開了兩支 main.py（例如 autostart 常駐＋手動測試）同時監控同個資料夾，
            # 搬移失敗的那一支就直接跳過，不會兩邊都各自反應同一個事件。
            os.replace(path, claimed_path)
        except OSError:
            return

        try:
            with open(claimed_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        event = data.get("event")
        if event == "Stop":
            self.stopTriggered.emit(data)
        elif event == "PreToolUse":
            self.preToolUseTriggered.emit(data)
        elif event == "PostToolUse":
            self.postToolUseTriggered.emit(data)
        elif event == "Notification":
            self.notificationTriggered.emit(data)
        elif event == "UserPromptSubmit":
            self.userPromptSubmitTriggered.emit(data)
        elif event == "PreCompact":
            self.preCompactTriggered.emit(data)


class Toast(QWidget):
    """Stop 事件通知：吐司從主圓圈位置彈出，OutBounce 呈現「彈出→落地」的彈跳感，點擊消失。"""

    WIDTH, HEIGHT = 140, 130
    SMOKE_WIDTH, SMOKE_HEIGHT = 80, 60  # 疊在吐司正上方的冒煙區域

    def __init__(self, text: str, land_pos: QPoint):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 視窗整體往上多留 SMOKE_HEIGHT 空間畫煙，吐司本體維持原尺寸與錨點
        self.setFixedSize(self.WIDTH, self.HEIGHT + self.SMOKE_HEIGHT)
        self._text = text
        self._pixmap = QPixmap(TOAST_IMAGE)

        self._smoke_movie = QMovie(SMOKE_GIF)
        self._smoke_movie.frameChanged.connect(lambda _: self.update())
        self._smoke_movie.start()

        start_pos = QPoint(land_pos.x(), land_pos.y() + 60 - self.SMOKE_HEIGHT)
        land_frame_pos = QPoint(land_pos.x(), land_pos.y() - self.SMOKE_HEIGHT)
        self.move(start_pos)
        self.show()

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(650)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(land_frame_pos)
        self._anim.setEasingCurve(QEasingCurve.OutBounce)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        smoke_pm = self._smoke_movie.currentPixmap()
        if not smoke_pm.isNull():
            scaled_smoke = smoke_pm.scaled(
                self.SMOKE_WIDTH, self.SMOKE_HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            p.drawPixmap((self.WIDTH - scaled_smoke.width()) // 2, 0, scaled_smoke)

        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.WIDTH, self.HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            p.drawPixmap(
                (self.WIDTH - scaled.width()) // 2,
                self.SMOKE_HEIGHT + (self.HEIGHT - scaled.height()) // 2,
                scaled,
            )

        # 文字疊在吐司內部下半部，加白色描邊確保在焦黃底色上仍清楚可讀
        text_rect = QRectF(
            10, self.SMOKE_HEIGHT + self.HEIGHT * 0.15, self.WIDTH - 20, self.HEIGHT * 0.45
        )
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
            self._smoke_movie.stop()
            self.close()

    def shift(self, delta: QPoint) -> None:
        """主圓圈被拖曳時同步跟隨；動畫進行中則平移動畫的起訖點，避免被下一幀蓋回原位。"""
        if self._anim.state() == QPropertyAnimation.Running:
            self._anim.setStartValue(self._anim.startValue() + delta)
            self._anim.setEndValue(self._anim.endValue() + delta)
        else:
            self.move(self.pos() + delta)


class SpeechBubble(QWidget):
    """Live2D 模式的 Stop 事件通知：漫畫對話框，不會自動消失，點擊後才關閉。"""

    WIDTH, HEIGHT = 200, 60
    TAIL_W, TAIL_H = 20, 8  # 對話框下緣的尖角尾巴，指向角色頭部
    OFFSET_X, OFFSET_Y = 40, 60  # 相對錨點的位移：正值往右／往下

    def __init__(self, text: str, tip_pos: QPoint):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(self.WIDTH, self.HEIGHT + self.TAIL_H)
        self._text = text
        self.move(
            tip_pos.x() - self.WIDTH // 2 + self.OFFSET_X,
            tip_pos.y() - self.HEIGHT - self.TAIL_H + self.OFFSET_Y,
        )
        self.show()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        body = QRectF(2, 2, self.WIDTH - 4, self.HEIGHT - 4)
        path = QPainterPath()
        path.addRoundedRect(body, 14, 14)
        tail_cx = self.WIDTH / 2
        path.moveTo(tail_cx - self.TAIL_W / 2 -40, self.HEIGHT - 4)
        path.lineTo(tail_cx -40, self.HEIGHT + self.TAIL_H - 4)
        path.lineTo(tail_cx + self.TAIL_W / 2 -40, self.HEIGHT - 4)
        path.closeSubpath()

        fill = QColor("#ffffff")
        fill.setAlphaF(0.6)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)

        font = p.font()
        font.setBold(True)
        font.setPointSize(11)
        p.setFont(font)
        p.setPen(QColor("#3a2410"))
        p.drawText(body.adjusted(8, 4, -8, -4), Qt.AlignCenter | Qt.TextWordWrap, self._text)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.close()

    def shift(self, delta: QPoint) -> None:
        self.move(self.pos() + delta)


class ToolNameLabel(QWidget):
    """Live2D 模式的 PreToolUse 通知：純文字（無底色、無外框），PostToolUse 時隱藏。"""

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._text = ""

    def show_text(self, text: str, pos: QPoint) -> None:
        self._text = text
        fm = QFontMetrics(self.font())
        self.setFixedSize(fm.horizontalAdvance(text) + 16, fm.height() + 8)
        self.move(pos)
        self.show()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#44b8d4"))
        p.drawText(self.rect(), Qt.AlignCenter, self._text)

    def shift(self, delta: QPoint) -> None:
        self.move(self.pos() + delta)


class ToolUseEffect(QWidget):
    """PreToolUse 開始播放、PostToolUse 停止：主圓圈左下角播放 GIF 動畫。
    若 PostToolUse 遲遲未到（例如 hook 漏發），SAFETY_TIMEOUT_MS 後自動隱藏，避免卡住。"""

    WIDTH, HEIGHT = 120, 120
    OFFSET_X, OFFSET_Y = -100, -150  # 相對主圓圈左下角的位移：負值往左／往上
    SAFETY_TIMEOUT_MS = 30_000

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
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

    def open(self, bubble_bottom_left: QPoint) -> None:
        self.move(
            bubble_bottom_left.x() + self.OFFSET_X,
            bubble_bottom_left.y() + self.OFFSET_Y,
        )
        self._movie.stop()
        self._movie.start()
        self.show()
        self._hide_timer.start(self.SAFETY_TIMEOUT_MS)

    def close_gif(self) -> None:
        self._hide_timer.stop()
        self._movie.stop()
        self.hide()

    def _on_timeout(self) -> None:
        self.close_gif()


class ThinkingEffect(QWidget):
    """UserPromptSubmit 事件反應：主圓圈正上方播放 GIF，上下浮動循環，
    固定秒數後自動隱藏（ponytail: 不追蹤後續事件，時間到就收，需要更精準時機再改）。"""

    WIDTH, HEIGHT = 120, 120
    OFFSET_Y = -100  # 相對主圓圈頂部置中的位移，與 Toast 落地位置相同高度
    FLOAT_PX = 12
    FLOAT_CYCLE_MS = 1500
    VISIBLE_MS = 3500

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._movie = QMovie(THINKING_GIF)
        self._movie.frameChanged.connect(lambda _: self.update())

        self._float_anim = QPropertyAnimation(self, b"pos", self)
        self._float_anim.setDuration(self.FLOAT_CYCLE_MS)
        self._float_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._float_anim.setLoopCount(-1)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.close_gif)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pm = self._movie.currentPixmap()
        if not pm.isNull():
            scaled = pm.scaled(
                self.WIDTH, self.HEIGHT, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            p.drawPixmap(
                (self.WIDTH - scaled.width()) // 2-10,
                (self.HEIGHT - scaled.height()) // 2,
                scaled,
            )

    def open(self, bubble_top_center: QPoint) -> None:
        top_pos = QPoint(bubble_top_center.x() - self.WIDTH // 2, bubble_top_center.y() + self.OFFSET_Y)
        self.move(top_pos)
        self._movie.stop()
        self._movie.start()
        self.show()

        low_pos = QPoint(top_pos.x(), top_pos.y() + self.FLOAT_PX)
        self._float_anim.stop()
        self._float_anim.setStartValue(top_pos)
        self._float_anim.setKeyValueAt(0.5, low_pos)
        self._float_anim.setEndValue(top_pos)
        self._float_anim.start()

        self._hide_timer.start(self.VISIBLE_MS)

    def close_gif(self) -> None:
        self._hide_timer.stop()
        self._float_anim.stop()
        self._movie.stop()
        self.hide()

    def shift(self, delta: QPoint) -> None:
        """主圓圈被拖曳時同步跟隨；浮動動畫進行中則平移每個關鍵影格。"""
        if self._float_anim.state() == QPropertyAnimation.Running:
            for step, value in self._float_anim.keyValues():
                self._float_anim.setKeyValueAt(step, value + delta)
        else:
            self.move(self.pos() + delta)


class NotificationEffect(QWidget):
    """Notification 事件反應：GIF 右下角對齊主圓圈中心，點擊後消失。"""

    WIDTH, HEIGHT = 120, 120

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._movie = QMovie(NOTIFICATION_GIF)
        self._movie.frameChanged.connect(lambda _: self.update())

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

    def play(self, bubble_center: QPoint) -> None:
        self.move(bubble_center.x() - self.WIDTH, bubble_center.y() - self.HEIGHT)
        self._movie.stop()
        self._movie.start()
        self.show()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._movie.stop()
            self.hide()


class PreCompactEffect(QWidget):
    """PreCompact 事件反應：對話即將被壓縮的提醒，主圓圈右上角小圖示，
    一閃即逝（VISIBLE_MS 後自動隱藏），點擊也可提前關閉。"""

    WIDTH, HEIGHT = 48, 48
    OFFSET_X, OFFSET_Y = -36, -12  # 相對主圓圈右上角的位移
    VISIBLE_MS = 2500

    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self._movie = QMovie(NOTIFICATION_GIF)
        self._movie.frameChanged.connect(lambda _: self.update())

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

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

    def play(self, bubble_top_right: QPoint) -> None:
        self.move(bubble_top_right.x() + self.OFFSET_X, bubble_top_right.y() + self.OFFSET_Y)
        self._movie.stop()
        self._movie.start()
        self.show()
        self._hide_timer.start(self.VISIBLE_MS)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._hide_timer.stop()
            self._movie.stop()
            self.hide()
