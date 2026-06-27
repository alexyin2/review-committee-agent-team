#!/usr/bin/env python3
"""把審查狀態烤成 site/data.js,供靜態站(site/index.html)讀取。

設計(design §8 L2 的進化版):GitHub Action 預烤資料 → 靜態頁在 browser 讀 →
無 server、無 token、不打 API。本檔產出的是「消毒過、可呈現」的結構化資料。

資料來源(只讀已落 git 的狀態,與 generate_dashboard.py 同源):
  - review/<case> 分支       → 待人簽(awaiting-signoff)
  - reviews/<case>/(main)    → 已裁決(decided)
  - 每個 case 的 findings/*.json + verdict/recommendation.md + README.md

★ 隱私:Pages 站台公開(即使 repo private)。預設輸出到 site/ 供本機/私有檢視;
  若要推 Pages,務必確認 data.js 內容可公開,或只放消毒過的彙總。
  本檔目前輸出完整 findings(含 evidence)——適合本機/private 檢視,推 Pages 前要再篩。

輸出:site/data.js(內含 `window.REVIEW_DATA = {...}`,讓 index.html 直接讀,免 fetch)。

跑法:
    python scripts/build_site.py                    # 寫 site/data.js
    python scripts/build_site.py --print            # 印 JSON 到 stdout
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEVERITY_ORDER = ["blocker", "high", "medium", "low", "info"]

# CAB 兩道關卡(對應公司實際流程:CAB1→UT、CAB2→PROD)
CAB_GATES = [
    {"id": "CAB1", "name": "CAB1", "env": "UT", "desc": "部署到 UT(測試)環境前的審查關卡"},
    {"id": "CAB2", "name": "CAB2", "env": "PROD", "desc": "部署到 PROD(正式)環境前的審查關卡"},
]
# 每道 CAB 的四步流程
CAB_WORKFLOW = ["提案", "文件 Review", "審核會議", "會議記錄"]

# 審核部門 = lens。lens 內部代碼 → 部門中文名。
DEPARTMENTS = [
    {"lens": "security", "name": "資安", "full": "資訊安全", "has_rubric": True},
    {"lens": "risk", "name": "風管", "full": "風險管理", "has_rubric": False},
    {"lens": "legal", "name": "法遵", "full": "法令遵循", "has_rubric": False},
]
DEPT_BY_LENS = {d["lens"]: d for d in DEPARTMENTS}


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)


def _review_branches() -> list[dict]:
    """待人簽的 review 分支。回傳 [{ref, case_id}]。

    同時掃本地 head 與遠端 tracking ref——CI / fresh clone 裡 review/* 是
    refs/remotes/origin/review/*(非本地 head),只掃 refs/heads 會漏掉。
    以 case_id 去重(本地與遠端同名只算一次,優先本地 ref)。
    """
    seen: dict[str, str] = {}  # case_id -> ref(供 git show)
    # 本地 heads 優先
    local = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads/review/"]).stdout
    for b in (l.strip() for l in local.splitlines()):
        if b:
            seen.setdefault(b[len("review/"):], b)
    # 再補遠端 tracking refs。注意:for-each-ref 的 pattern 不支援中間的 '*' 萬用字元
    # (refs/remotes/*/review/ 會匹配到空),要用前綴 refs/remotes/ 再自行過濾。
    remote = _git(["for-each-ref", "--format=%(refname:short)", "refs/remotes/"]).stdout
    for b in (l.strip() for l in remote.splitlines()):
        if not b or "/review/" not in b:
            continue
        case_id = b.split("/review/", 1)[1]
        seen.setdefault(case_id, b)  # 用完整 ref(如 origin/review/xxx)供 git show
    return [{"ref": ref, "case_id": cid} for cid, ref in seen.items()]


def _decided_cases() -> list[str]:
    reviews = REPO_ROOT / "reviews"
    if not reviews.is_dir():
        return []
    return sorted(p.name for p in reviews.iterdir()
                  if p.is_dir() and p.name != "_template" and (p / "verdict").is_dir())


def _read(branch: str | None, relpath: str) -> str | None:
    """branch=None → 讀工作樹(decided);否則讀分支(awaiting)。"""
    if branch is None:
        p = REPO_ROOT / relpath
        return p.read_text(encoding="utf-8") if p.exists() else None
    out = _git(["show", f"{branch}:{relpath}"])
    return out.stdout if out.returncode == 0 else None


