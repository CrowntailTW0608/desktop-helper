"""衛星圓圈：環形排列、展開/收合動畫、點擊啟動目標"""

import math
import os
import shlex
import subprocess

from PySide6.QtCore import (
    QEasingCurve,
    QFileInfo,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFileIconProvider, QMessageBox, QWidget

SAT_D = 48
ORBIT_R = 90  # circle 模式（GIF）：以中心點環繞一整圈
ARC_R = 120  # arc 模式（Live2D）：以角色上緣為錨點，向上展開半圓弧（像彩虹）
ANIM_MS = 200


def is_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def _command_exe(path: str):
    """把 path 當成「引號括住的執行檔 + 參數」解析，回傳執行檔路徑；失敗回傳 None。

    例：'"C:\\...\\chrome.exe" --profile-directory="Profile 7"' -> 'C:\\...\\chrome.exe'
    """
    try:
        tokens = shlex.split(path, posix=False)
    except ValueError:
        return None
    if not tokens:
        return None
    exe = tokens[0].strip('"')
    return exe if os.path.isfile(exe) else None


def resolve_target(path: str) -> dict:
    """判別連結目標型別（FR-11）：url／folder／file／command／invalid。

    command：帶參數的指令列（例如指定 Chrome profile），需用 subprocess 啟動；
    其餘型別以 os.startfile 開啟。
    """
    if is_url(path):
        return {"kind": "url", "exe": None}
    if os.path.isdir(path):
        return {"kind": "folder", "exe": None}
    if os.path.isfile(path):
        return {"kind": "file", "exe": path}
    exe = _command_exe(path)
    if exe:
        return {"kind": "command", "exe": exe}
    return {"kind": "invalid", "exe": None}


def open_target(path: str) -> None:
    """依 resolve_target 的判別結果開啟目標；失敗時拋出 OSError。"""
    target = resolve_target(path)
    if target["kind"] == "invalid":
        raise FileNotFoundError(f"找不到目標：{path}")
    if target["kind"] == "command":
        subprocess.Popen(path)
    else:
        os.startfile(path)


class Satellite(QWidget):
    activated = Signal()

    def __init__(self, tooltip: str, icon=None, text: str = ""):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(SAT_D, SAT_D)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self._icon = icon
        self._text = text

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(37, 37, 37, 235))
        p.setPen(QPen(QColor("#555555"), 1))
        p.drawEllipse(QRectF(1, 1, SAT_D - 2, SAT_D - 2))
        if self._icon is not None and not self._icon.isNull():
            pm = self._icon.pixmap(28, 28)
            p.drawPixmap(QRect(10, 10, 28, 28), pm)
        else:
            p.setPen(QColor("#e0e0e0"))
            p.setFont(QFont("Segoe UI Emoji", 16))
            p.drawText(self.rect(), Qt.AlignCenter, self._text)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.activated.emit()


class SatelliteRing(QObject):
    """管理衛星的建立、排列與動畫。"""

    settingsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._links = []
        self._sats = []
        self._expanded = False
        self._mode = "circle"
        self._group = None
        self._provider = QFileIconProvider()

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_links(self, links: list) -> None:
        self._links = links
        self.collapse(animated=False)

    def toggle(self, anchor: QPoint, mode: str = "circle") -> None:
        if self._expanded:
            self.collapse()
        else:
            self.expand(anchor, mode)

    # ── 展開/收合（FR-8、FR-12、6.3 節動畫）─────────────────────────────

    def _target_pos(self, anchor: QPoint, i: int, n: int, mode: str) -> QPoint:
        """circle：以 anchor 為中心環繞一整圈；arc：以 anchor 為錨點向上展開半圓弧（像彩虹）。"""
        if mode == "arc":
            angle = math.radians(180 + i * 180 / (n - 1)) if n > 1 else math.radians(270)
            radius = ARC_R
        else:
            angle = math.radians(-90 + i * 360 / n)
            radius = ORBIT_R
        return anchor + QPoint(
            round(radius * math.cos(angle)), round(radius * math.sin(angle))
        ) - QPoint(SAT_D // 2, SAT_D // 2)

    def expand(self, anchor: QPoint, mode: str = "circle") -> None:
        if self._expanded:
            return
        self._build_satellites()
        self._expanded = True
        self._mode = mode
        n = len(self._sats)
        start = anchor - QPoint(SAT_D // 2, SAT_D // 2)
        self._group = QParallelAnimationGroup(self)
        for i, sat in enumerate(self._sats):
            target = self._target_pos(anchor, i, n, mode)
            sat.move(start)
            sat.setWindowOpacity(0.0)
            sat.show()
            for prop, begin, end in (
                (b"pos", start, target),
                (b"windowOpacity", 0.0, 1.0),
            ):
                anim = QPropertyAnimation(sat, prop, self._group)
                anim.setDuration(ANIM_MS)
                anim.setStartValue(begin)
                anim.setEndValue(end)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                self._group.addAnimation(anim)
        self._group.start()

    def reposition(self, anchor: QPoint) -> None:
        """主圓圈拖曳時讓衛星跟隨（略過動畫，直接就定位；沿用展開時的排列模式）。"""
        if not self._expanded:
            return
        if self._group:
            self._group.stop()
            self._group = None
        n = len(self._sats)
        for i, sat in enumerate(self._sats):
            sat.setWindowOpacity(1.0)
            sat.move(self._target_pos(anchor, i, n, self._mode))

    def collapse(self, animated: bool = True) -> None:
        if not self._expanded:
            return
        self._expanded = False
        if self._group:
            self._group.stop()
            self._group = None
        sats = self._sats
        self._sats = []
        if not animated:
            for sat in sats:
                sat.close()
            return
        group = QParallelAnimationGroup(self)
        for sat in sats:
            anim = QPropertyAnimation(sat, b"windowOpacity", group)
            anim.setDuration(ANIM_MS)
            anim.setStartValue(sat.windowOpacity())
            anim.setEndValue(0.0)
            group.addAnimation(anim)
        group.finished.connect(lambda: [sat.close() for sat in sats])
        group.start()
        self._group = group

    # ── 衛星建立 ─────────────────────────────────────────────────────────

    def _build_satellites(self) -> None:
        self._sats = []
        for link in self._links:
            sat = Satellite(link["name"], *self._icon_for(link))
            sat.activated.connect(lambda l=link: self._open(l))
            self._sats.append(sat)
        gear = Satellite("設定", text="⚙")
        gear.activated.connect(self._on_gear)
        self._sats.append(gear)

    def _icon_for(self, link: dict):
        """回傳 (icon, text)：系統圖示、地球、或名稱前 1～2 字。"""
        target = resolve_target(link["path"])
        if target["kind"] == "url":
            return None, "🌐"
        icon_path = target["exe"] if target["kind"] in ("file", "command") else None
        if target["kind"] == "folder":
            icon_path = link["path"]
        if icon_path:
            icon = self._provider.icon(QFileInfo(icon_path))
            if not icon.isNull():
                return icon, ""
        return None, link["name"][:2]

    # ── 點擊行為 ─────────────────────────────────────────────────────────

    def _on_gear(self) -> None:
        self.collapse()
        self.settingsRequested.emit()

    def _open(self, link: dict) -> None:
        self.collapse()
        try:
            open_target(link["path"])
        except OSError as e:
            QMessageBox.warning(
                None, "Desktop Helper", f"無法開啟「{link['name']}」：\n{e}"
            )
