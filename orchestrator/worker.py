"""Step 2 — 審查外圈(Python,確定性)。

這是「外圈」:有副作用、絕不能漏的事都在這——它們交給 Python 的迴圈/條件,
不交給 model「記得做」(CLAUDE.md 鐵律 #2)。

外圈職責:
  輪詢 queue → 佈置 case 工作區 → 叫起【一個】claude session 跑審查(內圈)
   → ★驗收產出完整性 → git commit → gh pr create → 回 Slack 貼 PR + @委員

內圈(不在這個檔):一個 claude session 用 subagent fan-out 跑
  intake → 4 顆 lens(各載自己 rubric)→ synthesize → verdict。
  定義在 skills/run-review/SKILL.md(thin shim,動態內容住 GitHub)。

關鍵保險絲:model 做事、Python 驗收。開 PR 前先確定性檢查——
  4 個 findings.json 都在?verdict 產出了?缺就不開 PR、回報缺哪顆。
"""

# from . import queue, slack_client, git_ops, config
# import subprocess, json, pathlib

LENSES = ["security", "privacy", "legal", "ops"]


def run_once() -> None:
    """撈一個 case 跑完整流程。"""
    # case = queue.claim_next()
    # if case is None: return
    # workspace = setup_workspace(case)            # 佈置:rubric 切片 + 提交副本
    # invoke_review(workspace)                       # 內圈:subprocess claude -p ... (run-review skill)
    # if not outputs_complete(workspace):           # ★完整性檢查
    #     slack_client.post(...,"審查未完整,缺:..."); return
    # pr_url = git_ops.open_review_pr(case)          # commit findings+verdict → gh pr create
    # slack_client.post(case.channel, f"審查完成:{pr_url}\n請 {mention(reviewer)} 檢查並裁決",
    #                   thread_ts=case.thread_ts)
    # queue.mark_done(case.case_id)
    raise NotImplementedError("Step 2:見檔頭職責清單")


def outputs_complete(workspace: str) -> bool:
    """確定性驗收:每個 lens 都有 findings.json 且 verdict 存在。缺一不可。"""
    raise NotImplementedError


def main() -> None:
    # while True: run_once(); sleep(poll_interval)
    raise NotImplementedError


if __name__ == "__main__":
    main()
