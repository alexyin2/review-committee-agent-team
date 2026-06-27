"""排程觸發入口:把一筆 typed 排程任務丟進**同一條** queue。

設計(plan):排程觸發 = 把帶 type 的 payload enqueue,讓它走 worker 的同一條 dispatch。
本機可由 launchd / cron 在固定時間叫起:
    python -m orchestrator.scheduler daily-digest
也可手動觸發做 demo。

對照「worker 內迴圈排程」(user 選的):正式上線時時鐘 seam 在 worker.main 的
_run_scheduled_tasks_if_due() 裡;這支 CLI 提供「外部排程器/手動」這條等價路徑,
兩者最終都只是 enqueue 一筆 type=digest|reminder|patrol 的 payload。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from . import queue
from .config import config

JOBS = {
    "daily-digest": "digest",
    "overdue-reminder": "reminder",
    "submission-patrol": "patrol",
}


def _make_job_id(job_type: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m%d-%H%M%S")
    return f"{ts}-SCHED-{job_type.upper()}"


def enqueue_job(job_name: str) -> str:
    job_type = JOBS[job_name]
    case_id = _make_job_id(job_type)
    payload = {
        "case_id": case_id,
        "type": job_type,
        "source": {"type": "schedule", "job": job_name},
        "submitter": "scheduler",
        "lenses": config.review_lenses,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
    }
    queue.enqueue(case_id, payload)
    return case_id


def main() -> None:
    parser = argparse.ArgumentParser(description="排程觸發:把一筆任務丟進 queue。")
    parser.add_argument("job", choices=sorted(JOBS), help="要排的任務")
    parser.add_argument("--enqueue-only", action="store_true",
                        help="只入列,不立刻跑 worker(交給常駐 worker)。")
    args = parser.parse_args()

    case_id = enqueue_job(args.job)
    print(f"[scheduler] 已入列排程任務 {args.job}（type={JOBS[args.job]}）case={case_id}")

    if args.enqueue_only:
        print("[scheduler] --enqueue-only:交給常駐 worker 處理。")
        return

    from . import worker
    print("[scheduler] 同步跑一次 worker.run_once()…")
    worker.run_once()


if __name__ == "__main__":
    main()