def _verdict_recommendation(text: str | None) -> str:
    if not text:
        return "unknown"
    low = text.lower()
    if "no-go" in low or "no go" in low:
        return "no-go"
    if "帶條件" in text or "conditional" in low:
        return "conditional-go"
    if "go" in low:
        return "go"
    return "unknown"


def _lenses() -> list[str]:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from orchestrator.config import config
        return getattr(config, "review_lenses", None) or ["security"]
    except Exception:
        return ["security"]


def _project_of(case_id: str, readme_md: str | None) -> tuple[str, str]:
    """推斷 case 屬於哪個專案(產品/系統)。回傳 (project_id, project_name)。

    優先序:
      1. README 內若有 `專案:<名稱>` / `Project: <name>` 行 → 用它。
      2. 否則用 case_id 尾段的 Slack channel / LOCAL / SCHED 當分組鍵(demo 後援)。
    真實上線時應由提交 payload 帶明確 project 欄位;這裡保持可推斷、可覆寫。
    """
    if readme_md:
        for line in readme_md.splitlines():
            for key in ("專案:", "專案：", "Project:", "project:"):
                if key in line:
                    name = line.split(key, 1)[1].strip().strip("`*")
                    if name:
                        return (name, name)
    # 後援:case_id 形如 2026-0627-062747-C0DEMO123 → 取尾段
    tail = case_id.rsplit("-", 1)[-1] if "-" in case_id else case_id
    return (tail, tail)


def _skills_inventory() -> dict:
    """Skills 區的「腦」:rubrics / skills / agents 清單 + 最近 git 變更。"""
    def _entries(subdir: str, pattern: str) -> list[dict]:
        base = REPO_ROOT / subdir
        if not base.is_dir():
            return []
        out = []
        for p in sorted(base.rglob(pattern)):
            rel = p.relative_to(REPO_ROOT).as_posix()
            log = _git(["log", "-1", "--format=%h|%cs|%s", "--", rel]).stdout.strip()
            sha, date, subject = (log.split("|", 2) + ["", "", ""])[:3] if log else ("", "", "")
            out.append({
                "name": p.stem if pattern.endswith(".md") and p.name != "SKILL.md"
                        else (p.parent.name if p.name == "SKILL.md" else p.stem),
                "path": rel,
                "last_sha": sha,
                "last_date": date,
                "last_subject": subject,
            })
        return out

    return {
        "rubrics": _entries("rubrics", "*.md"),
        "skills": _entries("skills", "SKILL.md"),
        "agents": _entries("agents", "*.md"),
    }


