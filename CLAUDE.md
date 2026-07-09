# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

桌面圓形小幫手（PySide6），常駐桌面永遠置頂的圓形視窗。詳細功能規格見 [specification.md](specification.md)，操作說明與設定方式見 [README.md](README.md)。

## 常用指令

```powershell
# 安裝環境（uv）
uv venv .venv
uv pip install -r requirements.txt

# 啟動（有主控台，方便看例外/log）
.venv\Scripts\python main.py

# 背景常駐執行（無主控台視窗）
.venv\Scripts\pythonw main.py
```

本專案沒有測試套件、lint 設定或 CI。變更後以手動啟動 `main.py` 驗證行為。

打包用 `DesktopHelper.spec`（PyInstaller），非日常開發流程。

## 架構

`main.py` 的 `HelperApp` 是整個程式的組裝點與事件路由中樞，把以下幾個獨立元件串在一起：

- **`helper/bubble.py`（`Bubble`）**：主圓圈視窗。有兩種顯示模式：
  - `MODE_GIF`：播放單一 GIF 或資料夾輪播，並在外圍疊繪 Claude 用量三層圓環（`_paint_rings`）。
  - `MODE_LIVE2D`：委派給 `Live2DRenderer` 畫完整模型，不裁切、不畫用量圓環。
  兩種模式共用同一顆 `Bubble` 視窗，切換靠 `set_display_mode()`，視窗尺寸也會跟著變（`WINDOW` vs `LIVE2D_W/H`）。
- **`helper/live2d_view.py`（`Live2DRenderer`）**：用 `live2d-py` + PyOpenGL 離屏 FBO 渲染 Live2D 模型，`render_frame()` 讀回 RGBA 轉成 `QImage` 供 `Bubble` 用 `QTimer`（33ms）輪詢繪製。表情/動作對應寫死在檔案頂端常數（`EXPR_*`、`MOTION_*`），目前模型是 `helper/assest/Frieren/`。
- **`helper/satellite.py`（`SatelliteRing`）**：點擊主圓圈展開的衛星選單，負責連結項目排列、展開動畫、目標解析與啟動（exe/lnk/資料夾/URL/帶參數指令列）。
- **`helper/usage.py`（`UsageMonitor`）**：背景輪詢 Claude Pro 用量 API（60 秒一次），透過 Qt signal（`updated`/`failed`/`incidentsUpdated`）回傳給 `Bubble` 畫圓環。
- **`helper/trigger.py`（`TriggerWatcher`）**：每 2 秒輪詢一個 trigger 資料夾（預設 `~/.claude-triggers`，由外部工具如 Claude Code hooks 寫入 json），依 `event` 欄位（`Stop`/`PreToolUse`/`PostToolUse`/`Notification`/`UserPromptSubmit`）發出對應 signal。`main.py` 依目前是否為 Live2D 模式決定要疊 GIF 特效（`Toast`/`ToolUseEffect`/`ThinkingEffect`/`NotificationEffect`，皆定義於 `trigger.py`）還是呼叫 `bubble.live2d_react(event)` 切換模型表情/動作。
- **`helper/settings_ui.py`（`SettingsDialog`）**：設定視窗，透過 signal（`gifChanged`/`displayModeChanged`/`linksChanged`/`usageChanged`/`triggerChanged`）通知 `main.py` 重新套用設定。
- **`helper/config.py`**：設定檔讀寫，路徑固定在 `%APPDATA%\desktop-helper-live2d\config.json`，讀取失敗或欄位缺漏一律回退到 `DEFAULTS`，不會讓程式啟動失敗。
- **`helper/autostart.py`**：寫入/移除 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 登錄檔項目。

### 資料流慣例

- 所有跨元件通訊走 Qt signal/slot，`HelperApp` 是唯一的 signal 接線點；元件之間不互相 import 對方的實例。
- 設定變更一律先寫回 `self.cfg`（記憶體）+ `config.save()`（落地），再由對應的 `_apply_*_cfg()` 方法把新值套用到元件上——新增設定欄位時遵循這個「cfg 更新 → save → apply」的三段式。
- 主圓圈拖曳時，衛星選單、吐司、特效視窗都要跟著位移，邏輯集中在 `main.py` 的 `_on_bubble_dragged`；新增會疊加在主圓圈附近的浮動視窗時要記得在這裡加上位移同步。
