"""Step 2 — 審查外圈(Python,確定性)。

這是「外圈」:有副作用、絕不能漏的事都在這——它們交給 Python 的迴圈/條件,
不交給 model「記得做」(CLAUDE.md 鐵律 #2)。

外圈職責:
  輪詢 queue → 佈置 case 工作區 → 叫起【一個】claude session 跑審查(內圈)
   → ★驗收產出完整性 → git commit → gh pr create → 回 Slack 貼 PR + @委員

內圈(不在這個檔):一個 claude session 用 subagent fan-out 跑
  intake → 4 顆 lens(各載自己 rubric)→ synthesize → verdict。
  定義在 skills/run-review/SKILL.md(thin shim,動態內容住 GitHub)。
  ※ 本垂直切片只跑 security 一顆 lens,且 inline 跑(不 spawn subagent)。

關鍵保險絲:model 做事、Python 驗收。開 PR 前先確定性檢查——
  findings/security.json 與 verdict/recommendation.md 都在?缺就不開 PR、回報缺哪顆。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import git_ops, queue
from .config import REPO_ROOT, config

# 本切片只跑 security;擴展到四維時把其餘加回並改用 Task fan-out。
LENSES = ["security"]
CLAUDE_TIMEOUT_SECONDS = 600


# --------------------------------------------------------------------------
# payload 判別(向後相容舊的 Slack payload)
# --------------------------------------------------------------------------
def _case_type(case: dict) -> str:
    """review | digest | reminder | patrol。舊 Slack payload 無此欄 → review。"""
    return case.get("type", "review")


def _source_type(case: dict) -> str:
    """slack | local。

    相容三種形狀:
      - 舊 Slack:source = {"slack_permalink": ...}            → slack
      - 新標記式:source = {"type": "local"|"slack", ...}       → 該 type
      - 純字串  :source = "local"                               → local
    """
    source = case.get("source")
    if isinstance(source, dict):
        if "type" in source:
            return source["type"]
        if "slack_permalink" in source:
            return "slack"
    if isinstance(source, str):
        return source
    return "slack"  # 預設當舊 Slack


def _local_source_dir(case: dict) -> Path | None:
    """local case 的來源檔目錄(若有)。"""
    source = case.get("source")
    if isinstance(source, dict) and source.get("dir"):
        return Path(source["dir"])
    return None


# --------------------------------------------------------------------------
# 佈置工作區
# --------------------------------------------------------------------------
WORKSPACE_SUBDIRS = ("files", "intake", "lenses/security", "findings", "verdict")


def setup_workspace(case: dict) -> Path:
    """建立 .runtime/workspace/<case_id>/ 結構並備好提交檔。回傳 workspace 路徑。

    - 一律 idempotent(可重跑同一 case)。
    - local 來源:從 source.dir 複製檔到 files/(copy 而非 symlink,來源被改/移仍穩)。
    - slack 來源:檔已由 listener 放在 files/,僅確認存在。
    - 無任何輸入檔 → 早點丟 ValueError,別空轉叫起 claude。
    """
    case_id = case["case_id"]
    ws = config.workspace_dir(case_id)
    for sub in WORKSPACE_SUBDIRS:
        (ws / sub).mkdir(parents=True, exist_ok=True)

    files_dir = ws / "files"
    if _source_type(case) == "local":
        src = _local_source_dir(case)
        if src is None or not src.is_dir():
            raise ValueError(f"local case 的 source.dir 無效:{src}")
        for f in sorted(src.iterdir()):
            if f.is_file():
                shutil.copy2(f, files_dir / f.name)

    present = [p for p in files_dir.iterdir() if p.is_file()]
    if not present:
        raise ValueError(f"工作區無任何提交檔可審:{files_dir}")
    return ws


# --------------------------------------------------------------------------
# ★完整性驗收(開 PR 前的保險絲)
# --------------------------------------------------------------------------
_FINDING_REQUIRED_KEYS = ("id", "severity", "title", "rationale", "recommendation")


def outputs_complete(workspace: Path) -> tuple[bool, list[str]]:
    """確定性驗收:每個 lens 都有 findings.json(且結構對)+ verdict 存在且非空。

    回傳 (ok, missing):missing 是人可讀的問題清單,讓 worker 回報「缺哪顆」。
    本切片只驗 security 一顆。手刻檢查,不引入 jsonschema。
    """
    missing: list[str] = []

    for lens in LENSES:
        fpath = workspace / "findings" / f"{lens}.json"
        if not fpath.exists():
            missing.append(f"findings/{lens}.json 不存在")
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            missing.append(f"findings/{lens}.json 非合法 JSON:{e}")
            continue
        if not isinstance(data, dict):
            missing.append(f"findings/{lens}.json 頂層不是物件")
            continue
        if "lens" not in data:
            missing.append(f"findings/{lens}.json 缺 lens 欄")
        if not isinstance(data.get("findings"), list):
            missing.append(f"findings/{lens}.json 的 findings 不是陣列")
        else:
            for i, item in enumerate(data["findings"]):
                if not isinstance(item, dict):
                    missing.append(f"findings/{lens}.json findings[{i}] 不是物件")
                    continue
                lacking = [k for k in _FINDING_REQUIRED_KEYS if k not in item]
                if lacking:
                    missing.append(
                        f"findings/{lens}.json findings[{i}] 缺必填欄:{', '.join(lacking)}"
                    )

    vpath = workspace / "verdict" / "recommendation.md"
    if not vpath.exists():
        missing.append("verdict/recommendation.md 不存在")
    elif vpath.stat().st_size == 0:
        missing.append("verdict/recommendation.md 是空的")

    return (not missing, missing)


# --------------------------------------------------------------------------
# 內圈:叫起一個 claude session 跑 run-review(security 切片)
# --------------------------------------------------------------------------
def _build_review_prompt(workspace: Path) -> str:
    """組內圈 prompt:inline run-review SKILL + 各「腦」檔絕對路徑 + 完成定義。

    為何 inline 而非 /run-review:skills/ 在 repo root,不在 .claude/skills/,
    headless 下 slash command 不會解析到(見 plan 的環境事實)。
    """
    skill_md = (REPO_ROOT / "skills" / "run-review" / "SKILL.md").read_text(encoding="utf-8")
    rubric_path = REPO_ROOT / "rubrics" / "review-security.md"
    lens_agent_path = REPO_ROOT / "agents" / "review-lens.md"
    schema_path = REPO_ROOT / "contracts" / "finding.schema.json"
    policy_path = REPO_ROOT / "contracts" / "verdict-policy.md"
    findings_out = workspace / "findings" / "security.json"
    verdict_out = workspace / "verdict" / "recommendation.md"

    return f"""你是專案上線審查的內圈執行者。照下面的 run-review skill 跑【security 一個維度】的審查。

