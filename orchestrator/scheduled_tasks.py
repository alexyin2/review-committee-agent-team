"""排程任務的實作(走同一條 queue / worker dispatch)。

設計(design §6.1 + plan):排程任務和 Slack/local 觸發**共用同一條 queue**;
差別只在「誰把 typed payload 丟進去」。worker.run_once 依 case['type'] 分派到這裡。

本切片先做最有感的一顆:**daily-digest**——重算 dashboard + 印出摘要。
digest / reminder / patrol 都是**無 model 的機械任務**(讀已 commit 狀態 → 算 → 回報),
所以放外圈、不叫內圈 claude。

reminder / patrol 先留可呼叫的骨架,回報「尚未實作」。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_digest(case: dict) -> str:
    """每日 digest:重算 DASHBOARD.md,回傳一段人可讀摘要(供回報/Slack)。"""
    sys.path.insert(0, str(REPO_ROOT))
    from scripts import generate_dashboard as dash

    lenses = case.get("lenses") or ["security"]
    state = dash.collect_state(lenses)
    generated_at = case.get("generated_at", "(scheduled digest)")
    md = dash.render_markdown(state, generated_at=generated_at)
    out = REPO_ROOT / "DASHBOARD.md"
    out.write_text(md, encoding="utf-8")

    summary = (
        f"📊 每日 digest:待人簽 {len(state['awaiting'])} 件、"
        f"已裁決 {len(state['decided'])} 件、"
        f"rubric 近 30 天變更 {len(state['rubric_changes'])} 次。"
        f"DASHBOARD.md 已更新。"
    )
    if state["awaiting"]:
        names = "、".join(f"{c['case_id']}({c['verdict']})" for c in state["awaiting"])
        summary += f"\n  待簽:{names}"
    return summary


def run_reminder(case: dict) -> str:
    """逾期審查提醒(骨架)。未來:掃 awaiting-signoff 超過 N 天 → @委員。"""
    return "⏰ reminder 任務尚未實作(骨架)。"


def run_patrol(case: dict) -> str:
    """未觸發提交巡檢(骨架)。未來:掃 SharePoint/OneDrive 找沒走前門的提交。"""
    return "🔍 patrol 任務尚未實作(骨架)。"


# worker.run_once 依 type 查這張表
HANDLERS = {
    "digest": run_digest,
    "reminder": run_reminder,
    "patrol": run_patrol,
}