def _feedback_proposals() -> list[dict]:
    """待人覆核的 skill 修改提案(feedback-synthesis 產出)。讀 .runtime,屬內部資料。"""
    pdir = REPO_ROOT / ".runtime" / "feedback" / "proposals"
    if not pdir.is_dir():
        return []
    out = []
    for p in sorted(pdir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        # 抓「來源:N 條」當數量
        count = 0
        for line in text.splitlines():
            if "來源:" in line and "條" in line:
                import re as _re
                m = _re.search(r"來源:(\d+)", line)
                if m:
                    count = int(m.group(1))
                break
        out.append({"target": p.stem, "feedback_count": count, "body": text})
    return out


def _feedback_summary() -> dict:
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from orchestrator import feedback_store
        return feedback_store.summary()
    except Exception:
        return {"total": 0, "by_target": {}}


def _schedule_info() -> list[dict]:
    """排程區:任務清單 + 說明 + 狀態。"""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from orchestrator import scheduler, scheduled_tasks
    except Exception:
        return []
    out = []
    for name, jtype in scheduler.JOBS.items():
        handler = scheduled_tasks.HANDLERS.get(jtype)
        doc = ((handler.__doc__ or "").strip().split("\n")[0]) if handler else ""
        implemented = jtype in ("digest", "feedback-synthesis")
        out.append({
            "name": name,
            "type": jtype,
            "desc": doc,
            "status": "implemented" if implemented else "skeleton",
        })
    return out


def _collect_case(case_id: str, branch: str | None, status: str, lenses: list[str]) -> dict:
    base = f"reviews/{case_id}"
    findings = []
    lens_present = {}
    for lens in lenses:
        raw = _read(branch, f"{base}/findings/{lens}.json")
        if raw is None:
            lens_present[lens] = False
            continue
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            lens_present[lens] = False
            continue
        lens_present[lens] = True
        for f in doc.get("findings", []):
            # source_doc:優先用 finding 自帶,否則從 evidence 推(取「檔名.ext」),再否則用第一份提交檔
            src_doc = f.get("source_doc", "")
            if not src_doc:
                m = re.search(r"([\w\-]+\.(?:pdf|md|docx?|xlsx?|txt))", f.get("evidence", ""))
                src_doc = m.group(1) if m else ""
            findings.append({
                "lens": doc.get("lens", lens),
                "cab": f.get("cab", "CAB1"),      # 真實 pipeline 目前產 CAB1(UT)階段
                "source_doc": src_doc,
                "id": f.get("id", ""),
                "severity": f.get("severity", "info"),
                "title": f.get("title", ""),
                "rationale": f.get("rationale", ""),
                "recommendation": f.get("recommendation", ""),
                "evidence": f.get("evidence", ""),
                "rubric_ref": f.get("rubric_ref", ""),
            })

    findings.sort(key=lambda f: SEVERITY_ORDER.index(f["severity"])
                  if f["severity"] in SEVERITY_ORDER else 99)
    tally = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER}

    verdict_md = _read(branch, f"{base}/verdict/recommendation.md")
    readme_md = _read(branch, f"{base}/README.md")
    project_id, project_name = _project_of(case_id, readme_md)

    # 底稿(專案團隊提交的文件)— 指標來自 README;實體在 .runtime(不進 git)
    submission = []
    ws_files = REPO_ROOT / ".runtime" / "workspace" / case_id / "files"
    if ws_files.is_dir():
        submission = [{"name": f.name, "bytes": f.stat().st_size}
                      for f in sorted(ws_files.iterdir()) if f.is_file()]

    case = {
        "case_id": case_id,
        "project_id": project_id,
        "project_name": project_name,
        "status": status,                       # awaiting-signoff | decided
        "branch": branch or "main",
        "verdict": _verdict_recommendation(verdict_md),
        "verdict_md": verdict_md or "",
        "readme_md": readme_md or "",
        "findings": findings,
        "severity": tally,
        "lens_present": lens_present,
        "blockers": tally["blocker"],
        "submission": submission,
    }
    case["cabs"] = _build_cabs(case)
    return case


def _dept_verdict(findings: list[dict]) -> str:
    """單一部門依其 findings 推一個建議(部門在審核會議上給的意見)。"""
    sev = {f["severity"] for f in findings}
    if "blocker" in sev:
        return "no-go"
    if "high" in sev:
        return "conditional-go"
    return "go"


def _build_cabs(case: dict) -> list[dict]:
    """把一個 case 的扁平 findings 組成 CAB1/CAB2 兩道關卡的結構。

    每道關卡 = 4 步 workflow + 兩種切法:
      - 文件 Review(by 文件):該 CAB 下每份文件 + 指向它的 findings
      - 審核會議(by 部門):三個部門(風管/資安/法遵)各自的 Agent 模擬建議
    """
    cabs = []
    for gate in CAB_GATES:
        gf = [f for f in case["findings"] if f.get("cab", "CAB1") == gate["id"]]
        # 文件視角
        docs = {}
        for f in gf:
            d = f.get("source_doc") or "(未標來源)"
            docs.setdefault(d, []).append(f)
        doc_view = [{"doc": d, "findings": fs,
                     "blockers": sum(1 for x in fs if x["severity"] == "blocker")}
                    for d, fs in sorted(docs.items())]
        # 部門視角(審核會議:Agent 模擬各部門意見)
        dept_view = []
        for dept in DEPARTMENTS:
            df = [f for f in gf if f["lens"] == dept["lens"]]
            dept_view.append({
                "lens": dept["lens"], "name": dept["name"], "full": dept["full"],
                "has_rubric": dept["has_rubric"],
                "findings": df,
                "advice": _dept_verdict(df) if df else ("go" if dept["has_rubric"] else "pending"),
                "covered": bool(df) or dept["has_rubric"],
            })
        # 該 CAB 的狀態:有任何 finding 即視為已審;有 blocker → 卡關
        has_findings = bool(gf)
        blockers = sum(1 for f in gf if f["severity"] == "blocker")
        cabs.append({
            "id": gate["id"], "name": gate["name"], "env": gate["env"], "desc": gate["desc"],
            "workflow": CAB_WORKFLOW,
            "reviewed": has_findings,
            "blockers": blockers,
            "verdict": "no-go" if blockers else ("conditional-go"
                       if any(f["severity"] == "high" for f in gf) else
                       ("go" if has_findings else "pending")),
            "doc_view": doc_view,
            "dept_view": dept_view,
            "finding_count": len(gf),
        })
    return cabs


