# Desktop Helper

桌面圓形小幫手，靈感來自過去 Microsoft Office 的迴紋針助理。主體是一顆常駐桌面、永遠置頂的圓形視窗，可播放自訂 GIF；點擊後展開衛星圓圈，作為應用程式快速啟動器；外圍三層圓環即時顯示 Claude Pro 用量。

完整功能規格見 [specification.md](specification.md)。

---

## 功能總覽

- **主圓圈**：顯示自訂 GIF（可為單一檔案，或指向資料夾自動隨機輪播），永遠置頂、可拖曳、位置自動記憶。
- **衛星選單**：點擊主圓圈展開，支援四種連結目標：
  - 執行檔／捷徑（`.exe`、`.lnk`）
  - 資料夾
  - 網址（`http://`、`https://`）
  - 帶參數的指令列，例如 `"C:\...\chrome.exe" --profile-directory="Profile 7"`（執行檔路徑需以雙引號括住）
  - 連結清單在設定視窗中可拖曳調整順序，最多 8 個，展開時另附一個固定的齒輪衛星。
- **Claude 用量圓環**：主圓圈外圍三層圓環，由內而外為 Current Session（5hr）、特定模型 Weekly（7d）、Weekly Limit（7d）；弧長 = 用量百分比，顏色依嚴重度變化，並以白色基準線標示「若均勻消耗應落在的位置」。滑鼠懸停或在主圓圈按右鍵可查看詳細數字與 reset 倒數。
- **系統匣**：右鍵選單可顯示/隱藏小幫手、開啟設定、結束程式。
- **開機自動啟動**：設定視窗一鍵開關。

---

## 事前準備

1. 電腦已安裝 **Python 3.14**（開發環境為 3.14.6；PySide6 6.11 支援 Python 3.10～3.14）
2. 已安裝 [uv](https://docs.astral.sh/uv/)（用於建立虛擬環境與安裝套件）

---

## 安裝

在專案資料夾開啟 PowerShell：

```powershell
uv venv .venv
uv pip install -r requirements.txt
```

---

## 啟動

```powershell
.venv\Scripts\python main.py
```

背景常駐執行（不跳出主控台視窗）：

```powershell
.venv\Scripts\pythonw main.py
```

---

## 操作說明

| 操作 | 功能 |
|------|------|
| 單擊主圓圈 | 展開／收合衛星選單 |
| 按住主圓圈拖曳 | 移動小幫手位置（下次啟動保留） |
| 在主圓圈按右鍵 | 立即顯示 Claude 用量詳情 |
| 滑鼠懸停主圓圈 | 顯示 Claude 用量詳情 |
| 點擊衛星 | 開啟對應的應用程式／資料夾／網址 |
| 點擊齒輪衛星 | 開啟設定視窗 |
| 系統匣圖示右鍵 | 顯示/隱藏小幫手、開啟設定、結束程式 |

---

## 設定 Claude 用量顯示

1. 開啟設定視窗（點齒輪衛星，或系統匣選單「設定…」）
2. 在「Claude 用量」區塊勾選「啟用用量顯示」
3. 填入 `Session Key` 與 `Org ID`：
   - 用 Chrome 或 Edge 登入 [claude.ai](https://claude.ai)，按 **F12** 開啟開發人員工具
   - **Application** 分頁 → **Cookies** → `https://claude.ai` → 複製 `sessionKey` 的值（以 `sk-ant-sid` 開頭）
   - **Network** 分頁 → 重新整理頁面 → 搜尋 `usage` → 點該筆請求 → **Headers** 的 Request URL 中間那段 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` 即為 Org ID

> Session Key 有時效限制，過期需重新取得並更新設定。小幫手在連續失敗 3 次（約 3 分鐘）後才會將圓環轉灰並提示錯誤，偶發的單次失敗不影響顯示。

---

## 設定檔

位置：`%APPDATA%\desktop-helper\config.json`

刪除或內容毀損時，程式會自動以預設值重建，不影響啟動。詳細欄位說明見 [specification.md](specification.md#51-設定檔)。

---

## 專案結構

```
desktop-helper/
├── main.py                 # 進入點：組裝主圓圈、衛星、用量監控、系統匣
├── requirements.txt
├── helper/
│   ├── bubble.py            # 主圓圈：GIF 播放/輪播、拖曳、用量圓環繪製
│   ├── satellite.py         # 衛星圓圈：排列、展開動畫、目標解析與啟動
│   ├── usage.py              # Claude 用量：API 取得、60 秒背景輪詢
│   ├── settings_ui.py        # 設定視窗
│   ├── config.py             # 設定檔讀寫
│   └── autostart.py          # 開機自動啟動（登錄檔）
└── specification.md
```

---

## 常見問題

**Q：用量圓環一直是灰色**
> 檢查設定視窗中的 Session Key／Org ID 是否正確；若持續失敗（非偶發單次），代表 Session Key 可能已過期，請依「設定 Claude 用量顯示」重新取得。

**Q：點衛星沒反應或顯示找不到目標**
> 確認連結路徑仍然存在；若是帶參數的指令列，執行檔路徑務必用雙引號括住。

**Q：開機自動啟動沒生效**
> 開關會寫入登錄檔 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，可用登錄檔編輯器確認是否有 `DesktopHelper` 項目。
