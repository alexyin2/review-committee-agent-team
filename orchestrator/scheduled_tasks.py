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


def run_feedback_synthesis(case: dict) -> str:
    """排程:彙整委員回饋 → 草擬 rubric/skill 修改提案(類 PR-skill 動作)。

    架構轉向(memory architecture-centralized-feedback-loop):中央定期跑這隻,把累積的
    Slack 1:1 回饋按指向的 rubric_ref 分組,產出「修改提案」草稿。
    **提案不自動套用** —— 由人覆核(走 skills/rubrics 的 CODEOWNERS 人 merge 閘)才生效。

    本切片做確定性彙整 + 產出提案草稿(.runtime/feedback/proposals/);把草稿變成真正的
    rubric diff + 開 PR 是更重的一步(可叫內圈 claude),屬後續。
    """
    from . import feedback_store

    fb = feedback_store.all_feedback()
    if not fb:
        return "🧩 feedback-synthesis:目前沒有累積回饋,無提案。"

    # 按 target(rubric_ref / finding id)分組
    groups: dict[str, list[dict]] = {}
    for e in fb:
        key = e.get("target") or "(未指定)"
        groups.setdefault(key, []).append(e)

    proposals_dir = REPO_ROOT / ".runtime" / "feedback" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    generated_at = case.get("generated_at", "(scheduled)")

    proposals = []
    for target, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines = [
            f"# Skill 修改提案 — {target}",
            "",
            f"> 由 feedback-synthesis 於 {generated_at} 自動彙整,**待人覆核**。",
            f"> 來源:{len(items)} 條委員回饋。是否調整 rubric/skill 由人 merge 決定(CODEOWNERS)。",
            "",
            "## 彙整的回饋",
            "",
        ]
        for e in items:
            lines.append(f"- 「{e['text']}」 — {e['reviewer']}（{e.get('when','')}，case {e['case_id']}）")
        lines += [
            "",
            "## 建議動作(草案)",
            "",
            f"- 檢視 `rubrics/` 中對應 `{target}` 的條目,評估是否依上述回饋調整判準或補充要求。",
            "- 若採納:開 PR 修改 rubric → 指定委員 merge,下次審查自動吃新版(thin-shim)。",
            "- 若不採納:在本提案註記原因後關閉。",
            "",
        ]
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in target)
        path = proposals_dir / f"{slug}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        proposals.append({"target": target, "count": len(items), "path": str(path)})

    head = (f"🧩 feedback-synthesis:從 {len(fb)} 條回饋彙整出 {len(proposals)} 份 skill 修改提案"
            f"(待人覆核)。")
    detail = "；".join(f"{p['target']}（{p['count']} 條）" for p in proposals)
    return head + "\n  提案:" + detail


def run_poll_inbox(case: dict) -> str:
    """前門輪詢:撈各通道新 @mention → 收進 case_store → 丟 case-activity 信號。

    pull 不被 push(見 memory poll-not-push-channel-adapters)。本切片用 Slack adapter;
    無 token 時 adapter 回空(離線可測)。Teams(Graph)adapter 之後接上,同一條路。
    這層純機械,不叫 model;判斷由 worker 對 case-activity 信號叫 Claude 做。
    """
    from . import inbox

    adapter = inbox.SlackInboxAdapter()
    summary = inbox.poll_inbox(adapter)
    return (f"📥 poll-inbox（{summary['adapter']}）:新訊息 {summary['mentions']} 則，"
            f"觸及 case {summary['cases_touched']} 個。")


def run_reminder(case: dict) -> str:
    """逾期審查提醒(骨架)。未來:掃 awaiting-signoff 超過 N 天 → @委員。"""
    return "⏰ reminder 任務尚未實作(骨架)。"


def run_patrol(case: dict) -> str:
    """未觸發提交巡檢(骨架)。未來:掃 SharePoint/OneDrive 找沒走前門的提交。"""
    return "🔍 patrol 任務尚未實作(骨架)。"


# worker.run_once 依 type 查這張表
HANDLERS = {
    "digest": run_digest,
    "feedback-synthesis": run_feedback_synthesis,
    "poll-inbox": run_poll_inbox,
    "reminder": run_reminder,
    "patrol": run_patrol,
}