def collect() -> dict:
    lenses = _lenses()
    cases = []
    for rb in _review_branches():
        cases.append(_collect_case(rb["case_id"], rb["ref"], "awaiting-signoff", lenses))
    for case_id in _decided_cases():
        cases.append(_collect_case(case_id, None, "decided", lenses))

    # 排序:待人簽優先,blocker 多者優先
    cases.sort(key=lambda c: (c["status"] != "awaiting-signoff", -c["blockers"], c["case_id"]))

    rubric_log = _git(["log", "--since=30.days", "--oneline", "--", "rubrics/"]).stdout
    rubric_changes = [l for l in rubric_log.splitlines() if l.strip()]

    awaiting = [c for c in cases if c["status"] == "awaiting-signoff"]
    decided = [c for c in cases if c["status"] == "decided"]
    # lens 健康度按「部門」算:該部門有產出 findings 的 case 數
    lens_health = {
        d["name"]: {"produced": sum(1 for c in cases
                                    if any(f["lens"] == d["lens"] for f in c.get("findings", []))),
                    "total": len(cases), "has_rubric": d["has_rubric"]}
        for d in DEPARTMENTS
    }

    # 專案分組:一個專案(產品/系統)→ 其歷次審查(reviews)
    projects = {}
    for c in cases:
        pid = c["project_id"]
        if pid not in projects:
            projects[pid] = {
                "project_id": pid,
                "project_name": c["project_name"],
                "reviews": [],
            }
        projects[pid]["reviews"].append(c["case_id"])
    project_list = []
    for p in projects.values():
        revs = [c for c in cases if c["project_id"] == p["project_id"]]
        p["review_count"] = len(revs)
        p["open_count"] = sum(1 for c in revs if c["status"] == "awaiting-signoff")
        p["latest_verdict"] = revs[0]["verdict"] if revs else "unknown"
        p["total_blockers"] = sum(c["blockers"] for c in revs)
        project_list.append(p)
    project_list.sort(key=lambda p: (-p["open_count"], p["project_name"]))

    return {
        "lenses": lenses,
        "departments": DEPARTMENTS,
        "cab_gates": CAB_GATES,
        "cab_workflow": CAB_WORKFLOW,
        "cases": cases,
        "projects": project_list,
        "skills": _skills_inventory(),
        "schedule": _schedule_info(),
        "proposals": _feedback_proposals(),
        "feedback_summary": _feedback_summary(),
        "summary": {
            "awaiting": len(awaiting),
            "decided": len(decided),
            "rubric_changes_30d": len(rubric_changes),
            "total_cases": len(cases),
            "total_projects": len(project_list),
        },
        "rubric_changes": rubric_changes,
        "lens_health": lens_health,
    }


