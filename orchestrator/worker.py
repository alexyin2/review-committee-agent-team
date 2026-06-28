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

from . import case_store, git_ops, queue, slack_client
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
    """slack | local | inbox。

    相容多種形狀:
      - 舊 Slack:source = {"slack_permalink": ...}                  → slack
      - 新標記式:source = {"type": "local"|"slack"|"inbox", ...}     → 該 type
      - 純字串  :source = "local"                                     → local
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


def _fetch_docs(case: dict, files_dir: Path) -> None:
    """inbox 來源:把 case 的 doc_links 拓一份臨時副本進 files_dir(用完即拋,不進 git)。

    本切片支援的連結:
      - 本機路徑 / file:// → 直接複製(供離線測試與 local fast path)。
      - http(s) OneDrive/SharePoint → 待接 Graph(需 Azure 認證);本切片記 log 跳過。
    attachment 退路:listener 路徑已把附檔放在 files_dir,這裡不覆蓋。
    """
    for link in case.get("doc_links", []) or []:
        path_str = link[7:] if link.startswith("file://") else link
        p = Path(path_str).expanduser()
        if p.is_file():
            shutil.copy2(p, files_dir / p.name)
        elif p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file():
                    shutil.copy2(f, files_dir / f.name)
        else:
            print(f"[worker] doc_link 待 Graph 接線、本切片跳過:{link}")


def setup_workspace(case: dict, fresh: bool = False) -> Path:
    """建立 .runtime/workspace/<case_id>/ 結構並備好提交檔。回傳 workspace 路徑。

    - 一律 idempotent(可重跑同一 case)。
    - fresh=True(改版重審):先清 findings/verdict/intake,避免讀到上一版殘檔。
    - local 來源:從 source.dir 複製檔到 files/(copy 而非 symlink,來源被改/移仍穩)。
    - inbox 來源:從 doc_links 拓臨時副本(見 _fetch_docs);attachment 為退路。
    - slack 來源:檔已由 listener 放在 files/,僅確認存在。
    - 無任何輸入檔 → 丟 ValueError(呼叫端決定怎麼回報,別空轉叫起 claude)。
    """
    case_id = case["case_id"]
    ws = config.workspace_dir(case_id)
    if fresh:
        for sub in ("findings", "verdict", "intake"):
            shutil.rmtree(ws / sub, ignore_errors=True)
    for sub in WORKSPACE_SUBDIRS:
        (ws / sub).mkdir(parents=True, exist_ok=True)

    files_dir = ws / "files"
    src_type = _source_type(case)
    if src_type == "local":
        src = _local_source_dir(case)
        if src is None or not src.is_dir():
            raise ValueError(f"local case 的 source.dir 無效:{src}")
        for f in sorted(src.iterdir()):
            if f.is_file():
                shutil.copy2(f, files_dir / f.name)
    elif src_type == "inbox":
        _fetch_docs(case, files_dir)

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
# 回報(reporter seam:有 thread 就貼回對話,否則 print;無 token 時 post_thread 自降級)
# --------------------------------------------------------------------------
def _reply(case: dict, text: str) -> None:
    """把一段話送回 case 所在的 thread。

    reporter seam:綁了 thread 的 case → slack_client.post_thread(無 token 時自動印出);
    沒有 thread 的(local / schedule)→ 直接 print。取代舊的 [slack-TODO] 樁。
    """
    channel = case.get("channel", "")
    thread_id = case.get("thread_id") or case.get("thread_ts") or ""
    if channel and thread_id:
        slack_client.post_thread(channel, thread_id, text)
    else:
        print(f"[worker] {text}")


def _report_incomplete(case: dict, missing: list[str]) -> None:
    detail = "\n  - ".join(missing)
    _reply(case, f"⚠️ case {case['case_id']} 審查未完整,未開 PR。缺:\n  - {detail}")


def _report_scheduled(case: dict, result: str) -> None:
    """排程任務的回報(digest / poll-inbox 等);這些沒有對話 thread,印 stdout。"""
    print(f"[worker] {result}")


def _report_done(case: dict, pr_result: str) -> None:
    _reply(case, f"✅ case {case['case_id']} 審查完成 → {pr_result}")


# --------------------------------------------------------------------------
# 對話式 case:叫大腦(Claude 讀 brief)→ 兌現承諾(Python 執行+驗收)
# --------------------------------------------------------------------------
# 行動計畫 schema:Claude 只輸出意圖,副作用一律 Python 做(見 agents/case-agent.md)。
_ACTION_PLAN_KEYS = ("reply_text", "run_review", "crystallize_pr", "new_status_note", "reasoning")


def _build_case_agent_prompt(state: dict) -> str:
    """組「大腦」prompt:inline case-agent brief + 這個 case 的對話 context + 既有理解。

    與 _build_review_prompt 同精神(inline brief,不靠 slash command),但這是
    對話判斷層,不是審查層——輸出是行動計畫 JSON,不碰檔案。
    """
    brief = (REPO_ROOT / "agents" / "case-agent.md").read_text(encoding="utf-8")
    context_lines = "\n".join(
        f"  [{m.get('ts','')}] {m.get('user','?')}: {m.get('text','')}"
        for m in state.get("context", [])
    ) or "  (尚無對話)"
    doc_links = "\n".join(f"  - {l}" for l in state.get("doc_links", [])) or "  (無)"

    return f"""{brief}