本切片只跑 security 一顆 lens,直接 inline 跑(不要 spawn subagent / 不要用 Task)。

=== run-review SKILL(thin shim,逐步照做)===
{skill_md}
=== SKILL 結束 ===

## 這個 case 的絕對路徑
- 工作區:        {workspace}
- 提交檔(讀):  {workspace / "files"}
- security rubric(讀): {rubric_path}
- review-lens 骨架(讀): {lens_agent_path}
- finding schema(產出要符合): {schema_path}
- verdict policy(套用): {policy_path}

## 步驟(只做這些,做完就停)
1. 讀 {workspace / "files"} 下所有提交檔。
2. 讀 {rubric_path} 與 {lens_agent_path};只用 security 維度的 criteria。
3. 逐條對照 rubric 檢查提交,產出 findings,**寫到** `{findings_out}`,
   內容必須符合 {schema_path}:頂層 {{"lens": "security", "findings": [...]}},
   每條 finding 含 id / severity(blocker|high|medium|low|info)/ title / rationale /
   recommendation,有依據填 evidence、對應 rubric 填 rubric_ref;**沒有證據要明說「缺證據」,不要編**。
4. 套用 {policy_path},把 findings 權衡成 go / no-go / 帶條件 go,
   **寫到** `{verdict_out}`(markdown):推薦 + 理由 + 哪些必須人簽。