def _apply_demo_seed(data: dict) -> dict:
    """原型用:把真實 case 歸到一個有意義的專案,並掺入清楚標示為示意的專案/審查,
    讓「專案 → 歷次審查」「排程」「skills」整個 IA 都看得到。
    僅在 --demo 時呼叫;正式產線(無旗標)只吐真實資料。
    """
    def mk(lens, fid, sev, title, rec, doc, cab, ref, demo=True):
        return {"lens": lens, "cab": cab, "source_doc": doc, "id": fid, "severity": sev,
                "title": title, "rationale": f"(示意)對應 {lens} 部門 rubric {ref}。",
                "recommendation": rec, "evidence": f"{doc}(示意)", "rubric_ref": ref, "demo": demo}

    # 真實 case → 歸到「Payments Service」;其真實 findings 全屬 CAB1/資安。
    # 再掺示意的風管/法遵(CAB1)與 CAB2 全套,讓 CAB×部門×文件 結構完整可見。
    for c in data["cases"]:
        c["project_id"] = "payments-service"
        c["project_name"] = "Payments Service"
        c["demo"] = False
        for f in c["findings"]:           # 真實 findings 補欄位
            f.setdefault("cab", "CAB1")
            f.setdefault("source_doc", "launch-doc.md")
            f["demo"] = False
        # CAB1 補風管/法遵(示意)
        c["findings"] += [
            mk("risk", "risk-001", "high", "缺營運中斷影響評估(BIA)", "補 BIA 與回復時間目標 RTO。", "launch-doc.md", "CAB1", "risk-bia"),
            mk("legal", "legal-001", "medium", "個資蒐集告知不足", "補個資告知與同意機制說明。", "launch-doc.md", "CAB1", "legal-pdpa"),
        ]
        # CAB2(PROD)整套示意 — 大多已收斂,僅少量 high/medium
        c["findings"] += [
            mk("security", "sec-c2-001", "high", "PROD 金鑰輪換週期未定義", "訂定金鑰輪換政策。", "prod-runbook.pdf", "CAB2", "sec-secret"),
            mk("risk", "risk-c2-001", "medium", "上線回退(rollback)演練未紀錄", "補回退演練紀錄。", "prod-runbook.pdf", "CAB2", "risk-rollback"),
            mk("legal", "legal-c2-001", "low", "資料保存期限文件待補", "補保存期限政策。", "prod-dpa.pdf", "CAB2", "legal-retention"),
        ]
        c["submission"] = (c.get("submission") or []) + [
            {"name": "prod-runbook.pdf", "bytes": 51200, "demo": True},
            {"name": "prod-dpa.pdf", "bytes": 20480, "demo": True},
        ]
        c["cabs"] = _build_cabs(c)         # findings 變了,重建 CAB 結構

    # 第二個完全示意專案,展示多專案牌牆
    notify = {
        "case_id": "2026-0620-090000-NOTIFY", "project_id": "notification-hub",
        "project_name": "Notification Hub", "status": "decided", "branch": "main",
        "verdict": "go", "verdict_md": "", "readme_md": "", "demo": True,
        "findings": [
            mk("security", "sec-n1", "low", "建議補 rate limiting 文件", "補文件。", "notify-design.pdf", "CAB1", "sec-authz"),
            mk("risk", "risk-n1", "low", "監控告警門檻待確認", "確認門檻。", "notify-ops.md", "CAB1", "risk-monitoring"),
            mk("security", "sec-n2", "medium", "PROD CORS 設定過寬", "收斂允許來源。", "notify-prod.pdf", "CAB2", "sec-data"),
        ],
        "severity": {}, "lens_present": {}, "blockers": 0,
        "submission": [{"name":"notify-design.pdf","bytes":40960,"demo":True},
                       {"name":"notify-ops.md","bytes":3072,"demo":True},
                       {"name":"notify-prod.pdf","bytes":15360,"demo":True}],
    }
    notify["severity"] = {s: sum(1 for f in notify["findings"] if f["severity"] == s) for s in SEVERITY_ORDER}
    notify["blockers"] = notify["severity"]["blocker"]
    notify["cabs"] = _build_cabs(notify)
    data["cases"].append(notify)

    # 真實 case 的 severity/blockers 也要把示意 findings 算進去(供牌牆顯示)
    for c in data["cases"]:
        c["severity"] = {s: sum(1 for f in c["findings"] if f["severity"] == s) for s in SEVERITY_ORDER}
        c["blockers"] = c["severity"]["blocker"]

    return _regroup(data)


def _regroup(data: dict) -> dict:
    cases = data["cases"]
    projects = {}
    for c in cases:
        pid = c["project_id"]
        projects.setdefault(pid, {"project_id": pid, "project_name": c["project_name"], "reviews": []})
        projects[pid]["reviews"].append(c["case_id"])
    project_list = []
    for p in projects.values():
        revs = [c for c in cases if c["project_id"] == p["project_id"]]
        revs.sort(key=lambda c: (c["status"] != "awaiting-signoff", c["case_id"]), reverse=False)
        p["review_count"] = len(revs)
        p["open_count"] = sum(1 for c in revs if c["status"] == "awaiting-signoff")
        p["latest_verdict"] = revs[0]["verdict"] if revs else "unknown"
        p["total_blockers"] = sum(c["blockers"] for c in revs)
        project_list.append(p)
    project_list.sort(key=lambda p: (-p["open_count"], -p["total_blockers"], p["project_name"]))
    data["projects"] = project_list
    data["summary"]["total_projects"] = len(project_list)
    data["summary"]["decided"] = sum(1 for c in cases if c["status"] == "decided")
    data["summary"]["total_cases"] = len(cases)
    return data


