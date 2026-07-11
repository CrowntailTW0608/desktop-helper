"""Live2D 角色註冊表：新增角色只需在此新增一筆設定，不必改動 live2d_view.py。"""

import os

ASSET_ROOT = os.path.join(os.path.dirname(__file__), "assest")

DEFAULT_CHARACTER = "frieren"

# idle：待機時輪流播放的 (group, index) 清單，只有一筆時等同單一待機動作。
# reactions：{trigger 事件名稱: {"expression": 表情名, "motion": {"group", "index", "priority", "hold"}, "reset": True, "idle": True}}
#   trigger 事件名稱對應 helper/trigger.py 的 event 欄位（UserPromptSubmit/PreToolUse/PostToolUse/Stop），
#   另外 "Clicked" 對應主圓圈被點擊（main.py 的 _on_bubble_clicked）。
#   key 也可以寫成 "事件名稱:tool_name"（例如 "PreToolUse:AskUserQuestion"），這樣同一個事件
#   但不同 tool_name 可以有專屬反應；沒有對應的專屬 key 才會退回用純事件名稱的一般反應。
#   "idle": True 會立即中斷目前動作、回到 idle 清單播放（PostToolUse 常用此項回歸待機）。
#   "hold"：素材動作多為 Loop=True，動作本身不會觸發 onFinish，需標明秒數（通常填 motion3.json 的
#   Meta.Duration）才能在播放完後自動計時切回 idle；沒填就是播完（若真的會結束）或一直播到下個事件蓋過。
#   "sticky": True：明確表示這個動作要播到下個事件（通常是對應的結束事件，如 PreToolUse 對
#   PostToolUse）才會離開，即使素材播完一輪也不會自己回 idle；用在「一定要等對應事件來才結束」的場合，
#   不依賴素材本身是否真的 Loop=True。
#   "repeat"：搭配 sticky 使用，每隔幾秒重播一次同一個動作（通常填該動作 motion3.json 的
#   Meta.Duration），避免等待期間停在最後一幀不動；不填就維持停格，直到下個事件蓋過。
#   缺項代表該事件不觸發任何動作/表情。
CHARACTERS = {
    "frieren": {
        "name": "Frieren",
        "model_path": os.path.join("Frieren", "Frieren", "Frieren.model3.json"),
        "idle": [{"group": "", "index": 0}],
        "reactions": {
            "UserPromptSubmit": {"expression": "lks"},
            "PreToolUse": {"expression": "wh"},
            "PostToolUse": {"reset": True},
            "PreCompact": {"expression": "han"},
            "Stop": {
                "expression": "anya",
                "motion": {"group": "", "index": 1, "priority": "FORCE", "hold": 2.317},
            },
        },
    },
    "mao": {
        "name": "Mao (zh-Hans)",
        "model_path": os.path.join("mao_zh-Hans", "runtime", "mao_pro.model3.json"),
        "idle": [{"group": "Idle", "index": 0}, {"group": "", "index": 0}],
        "reactions": {
            "UserPromptSubmit" : {"motion": {"group": "", "index": 2}},
            "PreToolUse": {"motion": {"group": "", "index": 3, "sticky": True, "repeat": 7.8}},
            "PreToolUse:AskUserQuestion": {"motion": {"group": "", "index": 1, "sticky": True, "repeat": 4.0}},
            "PostToolUse": {"idle": True},
            "PreCompact": {"motion": {"group": "", "index": 4}, "expression": "exp_08"},
            "Stop": {"motion": {"group": "", "index": 5, "hold": 9.23}},
            "Clicked": {"motion": {"group": "", "index": 1},"reset": True},
        },
    },
}


def model_path(character_id: str) -> str:
    return os.path.join(ASSET_ROOT, CHARACTERS[character_id]["model_path"])
