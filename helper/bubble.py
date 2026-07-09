"""主圓圈視窗：GIF（單張/資料夾輪播）或 Live2D 完整模型、拖曳、點擊、用量圓環繪製"""

import glob
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QToolTip, QWidget

from helper.live2d_characters import CHARACTERS, DEFAULT_CHARACTER
from helper.live2d_view import Live2DRenderer
from helper.usage import STATUS_ZH, format_reset_time, incident_badge_color

BUBBLE_D = 96
RING_W = 3
RING_GAP = 2
WINDOW = 128  # 三環外緣約 126px（6.2 節）
DRAG_THRESHOLD = 6

MODE_GIF = "gif"
MODE_LIVE2D = "live2d"

LIVE2D_W, LIVE2D_H = 280, 420
LIVE2D_FPS_MS = 33

# Live2D 用量光環（地上橢圓，起訖點在正前方／下緣，中段會被角色身體自然遮住）
LIVE2D_RING_CENTER_Y = LIVE2D_H - 38
LIVE2D_RING_RX = 90
LIVE2D_RING_RY = 26
LIVE2D_RING_GAP_X = 8
LIVE2D_RING_GAP_Y = 5

SEV_COLOR = {"normal": "#44cc66", "warning": "#f0a030", "critical": "#ff4444"}
SEV_COLOR = {"normal": "#74c991", "warning": "#d9a84e", "critical": "#d97757"}
BASE_RING = "#3a3a3a"
ERROR_RING = "#777777"
DEFAULT_BG = "#4a6fa5"