def sanitize_public(data: dict) -> dict:
    """消毒成可公開(GitHub Pages 公開上網,個人帳號無法設私有)。

    只保留**彙總數字 + 結構名稱**;移除任何可能機敏的內文:
      - findings 內文(title/rationale/recommendation/evidence)、verdict_md、readme_md
      - 底稿檔名(submission)、case_id 細節保留(僅時間戳,不含 Slack channel 內容)
      - 提案 body(只留 target + 數量)、回饋逐條內容
    保留:各狀態計數、各 lens 健康度、severity 分布、專案名與審查數、skill/rubric **名稱與路徑**。
    """
    pub = {
        "public_mode": True,
        "generated_at": data.get("generated_at", ""),
        "lenses": data["lenses"],
        "summary": data["summary"],
        "lens_health": data["lens_health"],
        "schedule": [{"name": s["name"], "type": s["type"], "status": s["status"]}
                     for s in data.get("schedule", [])],
        # 專案:只留名稱與彙總,不留 case 內文
        "projects": [{
            "project_id": p["project_id"], "project_name": p["project_name"],
            "review_count": p["review_count"], "open_count": p["open_count"],
            "latest_verdict": p["latest_verdict"], "total_blockers": p["total_blockers"],
        } for p in data.get("projects", [])],
        "departments": data.get("departments", []),
        "cab_gates": data.get("cab_gates", []),
        "cab_workflow": data.get("cab_workflow", []),
        # 審查:只留狀態 + severity 分布 + CAB 結構彙總(數字),不留 findings 內文/verdict/底稿
        "cases": [{
            "case_id": c["case_id"], "project_id": c["project_id"], "project_name": c["project_name"],
            "status": c["status"], "verdict": c["verdict"], "severity": c["severity"],
            "blockers": c["blockers"], "finding_count": len(c["findings"]), "demo": c.get("demo", False),
            "cabs": [_sanitize_cab(cab) for cab in c.get("cabs", [])],
        } for c in data.get("cases", [])],
        # skills:只留名稱/路徑/最近變更(本來就是 git 公開資訊),不含 rubric 內文
        "skills": data.get("skills", {}),
        # 提案:只留 target + 數量,不留 body(可能含回饋原文)
        "proposals": [{"target": p["target"], "feedback_count": p["feedback_count"]}
                      for p in data.get("proposals", [])],
        "feedback_summary": {"total": data.get("feedback_summary", {}).get("total", 0)},
        "rubric_changes_30d": data["summary"].get("rubric_changes_30d", 0),
    }
    return pub


def _sanitize_cab(cab: dict) -> dict:
    """消毒 CAB 結構:保留關卡/部門/文件的**結構與數字**,移除 findings 內文。"""
    return {
        "id": cab["id"], "name": cab["name"], "env": cab["env"], "desc": cab["desc"],
        "workflow": cab["workflow"], "reviewed": cab["reviewed"],
        "blockers": cab["blockers"], "verdict": cab["verdict"], "finding_count": cab["finding_count"],
        # 文件視角:檔名可能本身洩漏資訊 → 遮成代號(文件 1/2…),只留結構與數字
        "doc_view": [{"doc": f"文件 {i+1}", "finding_count": len(d["findings"]), "blockers": d["blockers"]}
                     for i, d in enumerate(cab.get("doc_view", []))],
        # 部門視角:只留部門名 + 建議 + finding 數(不留 findings 內文)
        "dept_view": [{"lens": dv["lens"], "name": dv["name"], "full": dv["full"],
                       "has_rubric": dv["has_rubric"], "advice": dv["advice"],
                       "covered": dv["covered"], "finding_count": len(dv["findings"])}
                      for dv in cab.get("dept_view", [])],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="烤審查狀態成 site/data.js")
    parser.add_argument("--print", action="store_true", dest="to_stdout")
    parser.add_argument("--demo", action="store_true", help="掺入示意專案/審查,展示完整 IA(原型用)")
    parser.add_argument("--public", action="store_true",
                        help="消毒成可公開版(供 GitHub Pages;只留彙總數字,不含機敏內文)")
    parser.add_argument("--generated-at", default="(local build)")
    args = parser.parse_args()

    data = collect()
    if args.demo:
        data = _apply_demo_seed(data)
        data["demo_mode"] = True
    data["generated_at"] = args.generated_at
    if args.public:
        data = sanitize_public(data)
        data["generated_at"] = args.generated_at
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    if args.to_stdout:
        print(payload)
        return

    site = REPO_ROOT / "site"
    site.mkdir(exist_ok=True)
    (site / "data.js").write_text(
        f"window.REVIEW_DATA = {payload};\n", encoding="utf-8"
    )
    print(f"[build_site] 已寫出 site/data.js"
          f"（{data['summary']['awaiting']} 待簽 / {data['summary']['decided']} 已裁決）")


if __name__ == "__main__":
    main()
