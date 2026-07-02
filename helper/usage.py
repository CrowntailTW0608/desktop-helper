"""Claude 用量：API 取得與 60 秒輪詢（移植自 claude-usage-widget）"""

import threading
from datetime import datetime, timedelta, timezone

import requests
from PySide6.QtCore import QObject, QTimer, Signal

REFRESH_MS = 60_000
# 連續失敗達此次數才對外報錯；偶發的 401/403（Cloudflare 抖動）不干擾顯示
FAIL_THRESHOLD = 3
# 圓環由內而外的順序（FR-24）
RING_ORDER = ("session", "weekly_scoped", "weekly_all")
LABELS = {"session": "Session (5hr)", "weekly_all": "Weekly (7d)"}
WINDOW_HOURS = {"session": 5, "weekly_scoped": 24 * 7, "weekly_all": 24 * 7}


def fetch_usage(session_key: str, org_id: str) -> dict:
    url = f"https://claude.ai/api/organizations/{org_id}/usage"
    headers = {
        "Cookie": f"sessionKey={session_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://claude.ai//settings",
    }
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def format_reset_time(iso_str) -> str:
    """把 UTC 時間轉成本地時間並格式化"""
    if not iso_str:
        return "—"
    dt = datetime.fromisoformat(iso_str).astimezone()
    now = datetime.now(timezone.utc).astimezone()
    total_minutes = int((dt - now).total_seconds() / 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours > 0:
        remaining = f"Reset in {hours}hr {minutes}min"
    else:
        remaining = f"Reset in {minutes}min"
    return f"{dt.strftime('%m/%d %H:%M')} ({remaining})"


def elapsed_percent(resets_at, window_hours: float):
    """目前時間在整個視窗（reset 往前推 window_hours）中的經過百分比；無資料回傳 None。"""
    if not resets_at:
        return None
    end = datetime.fromisoformat(resets_at).astimezone()
    now = datetime.now(timezone.utc).astimezone()
    window = timedelta(hours=window_hours)
    start = end - window
    pct = (now - start).total_seconds() / window.total_seconds() * 100
    return max(0.0, min(100.0, pct))


def parse_limits(data: dict) -> list:
    """把 API 回應整理成圓環用的清單（由內而外排序）。"""
    items = {}
    for lim in data.get("limits", []):
        kind = lim.get("kind")
        if kind not in RING_ORDER:
            continue
        if kind == "weekly_scoped":
            model = (lim.get("scope") or {}).get("model") or {}
            label = f"{model.get('display_name', 'Model')} (7d)"
        else:
            label = LABELS[kind]
        items[kind] = {
            "label": label,
            "percent": lim.get("percent", 0),
            "severity": lim.get("severity", "normal"),
            "resets_at": lim.get("resets_at"),
            "elapsed": elapsed_percent(lim.get("resets_at"), WINDOW_HOURS[kind]),
        }
    return [items[k] for k in RING_ORDER if k in items]


class UsageMonitor(QObject):
    """每 60 秒於背景執行緒取得用量（FR-26），成功發 updated、失敗發 failed。"""

    updated = Signal(list)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self._poll)
        self._key = ""
        self._org = ""
        self._fail_count = 0

    def configure(self, enabled: bool, session_key: str, org_id: str) -> None:
        self._key, self._org = session_key, org_id
        self._fail_count = 0
        if enabled and session_key and org_id:
            self._timer.start()
            self._poll()
        else:
            self._timer.stop()

    def _poll(self) -> None:
        key, org = self._key, self._org

        def work():
            try:
                items = parse_limits(fetch_usage(key, org))
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (401, 403):
                    self._on_fail(
                        f"HTTP {status}：驗證被拒。若持續發生，請至設定更新 Session Key"
                    )
                else:
                    self._on_fail(f"HTTP {status}")
            except Exception as e:
                self._on_fail(str(e)[:60])
            else:
                self._fail_count = 0
                self.updated.emit(items)

        threading.Thread(target=work, daemon=True).start()

    def _on_fail(self, msg: str) -> None:
        """暫時性失敗先容忍、保留上次資料；連續達門檻才對外報錯。"""
        self._fail_count += 1
        if self._fail_count >= FAIL_THRESHOLD:
            self.failed.emit(msg)
