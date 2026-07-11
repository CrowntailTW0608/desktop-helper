"""設定視窗：外觀、應用程式連結、Claude 用量、一般（6.4 節）"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from helper import autostart, config
from helper.bubble import DEFAULT_LIVE2D_LAYOUT, MODE_GIF, MODE_LIVE2D
from helper.icon import app_icon
from helper.live2d_characters import CHARACTERS
from helper.trigger import DEFAULT_TRIGGER_DIR


class LinkDialog(QDialog):
    """新增/編輯單一連結（名稱 + 目標）。"""

    def __init__(self, parent=None, link=None):
        super().__init__(parent)
        self.setWindowTitle("編輯連結" if link else "新增連結")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.name_edit = QLineEdit(link["name"] if link else "")
        form.addRow("顯示名稱", self.name_edit)

        self.path_edit = QLineEdit(link["path"] if link else "")
        self.path_edit.setPlaceholderText(
            '執行檔/捷徑/資料夾路徑、https:// 網址，'
            '或帶參數指令列如 "C:\\...\\chrome.exe" --profile-directory="Profile 7"'
        )
        browse_file = QPushButton("選檔案…")
        browse_file.clicked.connect(self._pick_file)
        browse_dir = QPushButton("選資料夾…")
        browse_dir.clicked.connect(self._pick_dir)
        row = QHBoxLayout()
        row.addWidget(self.path_edit)
        row.addWidget(browse_file)
        row.addWidget(browse_dir)
        form.addRow("目標", row)

        buttons = QHBoxLayout()
        ok = QPushButton("確定")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        form.addRow(buttons)

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇目標", "", "程式與捷徑 (*.exe *.lnk *.bat);;所有檔案 (*)"
        )
        if path:
            self.path_edit.setText(path)
            if not self.name_edit.text():
                self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, "選擇資料夾")
        if path:
            self.path_edit.setText(path)
            if not self.name_edit.text():
                self.name_edit.setText(os.path.basename(path))

    def _accept(self):
        if not self.name_edit.text().strip() or not self.path_edit.text().strip():
            QMessageBox.warning(self, "Desktop Helper", "名稱與目標皆不可空白。")
            return
        self.accept()

    def link(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "path": self.path_edit.text().strip(),
        }


class SettingsDialog(QDialog):
    """設定變更即時生效並寫入設定檔（FR-19）。"""

    gifChanged = Signal()
    displayModeChanged = Signal()
    live2dCharacterChanged = Signal()
    live2dLayoutChanged = Signal()
    linksChanged = Signal()
    usageChanged = Signal()
    triggerChanged = Signal()

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Desktop Helper 設定")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)

        character_box = self._build_live2d_character()
        appearance_box = self._build_appearance()

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.addWidget(appearance_box)
        general_layout.addWidget(self._build_links())
        general_layout.addWidget(self._build_usage())
        general_layout.addWidget(self._build_trigger())
        general_layout.addWidget(self._build_general())

        live2d_tab = QWidget()
        live2d_layout = QVBoxLayout(live2d_tab)
        live2d_layout.addWidget(character_box)
        live2d_layout.addWidget(self._build_live2d_layout())
        live2d_layout.addStretch()

        tabs = QTabWidget()
        tabs.addTab(general_tab, "一般")
        tabs.addTab(live2d_tab, "Live2D")
        root.addWidget(tabs)

    # ── Live2D 角色與版面 ────────────────────────────────────────────────

    def _build_live2d_character(self) -> QGroupBox:
        box = QGroupBox("角色")
        row = QHBoxLayout(box)
        row.addWidget(QLabel("Live2D 角色"))
        self.character_combo = QComboBox()
        for character_id, character in CHARACTERS.items():
            self.character_combo.addItem(character["name"], character_id)
        self.character_combo.setCurrentIndex(
            self.character_combo.findData(self.cfg["live2d_character"])
        )
        self.character_combo.setEnabled(self.cfg["display_mode"] == MODE_LIVE2D)
        self.character_combo.currentIndexChanged.connect(self._character_updated)
        row.addWidget(self.character_combo)
        row.addStretch()
        return box

    def _build_live2d_layout(self) -> QGroupBox:
        box = QGroupBox("版面")
        form = QFormLayout(box)
        layout = self.cfg["live2d_layout"]

        def spin(key: str, minimum: int, maximum: int) -> QSpinBox:
            s = QSpinBox()
            s.setRange(minimum, maximum)
            s.setValue(int(layout[key]))
            s.editingFinished.connect(self._live2d_layout_updated)
            return s

        self.arc_offset_spin = spin("arc_top_offset", -200, 400)
        form.addRow("衛星選單弧形錨點偏移（px）", self.arc_offset_spin)
        self.l2d_w_spin = spin("w", 100, 800)
        form.addRow("視窗寬度（px）", self.l2d_w_spin)
        self.l2d_h_spin = spin("h", 100, 1000)
        form.addRow("視窗高度（px）", self.l2d_h_spin)
        self.l2d_scale_spin = QDoubleSpinBox()
        self.l2d_scale_spin.setRange(0.1, 3.0)
        self.l2d_scale_spin.setSingleStep(0.05)
        self.l2d_scale_spin.setValue(float(layout["scale"]))
        self.l2d_scale_spin.editingFinished.connect(self._live2d_layout_updated)
        form.addRow("角色縮放（視窗開大留動作空間時，調小維持原本大小）", self.l2d_scale_spin)
        self.l2d_fps_spin = spin("fps_ms", 10, 200)
        form.addRow("渲染間隔（ms，值越小越流暢但越耗效能）", self.l2d_fps_spin)
        self.ring_margin_spin = spin("ring_center_y_margin", 0, 400)
        form.addRow("用量光環中心距視窗底部（px）", self.ring_margin_spin)
        self.ring_rx_spin = spin("ring_rx", 10, 300)
        form.addRow("用量光環寬度半徑（px）", self.ring_rx_spin)
        self.ring_ry_spin = spin("ring_ry", 5, 150)
        form.addRow("用量光環高度半徑（px）", self.ring_ry_spin)
        self.tool_label_x_spin = spin("tool_label_x", -400, 400)
        form.addRow("工具名稱標籤水平偏移（px，相對視窗左上角）", self.tool_label_x_spin)
        self.tool_label_y_spin = spin("tool_label_y", -400, 400)
        form.addRow("工具名稱標籤垂直偏移（px，相對視窗左上角）", self.tool_label_y_spin)

        reset = QPushButton("還原預設")
        reset.clicked.connect(self._reset_live2d_layout)
        form.addRow(reset)
        return box

    def _live2d_layout_updated(self):
        layout = self.cfg["live2d_layout"]
        layout["arc_top_offset"] = self.arc_offset_spin.value()
        layout["w"] = self.l2d_w_spin.value()
        layout["h"] = self.l2d_h_spin.value()
        layout["scale"] = self.l2d_scale_spin.value()
        layout["fps_ms"] = self.l2d_fps_spin.value()
        layout["ring_center_y_margin"] = self.ring_margin_spin.value()
        layout["ring_rx"] = self.ring_rx_spin.value()
        layout["ring_ry"] = self.ring_ry_spin.value()
        layout["tool_label_x"] = self.tool_label_x_spin.value()
        layout["tool_label_y"] = self.tool_label_y_spin.value()
        config.save(self.cfg)
        self.live2dLayoutChanged.emit()

    def _reset_live2d_layout(self):
        self.cfg["live2d_layout"] = dict(DEFAULT_LIVE2D_LAYOUT)
        layout = self.cfg["live2d_layout"]
        self.arc_offset_spin.setValue(layout["arc_top_offset"])
        self.l2d_w_spin.setValue(layout["w"])
        self.l2d_h_spin.setValue(layout["h"])
        self.l2d_scale_spin.setValue(layout["scale"])
        self.l2d_fps_spin.setValue(layout["fps_ms"])
        self.ring_margin_spin.setValue(layout["ring_center_y_margin"])
        self.ring_rx_spin.setValue(layout["ring_rx"])
        self.ring_ry_spin.setValue(layout["ring_ry"])
        self.tool_label_x_spin.setValue(layout["tool_label_x"])
        self.tool_label_y_spin.setValue(layout["tool_label_y"])
        config.save(self.cfg)
        self.live2dLayoutChanged.emit()

    # ── 1. 外觀 ──────────────────────────────────────────────────────────

    def _build_appearance(self) -> QGroupBox:
        box = QGroupBox("外觀")
        layout = QVBoxLayout(box)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("顯示模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("GIF", MODE_GIF)
        self.mode_combo.addItem("Live2D", MODE_LIVE2D)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.cfg["display_mode"]))
        self.mode_combo.currentIndexChanged.connect(self._mode_updated)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.gif_label = QLabel(self.cfg["gif_path"] or "（預設圖案）")
        self.gif_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.gif_label)

        row = QHBoxLayout()
        pick = QPushButton("選擇 GIF…")
        pick.clicked.connect(self._pick_gif)
        pick_dir = QPushButton("選擇資料夾…")
        pick_dir.clicked.connect(self._pick_gif_dir)
        reset = QPushButton("還原預設")
        reset.clicked.connect(lambda: self._set_gif(""))
        row.addWidget(pick)
        row.addWidget(pick_dir)
        row.addWidget(reset)
        row.addStretch()
        layout.addLayout(row)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("輪播間隔（秒，選資料夾時生效）"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 86400)
        self.interval_spin.setValue(int(self.cfg["gif_interval"]))
        self.interval_spin.editingFinished.connect(self._interval_updated)
        interval_row.addWidget(self.interval_spin)
        interval_row.addStretch()
        layout.addLayout(interval_row)
        return box

    def _mode_updated(self, _index: int):
        self.cfg["display_mode"] = self.mode_combo.currentData()
        self.character_combo.setEnabled(self.cfg["display_mode"] == MODE_LIVE2D)
        config.save(self.cfg)
        self.displayModeChanged.emit()

    def _character_updated(self, _index: int):
        self.cfg["live2d_character"] = self.character_combo.currentData()
        config.save(self.cfg)
        self.live2dCharacterChanged.emit()

    def _pick_gif(self):
        path, _ = QFileDialog.getOpenFileName(self, "選擇 GIF", "", "GIF (*.gif)")
        if path:
            self._set_gif(path)

    def _pick_gif_dir(self):
        path = QFileDialog.getExistingDirectory(self, "選擇 GIF 資料夾")
        if path:
            self._set_gif(path)

    def _set_gif(self, path: str):
        self.cfg["gif_path"] = path
        self.gif_label.setText(path or "（預設圖案）")
        config.save(self.cfg)
        self.gifChanged.emit()

    def _interval_updated(self):
        if self.interval_spin.value() == self.cfg["gif_interval"]:
            return
        self.cfg["gif_interval"] = self.interval_spin.value()
        config.save(self.cfg)
        self.gifChanged.emit()

    # ── 2. 應用程式連結 ──────────────────────────────────────────────────

    def _build_links(self) -> QGroupBox:
        box = QGroupBox(f"應用程式連結（最多 {config.MAX_LINKS} 個，拖曳可調整順序）")
        layout = QVBoxLayout(box)
        self.link_list = QListWidget()
        self.link_list.setDragDropMode(QListWidget.InternalMove)
        self.link_list.model().rowsMoved.connect(self._rows_moved)
        self._reload_link_list()
        layout.addWidget(self.link_list)
        row = QHBoxLayout()
        for label, handler in (
            ("新增…", self._add_link),
            ("編輯…", self._edit_link),
            ("刪除", self._remove_link),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        return box

    def _reload_link_list(self):
        self.link_list.clear()
        for link in self.cfg["links"]:
            self.link_list.addItem(f"{link['name']} — {link['path']}")

    def _rows_moved(self, _parent, start, _end, _dest, row):
        """拖曳排序後同步 cfg（清單本身已由 Qt 移好，不需重載）。"""
        link = self.cfg["links"].pop(start)
        if row > start:
            row -= 1
        self.cfg["links"].insert(row, link)
        config.save(self.cfg)
        self.linksChanged.emit()

    def _links_updated(self):
        self._reload_link_list()
        config.save(self.cfg)
        self.linksChanged.emit()

    def _add_link(self):
        if len(self.cfg["links"]) >= config.MAX_LINKS:
            QMessageBox.information(
                self, "Desktop Helper", f"連結數量已達上限（{config.MAX_LINKS} 個）。"
            )
            return
        dlg = LinkDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.cfg["links"].append(dlg.link())
            self._links_updated()

    def _edit_link(self):
        i = self.link_list.currentRow()
        if i < 0:
            return
        dlg = LinkDialog(self, self.cfg["links"][i])
        if dlg.exec() == QDialog.Accepted:
            self.cfg["links"][i] = dlg.link()
            self._links_updated()

    def _remove_link(self):
        i = self.link_list.currentRow()
        if i < 0:
            return
        del self.cfg["links"][i]
        self._links_updated()

    # ── 3. Claude 用量（FR-20）──────────────────────────────────────────

    def _build_usage(self) -> QGroupBox:
        box = QGroupBox("Claude 用量")
        cu = self.cfg["claude_usage"]
        form = QFormLayout(box)
        self.usage_enable = QCheckBox("啟用用量顯示（主圓圈外圍三層圓環）")
        self.usage_enable.setChecked(cu["enabled"])
        self.usage_enable.toggled.connect(self._usage_updated)
        form.addRow(self.usage_enable)

        self.elapsed_line_enable = QCheckBox("顯示均勻消耗基準白線")
        self.elapsed_line_enable.setChecked(cu["show_elapsed_line"])
        self.elapsed_line_enable.toggled.connect(self._usage_updated)
        form.addRow(self.elapsed_line_enable)

        self.key_edit = QLineEdit(cu["session_key"])
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.editingFinished.connect(self._usage_updated)
        form.addRow("Session Key", self.key_edit)

        self.org_edit = QLineEdit(cu["org_id"])
        self.org_edit.editingFinished.connect(self._usage_updated)
        form.addRow("Org ID", self.org_edit)
        return box

    def _usage_updated(self, *_):
        cu = self.cfg["claude_usage"]
        cu["enabled"] = self.usage_enable.isChecked()
        cu["show_elapsed_line"] = self.elapsed_line_enable.isChecked()
        cu["session_key"] = self.key_edit.text().strip()
        cu["org_id"] = self.org_edit.text().strip()
        config.save(self.cfg)
        self.usageChanged.emit()

    # ── 4. Trigger 監控 ──────────────────────────────────────────────────

    def _build_trigger(self) -> QGroupBox:
        box = QGroupBox("Trigger 監控")
        tr = self.cfg["trigger"]
        layout = QVBoxLayout(box)

        self.trigger_enable = QCheckBox(
            "啟用監控（每 2 秒讀取一次，Stop、PostToolUse、Notification）"
        )
        self.trigger_enable.setChecked(tr["enabled"])
        self.trigger_enable.toggled.connect(self._trigger_updated)
        layout.addWidget(self.trigger_enable)

        self.trigger_dir_label = QLabel(tr["dir"] or DEFAULT_TRIGGER_DIR)
        self.trigger_dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.trigger_dir_label)

        row = QHBoxLayout()
        pick = QPushButton("選擇資料夾…")
        pick.clicked.connect(self._pick_trigger_dir)
        reset = QPushButton("還原預設")
        reset.clicked.connect(lambda: self._set_trigger_dir(""))
        row.addWidget(pick)
        row.addWidget(reset)
        row.addStretch()
        layout.addLayout(row)
        return box

    def _pick_trigger_dir(self):
        path = QFileDialog.getExistingDirectory(self, "選擇 Trigger 資料夾")
        if path:
            self._set_trigger_dir(path)

    def _set_trigger_dir(self, path: str):
        self.cfg["trigger"]["dir"] = path
        self.trigger_dir_label.setText(path or DEFAULT_TRIGGER_DIR)
        config.save(self.cfg)
        self.triggerChanged.emit()

    def _trigger_updated(self, checked: bool):
        self.cfg["trigger"]["enabled"] = checked
        config.save(self.cfg)
        self.triggerChanged.emit()

    # ── 5. 一般 ──────────────────────────────────────────────────────────

    def _build_general(self) -> QGroupBox:
        box = QGroupBox("一般")
        layout = QVBoxLayout(box)
        auto = QCheckBox("開機時自動啟動")
        auto.setChecked(self.cfg["auto_start"])
        auto.toggled.connect(self._autostart_updated)
        layout.addWidget(auto)
        return box

    def _autostart_updated(self, checked: bool):
        self.cfg["auto_start"] = checked
        config.save(self.cfg)
        try:
            autostart.set_enabled(checked)
        except OSError as e:
            QMessageBox.warning(self, "Desktop Helper", f"無法更新開機自啟設定：\n{e}")