## 完成定義(務必達成才結束)
- `{findings_out}` 已寫出且符合 schema。
- `{verdict_out}` 已寫出且非空。
寫完這兩個檔就結束你的回合。
"""


def invoke_review(workspace: Path, case_id: str) -> subprocess.CompletedProcess:
    """subprocess 叫起 headless claude 跑內圈。回傳 CompletedProcess(供 log)。

    非零退出視為「軟失敗」:記 log,但仍交給 outputs_complete 把關——
    檔案可能在晚一步的錯誤前就寫好了。把關靠檔案,不靠退出碼(鐵律 #2)。
    """
    prompt = _build_review_prompt(workspace)
    argv = [
        config.claude_cmd,
        "-p", prompt,
        "--model", config.claude_model,
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep",
        "--add-dir", str(workspace),
        "--output-format", "json",
        "--append-system-prompt",
        "你是審查內圈。只寫進工作區的 findings/ 與 verdict/。"
        "不要 git commit、不要開 PR、不要貼 Slack——那是外圈的事。"
        "findings/security.json 與 verdict/recommendation.md 寫好且符合格式後就結束回合。",
    ]
    env = {**os.environ, "REVIEW_FETCH_LOCAL": "1"}
    print(f"[worker] 叫起 claude 審查 case={case_id}(timeout={CLAUDE_TIMEOUT_SECONDS}s)…")
    return subprocess.run(
        argv,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )


# --------------------------------------------------------------------------
# 回報(依來源分流;本切片 local→stdout,slack 留 TODO seam)
# --------------------------------------------------------------------------
def _report_incomplete(case: dict, missing: list[str]) -> None:
    detail = "\n  - ".join(missing)
    msg = f"⚠️ case {case['case_id']} 審查未完整,未開 PR。缺:\n  - {detail}"
    if _source_type(case) == "slack":
        # TODO: slack post for source==slack(slack_client 目前無 post 方法)
        print(f"[worker][slack-TODO] {msg}")
    else:
        print(f"[worker] {msg}")


def _report_scheduled(case: dict, result: str) -> None:
    """排程任務的回報。本切片印 stdout;未來 digest 可貼審查頻道。"""
    # TODO: 把 digest 摘要貼到審查頻道(source==slack/schedule 時)
    print(f"[worker] {result}")


def _report_done(case: dict, pr_result: str) -> None:
    msg = f"✅ case {case['case_id']} 審查完成 → {pr_result}"
    if _source_type(case) == "slack":
        # TODO: slack post + @reviewer for source==slack
        print(f"[worker][slack-TODO] {msg}")
    else:
        print(f"[worker] {msg}")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def _run_review_case(case: dict) -> None:
    """跑一個 review case 的完整內外圈。"""
    case_id = case["case_id"]
    ws = setup_workspace(case)

    proc = invoke_review(ws, case_id)
    if proc.returncode != 0:
        print(f"[worker] claude 退出碼 {proc.returncode}(軟失敗,仍驗收產出)")
        if proc.stderr:
            print(f"[worker] stderr 末段:{proc.stderr[-800:]}")

    ok, missing = outputs_complete(ws)
    if not ok:
        _report_incomplete(case, missing)
        return  # ★保險絲:產出不完整就不開 PR

    pr_result = git_ops.open_review_pr(case)
    _report_done(case, pr_result)


def run_once() -> bool:
    """撈一個 case 跑完整流程。回傳是否有處理到 case(供 main 排空判斷)。"""
    case = queue.claim_next()
    if case is None:
        return False

    ctype = _case_type(case)
    try:
        if ctype == "review":
            _run_review_case(case)
        else:
            # digest / reminder / patrol:排程任務,走同一條 dispatch(無 model,外圈做)。
            from . import scheduled_tasks
            handler = scheduled_tasks.HANDLERS.get(ctype)
            if handler is None:
                print(f"[worker] 未知 case type={ctype},略過。")
            else:
                result = handler(case)
                _report_scheduled(case, result)
        queue.mark_done(case["case_id"])
    except Exception:  # 硬失敗:留在 processing/ 供重撈,別 mark_done
        import traceback
        print(f"[worker] 處理 case {case.get('case_id')} 失敗,保留在 processing/ 供重試:")
        traceback.print_exc()
    return True


def _run_scheduled_tasks_if_due() -> None:
    """排程任務的時鐘 seam(user 選的「worker 內迴圈」排程)。

    未來在這裡看 wall-clock,到點就 queue.enqueue 一筆帶 type 的 payload
    (digest / reminder / patrol),讓它走同一條 run_once dispatch。
    本切片:no-op。
    """
    pass


def main() -> None:
    print(f"[worker] 啟動,poll={config.poll_interval}s,lenses={LENSES}")
    while True:
        worked = True
        while worked:  # 把 queue 排空
            worked = run_once()
        _run_scheduled_tasks_if_due()
        time.sleep(config.poll_interval)


if __name__ == "__main__":
    main()