=== 這個 case 的現況 ===
case_id: {state.get('case_id')}
version: {state.get('version')}（已產出過 verdict 草稿:{'是' if state.get('draft_msg_ts') else '否'}）
你上次的理解 status_note: {state.get('status_note') or '(無)'}
文件連結 doc_links:
{doc_links}

對話 context（依時間）:
{context_lines}

=== 你的任務 ===
依 brief 判斷下一步,**只**輸出一個 JSON 行動計畫(不要任何其他文字、不要 markdown code fence）:
{{"reply_text": "...", "run_review": false, "crystallize_pr": false, "new_status_note": "...", "reasoning": "..."}}
"""


def _parse_action_plan(raw: str) -> dict:
    """從 Claude 輸出抽出行動計畫 JSON;寬鬆容忍包了 code fence 或前後雜訊。"""
    text = raw.strip()
    # 去掉可能的 ```json ... ``` 包裝
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
    # 取第一個 { 到最後一個 } 之間
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    plan = json.loads(text)
    # 正規化:補預設,避免下游 KeyError
    return {
        "reply_text": plan.get("reply_text", ""),
        "run_review": bool(plan.get("run_review", False)),
        "crystallize_pr": bool(plan.get("crystallize_pr", False)),
        "new_status_note": plan.get("new_status_note", ""),
        "reasoning": plan.get("reasoning", ""),
    }


def _decide(state: dict) -> dict:
    """叫起 Claude 讀 brief + context,回傳行動計畫 dict。

    這是「路徑」層(model 推理)。測試可 monkeypatch 此函式餵假行動計畫,
    驗證下游「承諾」層(Python 兌現)而不真叫 model。
    """
    prompt = _build_case_agent_prompt(state)
    argv = [
        config.claude_cmd,
        "-p", prompt,
        "--model", config.claude_model,
        "--output-format", "json",
        "--append-system-prompt",
        "你是審查同事的對話大腦。只輸出一個 JSON 行動計畫,不要開 PR / commit / 貼訊息——"
        "那些是外圈 Python 的事。你只在 JSON 裡『請求』。",
    ]
    proc = subprocess.run(
        argv, cwd=str(REPO_ROOT), capture_output=True, text=True,
        timeout=CLAUDE_TIMEOUT_SECONDS,
    )
    # claude --output-format json 會把模型輸出包在 {"result": "..."} 裡;容忍兩種
    out = proc.stdout.strip()
    try:
        wrapper = json.loads(out)
        inner = wrapper.get("result", out) if isinstance(wrapper, dict) else out
    except json.JSONDecodeError:
        inner = out
    return _parse_action_plan(inner)


def _execute_action_plan(case: dict, state: dict, plan: dict) -> None:
    """★承諾層:逐項兌現行動計畫,Python 做副作用 + 驗收。絕不讓 model 直接開 PR。

    順序:跑審查(若請求)→ 回貼 reply → 結晶 PR(若請求且產出齊全)→ 持久化理解。
    """
    case_id = case["case_id"]

    # 1) run_review:跑(或重跑)審查;Python 做完整性驗收,缺就不往下走
    review_ok = False
    if plan["run_review"]:
        ws = setup_workspace(case, fresh=(state.get("version", 0) > state.get("reviewed_version", -1)))
        proc = invoke_review(ws, case_id)
        if proc.returncode != 0:
            print(f"[worker] claude 退出碼 {proc.returncode}(軟失敗,仍驗收產出)")
            if proc.stderr:
                print(f"[worker] stderr 末段:{proc.stderr[-800:]}")
        ok, missing = outputs_complete(ws)
        if ok:
            review_ok = True
            state["reviewed_version"] = state.get("version", 0)
        else:
            _report_incomplete(case, missing)

    # 2) reply_text:把話貼回 thread(reporter seam)
    if plan["reply_text"]:
        _reply(case, plan["reply_text"])

    # 3) crystallize_pr:★只有 Python 決定才開——且必須有齊全產出(鐵律 #1)
    if plan["crystallize_pr"]:
        ws = config.workspace_dir(case_id)
        ok, missing = outputs_complete(ws)
        if ok:
            pr_result = git_ops.open_review_pr(case)
            _report_done(case, pr_result)
        else:
            _report_incomplete(case, missing)

    # 4) 持久化 Claude 的最新理解(跨輪記憶)
    if plan["new_status_note"]:
        state["status_note"] = plan["new_status_note"]
    case_store.save(case_id, state)


def _handle_case_activity(signal: dict) -> None:
    """對話式 case 的一輪:load + drain → 叫大腦 → 兌現承諾。

    signal 是 inbox.enqueue_case_activity 丟的輕量信號;真正的 context 在 case_store。
    """
    case_id = signal["case_id"]
    state = case_store.load(case_id)
    if state is None:
        print(f"[worker] 孤兒 case-activity 信號(state 不存在):{case_id},丟棄。")
        return

    case_store.drain_inbox(case_id)
    state = case_store.load(case_id)  # drain 後重讀,拿到累積的 context

    # 把 case_store state 補成 review pipeline 認得的 case 形狀(channel/thread/source)
    case = {
        "case_id": case_id,
        "channel": state.get("channel", ""),
        "thread_id": state.get("thread_id", ""),
        "submitter": state.get("submitter", ""),
        "source": {"type": "inbox", "thread_id": state.get("thread_id", "")},
        "doc_links": state.get("doc_links", []),
        "files": [],
        "version": state.get("version", 0),
        "status_note": state.get("status_note", ""),
        "created_at": state.get("created_at", ""),
    }

    plan = _decide(state)
    print(f"[worker] case {case_id} 行動計畫:run_review={plan['run_review']} "
          f"crystallize_pr={plan['crystallize_pr']} reply={'有' if plan['reply_text'] else '無'}"
          f"（{plan.get('reasoning','')}）")
    _execute_action_plan(case, state, plan)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def _run_review_case(case: dict) -> None:
    """跑一個 review case 的完整內外圈(local / 直接審查 fast path)。"""
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
        elif ctype == "case-activity":
            _handle_case_activity(case)
        else:
            # digest / reminder / patrol:排程任務,走同一條 dispatch(無 model,外圈做)。
            from . import scheduled_tasks
            handler = scheduled_tasks.HANDLERS.get(ctype)
            if handler is None:
                print(f"[worker] 未知 case type={ctype},略過。")
            else:
                result = handler(case)
                _report_scheduled(case, result)
        queue.mark_done(case)
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