class Bubble(QWidget):
    clicked = Signal()
    moved = Signal(int, int)
    dragMoved = Signal()

    def __init__(self):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WINDOW, WINDOW)
        self._mode = MODE_GIF
        self._movie = None
        self._gif_dir = ""
        self._current_gif = ""
        self._rotate_timer = QTimer(self)
        self._rotate_timer.timeout.connect(self._next_gif)
        self._live2d = None
        self._live2d_character = DEFAULT_CHARACTER
        self._live2d_pixmap = None
        self._live2d_timer = QTimer(self)
        self._live2d_timer.setInterval(LIVE2D_FPS_MS)
        self._live2d_timer.timeout.connect(self._tick_live2d)
        self._press_offset = None
        self._press_global = None
        self._dragged = False
        self._usage_enabled = False
        self._usage_items = []
        self._usage_error = ""
        self._incidents = []

    # ── 顯示模式（GIF / Live2D）──────────────────────────────────────────

    def set_display_mode(self, mode: str) -> None:
        if mode not in (MODE_GIF, MODE_LIVE2D) or mode == self._mode:
            return
        self._mode = mode
        if mode == MODE_LIVE2D:
            self.setFixedSize(LIVE2D_W, LIVE2D_H)
            if self._live2d is None:
                self._live2d = Live2DRenderer(self._live2d_character, LIVE2D_W, LIVE2D_H)
            self._live2d_timer.start()
        else:
            self._live2d_timer.stop()
            self.setFixedSize(WINDOW, WINDOW)
        self.update()

    def set_live2d_character(self, character_id: str) -> None:
        """切換 Live2D 角色；若目前正在 Live2D 模式，立即重建渲染器。"""
        if character_id not in CHARACTERS or character_id == self._live2d_character:
            return
        self._live2d_character = character_id
        if self._live2d is not None:
            self._live2d.dispose()
            self._live2d = Live2DRenderer(character_id, LIVE2D_W, LIVE2D_H)

    def _tick_live2d(self) -> None:
        self._live2d_pixmap = QPixmap.fromImage(self._live2d.render_frame())
        self.update()

    def live2d_react(self, event: str) -> None:
        """對應 trigger 事件；僅在 Live2D 模式且模型已載入時生效，行為由角色設定驅動。"""
        if self._live2d is not None:
            self._live2d.react(event)

    # ── GIF（FR-2a：檔案單張、資料夾輪播）────────────────────────────────

    def set_gif(self, path: str, interval_s: int = 60) -> None:
        self._rotate_timer.stop()
        self._gif_dir = ""
        if path and os.path.isdir(path):
            self._gif_dir = path
            self._rotate_timer.setInterval(max(1, int(interval_s)) * 1000)
            self._next_gif()
            self._rotate_timer.start()
        else:
            self._play(path)

    def _next_gif(self) -> None:
        gifs = glob.glob(os.path.join(self._gif_dir, "*.gif"))
        if not gifs:
            self._play("")
            return
        candidates = [g for g in gifs if g != self._current_gif] or gifs
        chosen = random.choice(candidates)
        if chosen != self._current_gif:
            self._play(chosen)

    def _play(self, path: str) -> None:
        if self._movie:
            self._movie.stop()
            self._movie = None
        self._current_gif = ""
        if path and os.path.isfile(path):
            movie = QMovie(path)
            if movie.isValid():
                movie.frameChanged.connect(lambda _: self.update())
                movie.start()
                self._movie = movie
                self._current_gif = path
        self.update()

    # ── 用量 ─────────────────────────────────────────────────────────────

    def set_usage_enabled(self, enabled: bool) -> None:
        self._usage_enabled = enabled
        if not enabled:
            self._usage_items = []
            self._usage_error = ""
            self._incidents = []
        self._refresh_tooltip()
        self.update()

    def set_usage(self, items: list) -> None:
        self._usage_items = items
        self._usage_error = ""
        self._refresh_tooltip()
        self.update()

    def set_usage_error(self, msg: str) -> None:
        self._usage_error = msg
        self._refresh_tooltip()
        self.update()

    def set_incidents(self, incidents: list) -> None:
        self._incidents = incidents
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self) -> None:
        if not self._usage_enabled:
            self.setToolTip("")
            return
        if self._usage_error:
            text = f"Claude 用量取得失敗：{self._usage_error}"
        elif self._usage_items:
            # sort by Session / Weekly Scoped / Weekly All
            # print(f'self._usage_items: {self._usage_items}')
            self._usage_items.sort(key=lambda it: ["Session (5hr)", "Weekly (7d)", "Fable (7d)"].index(it["label"]))

            lines = [
                f"{it['label']}\t  {it['percent']}%\t  {format_reset_time(it['resets_at'])}"
                for it in self._usage_items
            ]
            text = "\n".join(lines)
        else:
            text = "Claude 用量讀取中…"
        if self._incidents:
            inc_lines = [
                f"● {inc['name']}［{STATUS_ZH.get(inc['status'], inc['status'])}］"
                for inc in self._incidents
            ]
            text += "\n\n今日事故通報：\n" + "\n".join(inc_lines)
        self.setToolTip(text)

    # ── 繪製 ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        if self._mode == MODE_LIVE2D:
            self._paint_live2d()
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = cy = WINDOW / 2
        r = BUBBLE_D / 2
        circle = QRectF(cx - r, cy - r, BUBBLE_D, BUBBLE_D)

        clip = QPainterPath()
        clip.addEllipse(circle)
        p.save()
        p.setClipPath(clip)
        pm = self._movie.currentPixmap() if self._movie else None
        if pm is not None and not pm.isNull():
            pm = pm.scaled(
                BUBBLE_D, BUBBLE_D,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
            )
            p.drawPixmap(int(cx - pm.width() / 2), int(cy - pm.height() / 2), pm)
        else:
            self._paint_default_face(p, circle)
        p.restore()

        if self._usage_enabled:
            self._paint_rings(p, cx, cy, r)
            badge_color = incident_badge_color(self._incidents)
            if badge_color:
                self._paint_incident_badge(p, cx, cy, r, badge_color)

    def _paint_live2d(self) -> None:
        """Live2D 模式：先畫地上用量光環（若啟用），角色畫在上層，自然遮住光環後半段。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._usage_enabled:
            self._paint_live2d_rings(p)
        if self._live2d_pixmap is not None and not self._live2d_pixmap.isNull():
            p.drawPixmap(0, 0, self._live2d_pixmap)

    def _paint_default_face(self, p: QPainter, circle: QRectF) -> None:
        """未設定 GIF 時的預設外觀（FR-3）：純色圓 + 簡單笑臉。"""
        p.fillRect(circle, QColor(DEFAULT_BG))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        cx, cy = circle.center().x(), circle.center().y()
        p.drawEllipse(QRectF(cx - 18, cy - 14, 8, 12))
        p.drawEllipse(QRectF(cx + 10, cy - 14, 8, 12))
        pen = QPen(QColor("white"), 4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - 16, cy - 4, 32, 24), -30 * 16, -120 * 16)

    def _paint_rings(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        base = QColor(ERROR_RING if self._usage_error else BASE_RING)
        for i in range(3):
            radius = r + RING_GAP + RING_W / 2 + i * (RING_W + RING_GAP)
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            p.setPen(QPen(base, RING_W))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(rect)
            if self._usage_error or i >= len(self._usage_items):
                continue
            item = self._usage_items[i]
            pen = QPen(QColor(SEV_COLOR.get(item["severity"], "#4a9eff")), RING_W)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            span = -round(item["percent"] / 100 * 360 * 16)
            p.drawArc(rect, 90 * 16, span)
            # 均勻消耗基準白線：時間經過百分比的位置
            if item.get("elapsed") is not None:
                ang = math.radians(90 - item["elapsed"] * 3.6)
                inner, outer = radius - RING_W / 2 - 1, radius + RING_W / 2 + 1
                p.setPen(QPen(QColor("white"), 1.5))
                p.drawLine(
                    QPointF(cx + inner * math.cos(ang), cy - inner * math.sin(ang)),
                    QPointF(cx + outer * math.cos(ang), cy - outer * math.sin(ang)),
                )

    def _paint_live2d_rings(self, p: QPainter) -> None:
        """扁平橢圓光環：起訖點在下緣（正前方），順時針掃出進度；50% 落在上緣（角色身後，可能被遮擋）。"""
        cx = LIVE2D_W / 2
        cy = LIVE2D_RING_CENTER_Y
        base = QColor(ERROR_RING if self._usage_error else BASE_RING)
        for i in range(3):
            rx = LIVE2D_RING_RX + i * LIVE2D_RING_GAP_X
            ry = LIVE2D_RING_RY + i * LIVE2D_RING_GAP_Y
            rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
            p.setPen(QPen(base, RING_W))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(rect)
            if self._usage_error or i >= len(self._usage_items):
                continue
            item = self._usage_items[i]
            pen = QPen(QColor(SEV_COLOR.get(item["severity"], "#4a9eff")), RING_W)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            span = -round(item["percent"] / 100 * 360 * 16)
            p.drawArc(rect, -90 * 16, span)

    def _paint_incident_badge(self, p: QPainter, cx: float, cy: float, r: float, color: str) -> None:
        """今日有事故仍在處理時，於主圓圈右上角顯示小圓點徽章（類似狀態指示點）。"""
        badge_r = 8
        dist = r - 6
        ang = math.radians(45)
        x = cx + dist * math.cos(ang)
        y = cy - dist * math.sin(ang)
        p.setPen(QPen(QColor("#1c1c1c"), 2))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(x, y), badge_r, badge_r)

    # ── 拖曳與點擊（FR-6、FR-7）──────────────────────────────────────────

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._press_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragged = False

    def _show_usage_tip(self, global_pos) -> None:
        """右鍵立即顯示用量詳情（與 hover tooltip 同內容，FR-27）。
        需在 release 時顯示：press 顯示會被緊接的 release 事件自動關閉。"""
        text = self.toolTip() or "未啟用 Claude 用量顯示（可至設定開啟）"
        QToolTip.showText(global_pos, text, self)

    def mouseMoveEvent(self, e) -> None:
        if self._press_offset is None or not (e.buttons() & Qt.LeftButton):
            return
        g = e.globalPosition().toPoint()
        if not self._dragged:
            if (g - self._press_global).manhattanLength() < DRAG_THRESHOLD:
                return
            self._dragged = True
        self.move(g - self._press_offset)
        self.dragMoved.emit()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.RightButton:
            self._show_usage_tip(e.globalPosition().toPoint())
        elif e.button() == Qt.LeftButton and self._press_offset is not None:
            if self._dragged:
                self.moved.emit(self.x(), self.y())
            else:
                self.clicked.emit()
            self._press_offset = None
