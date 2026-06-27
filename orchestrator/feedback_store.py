"""中央 feedback 儲存。委員透過 Slack 1:1 / thread 給的回饋落在這。

架構轉向(見 memory architecture-centralized-feedback-loop):
  - 拿掉「user 用自己訂閱跑」;回饋不再是個人 overlay,而是進**中央** store。
  - 一隻排程 agent(feedback-synthesis)定期讀這裡,彙整成 rubric/skill 修改提案、開 PR,
    最後**由人覆核**才決定是否調整 skill(走 CODEOWNERS 人 merge 閘)。

為何用 append-only JSONL 在 .runtime/:
  - 回饋是高頻、暫存性的原始輸入,屬機密、不進 git(鐵律 #3);彙整後的「提案」才走 git/PR。
  - append-only 不覆寫,保留每一條原始回饋供合成與稽核。

落點:.runtime/feedback/<case_id>.jsonl(每行一條),外加 _index.jsonl 記全部(供合成掃描)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import config

FEEDBACK_DIR = config.runtime_dir / "feedback"


def _ensure() -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


def record_feedback(
    *,
    case_id: str | None,
    reviewer: str,
    text: str,
    source: str = "slack",
    target: str | None = None,
    when: str | None = None,
) -> dict:
    """記一條委員回饋。

    case_id:針對哪個審查 case(可為 None = 一般性回饋)。
    reviewer:Slack user id 或名稱。
    text:回饋內容。
    source:slack | local | …
    target:這條回饋指向的對象,如 finding id(sec-006)或 rubric_ref(sec-authn);選填。
    when:ISO 時間字串;預設由呼叫端傳(scripts 不可用 Date,故由呼叫端給或留空)。
    """
    _ensure()
    entry = {
        "case_id": case_id or "_general",
        "reviewer": reviewer,
        "text": text,
        "source": source,
        "target": target or "",
        "when": when or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
    }
    line = json.dumps(entry, ensure_ascii=False)
    # 寫到 per-case 檔 + 全域 index(append-only)
    with (FEEDBACK_DIR / f"{entry['case_id']}.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    with (FEEDBACK_DIR / "_index.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return entry


def all_feedback() -> list[dict]:
    """讀全部回饋(供 feedback-synthesis 掃描)。"""
    idx = FEEDBACK_DIR / "_index.jsonl"
    if not idx.exists():
        return []
    out = []
    for raw in idx.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def feedback_for_case(case_id: str) -> list[dict]:
    p = FEEDBACK_DIR / f"{case_id}.jsonl"
    if not p.exists():
        return []
    out = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return out


def summary() -> dict:
    """供 dashboard/UI:回饋總數、指向各 rubric 的次數。"""
    fb = all_feedback()
    by_target: dict[str, int] = {}
    for e in fb:
        t = e.get("target") or "(未指定)"
        by_target[t] = by_target.get(t, 0) + 1
    return {"total": len(fb), "by_target": by_target}
