"""離線冒煙測試:不需 Slack token,驗證 config 路徑 + queue 收發。

跑法(repo 根目錄):
    python -m orchestrator.smoke_test
這只測「機械骨架」是否健康;真正的 Slack 端到端要 token + 啟動 listener。
"""

from __future__ import annotations

from . import queue
from .config import config


def main() -> None:
    print(f"[smoke] repo root  = {config.runtime_dir.parent}")
    print(f"[smoke] runtime dir = {config.runtime_dir}")
    print(f"[smoke] queue dir   = {config.queue_dir}")

    case_id = "0000-0000-000000-CSMOKE"
    payload = {
        "case_id": case_id,
        "source": {"slack_permalink": "(smoke)"},
        "channel": "CSMOKE",
        "submitter": "USMOKE",
        "files": [{"name": "demo.pdf", "sha256": "deadbeef"}],
    }

    path = queue.enqueue(case_id, payload)
    print(f"[smoke] enqueued -> {path}")
    assert path.exists(), "enqueue 沒寫出檔"

    claimed = queue.claim_next()
    assert claimed is not None, "claim_next 撈不到剛入列的 case"
    assert claimed["case_id"] == case_id, "撈到的 case_id 不符"
    print(f"[smoke] claimed  -> {claimed['case_id']} (moved to processing/)")

    queue.mark_done(case_id)
    print(f"[smoke] done     -> moved to done/")

    # 清掉 done 裡的測試檔,保持乾淨
    (queue.DONE / f"{case_id}.json").unlink(missing_ok=True)
    print("[smoke] PASS ✅  config + queue 機械骨架健康")


if __name__ == "__main__":
    main()
