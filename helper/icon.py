"""App 圖示（系統匣、設定視窗標題列共用）：行星＋傾斜軌道衛星"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

_PLANET_COLOR = QColor("#4a6fa5")
_ORBIT_COLOR = QColor("#8fb3e0")
_TILT_DEG = -30  # 軌道傾斜角度，長軸呈右上至左下
# 三顆衛星在軌道上的角度（0 = 軌道右側，順時針）與各自顏色，刻意不均勻分佈
# 角度需遠離 90°/270°（軌道短軸），否則會被放大後的行星本體完全遮住
_SATELLITES = (
    (20, QColor("#74c991")),
    (155, QColor("#d9a84e")),
    (260, QColor("#d97757")),
)


def app_icon(size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    center = size / 2
    planet_r = size * 0.34
    orbit_rx = size * 0.46
    orbit_ry = size * 0.20
    sat_r = size * 0.075

    p.translate(center, center)
    p.rotate(_TILT_DEG)

    orbit_rect = QRectF(-orbit_rx, -orbit_ry, orbit_rx * 2, orbit_ry * 2)
    orbit_pen = QPen(_ORBIT_COLOR, max(1.0, size * 0.035))

    def satellite_pos(angle_deg: float) -> QPointF:
        rad = math.radians(angle_deg)
        return QPointF(orbit_rx * math.cos(rad), orbit_ry * math.sin(rad))

    # 軌道後半＋後半的衛星：先畫，之後會被行星本體遮住一部分
    p.setPen(orbit_pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(orbit_rect, 0, 180 * 16)
    p.setPen(Qt.NoPen)
    for angle, color in _SATELLITES:
        if 0 <= angle % 360 <= 180:
            p.setBrush(color)
            p.drawEllipse(satellite_pos(angle), sat_r, sat_r)

    # 行星本體（蓋住軌道中段，製造穿越感）
    p.setBrush(_PLANET_COLOR)
    p.drawEllipse(QPointF(0, 0), planet_r, planet_r)

    # 軌道前半＋前半的衛星：疊在行星之上
    p.setPen(orbit_pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(orbit_rect, 180 * 16, 180 * 16)
    p.setPen(Qt.NoPen)
    for angle, color in _SATELLITES:
        if 180 < angle % 360 < 360:
            p.setBrush(color)
            p.drawEllipse(satellite_pos(angle), sat_r, sat_r)

    p.end()
    return QIcon(pm)
