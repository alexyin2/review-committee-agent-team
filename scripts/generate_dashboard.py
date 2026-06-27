#!/usr/bin/env python3
"""產生 L1 私有 dashboard(DASHBOARD.md),寫回 repo。

設計(design §8):GitHub Action 是代管 compute,不是要維護的 server。
dashboard = 「把現況算出來、寫回 repo」。本檔只讀**已 commit 的狀態**——

  - 已裁決(decided):reviews/<case>/ 已 merge 進 main(人簽過)。
  - 待人簽(awaiting-signoff):review/<case> 分支已 commit,但尚未 merge(= 待裁決)。
  - rubric 變更:git log on rubrics/。
  - 各 lens 健康度:findings.json 是否存在且可解析。

★ 看不到 .runtime/queue(只在桌機本機)——所以 dashboard 反映的是「已落 git 的審查狀態」,
  不是即時佇列深度。這是刻意的(Action 沒有桌機的 runtime 視角)。

敏感性(design §8):L1 DASHBOARD.md 完全私有(commit 回 private repo)。
不要把它推上 GitHub Pages(Pages 即使 repo private 也公開)。

跑法:
    python scripts/generate_dashboard.py            # 寫 DASHBOARD.md
    python scripts/generate_dashboard.py --print     # 只印到 stdout,不寫檔
純標準庫;不呼叫 model(鐵律:Actions 只做不需 model 的事)。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEVERITY_ORDER = ["blocker", "high", "medium", "low", "info"]


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True
    ).stdout


def _review_branches() -> list[str]:
    """待人簽:review/<case> 分支清單。"""
    out = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads/review/"])
    return [b.strip() for b in out.splitlines() if b.strip()]


def _decided_cases() -> list[str]:
    """已裁決:main 工作樹上的 reviews/<case>/(排除 _template)。"""
    reviews = REPO_ROOT / "reviews"
    if not reviews.is_dir():
        return []
    return sorted(
        p.name for p in reviews.iterdir()
        if p.is_dir() and p.name != "_template" and (p / "verdict").is_dir()
    )


def _read_findings_from_branch(branch: str, case_id: str, lens: str) -> dict | None:
    out = subprocess.run(
        ["git", "show", f"{branch}:reviews/{case_id}/findings/{lens}.json"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return None


def _read_findings_from_disk(case_id: str, lens: str) -> dict | None:
    fpath = REPO_ROOT / "reviews" / case_id / "findings" / f"{lens}.json"
    if not fpath.exists():
        return None
    try:
        return json.loads(fpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _verdict_recommendation(text: str) -> str:
    """從 verdict markdown 粗略抓推薦(no-go / go / 帶條件)。"""
    low = text.lower()
    if "no-go" in low or "no go" in low:
        return "no-go"
    if "帶條件" in text or "conditional" in low:
        return "帶條件 go"
    if "go" in low:
        return "go"
    return "?"


def _read_verdict_from_branch(branch: str, case_id: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{branch}:reviews/{case_id}/verdict/recommendation.md"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    return _verdict_recommendation(out.stdout) if out.returncode == 0 else "?"


def _read_verdict_from_disk(case_id: str) -> str:
    vpath = REPO_ROOT / "reviews" / case_id / "verdict" / "recommendation.md"
    return _verdict_recommendation(vpath.read_text(encoding="utf-8")) if vpath.exists() else "?"


def _severity_tally(findings_doc: dict | None) -> dict[str, int]:
    tally = {s: 0 for s in SEVERITY_ORDER}
    if findings_doc:
        for f in findings_doc.get("findings", []):
            sev = f.get("severity", "info")
            tally[sev] = tally.get(sev, 0) + 1
    return tally


def collect_state(lenses: list[str]) -> dict:
    """彙整 dashboard 需要的數字。回傳 dict(也給 digest 任務重用)。"""
    cases = []

    # 待人簽:review/<case> 分支
    for branch in _review_branches():
        case_id = branch[len("review/"):]
        sev = {s: 0 for s in SEVERITY_ORDER}
        lens_present = {}
        for lens in lenses:
            doc = _read_findings_from_branch(branch, case_id, lens)
            lens_present[lens] = doc is not None
            for k, v in _severity_tally(doc).items():
                sev[k] += v
        cases.append({
            "case_id": case_id,
            "status": "awaiting-signoff",
            "verdict": _read_verdict_from_branch(branch, case_id),
            "severity": sev,
            "lens_present": lens_present,
        })

    # 已裁決:main 工作樹
    for case_id in _decided_cases():
        sev = {s: 0 for s in SEVERITY_ORDER}
        lens_present = {}
        for lens in lenses:
            doc = _read_findings_from_disk(case_id, lens)
            lens_present[lens] = doc is not None
            for k, v in _severity_tally(doc).items():
                sev[k] += v
        cases.append({
            "case_id": case_id,
            "status": "decided",
            "verdict": _read_verdict_from_disk(case_id),
            "severity": sev,
            "lens_present": lens_present,
        })

    # rubric 變更(近 30 天)
    rubric_log = _git(["log", "--since=30.days", "--oneline", "--", "rubrics/"])
    rubric_changes = [l for l in rubric_log.splitlines() if l.strip()]

    # 各 lens 健康度:在所有 case 裡，該 lens 有產出的比例
    lens_health = {}
    for lens in lenses:
        produced = sum(1 for c in cases if c["lens_present"].get(lens))
        lens_health[lens] = {"produced": produced, "total": len(cases)}

    awaiting = [c for c in cases if c["status"] == "awaiting-signoff"]
    decided = [c for c in cases if c["status"] == "decided"]
    return {
        "cases": cases,
        "awaiting": awaiting,
        "decided": decided,
        "rubric_changes": rubric_changes,
        "lens_health": lens_health,
        "lenses": lenses,
    }


def _health_glyph(produced: int, total: int) -> str:
    if total == 0:
        return "—"
    if produced == total:
        return "✅"
    if produced == 0:
        return "❌"
    return "⚠️"


def render_markdown(state: dict, *, generated_at: str) -> str:
    lenses = state["lenses"]
    awaiting = state["awaiting"]
    decided = state["decided"]

    health_cells = " ".join(
        f"{lens}:{_health_glyph(state['lens_health'][lens]['produced'], state['lens_health'][lens]['total'])}"
        for lens in lenses
    ) or "—"

    lines = [
        "# Review Committee — Dashboard",
        "",
        f"> 自動產生於 {generated_at}（L1 私有；勿推上 Pages）。"
        "反映**已落 git 的審查狀態**,不含桌機本機佇列深度。",
        "",
        "## 概況",
        "",
        "| 指標 | 值 |",
        "|---|---|",
        f"| 待人簽裁決（awaiting-signoff） | {len(awaiting)} |",
        f"| 已裁決（decided） | {len(decided)} |",
        f"| rubric 變更（近 30 天） | {len(state['rubric_changes'])} |",
        f"| 各 lens 健康度 | {health_cells} |",
        "",
    ]

    lines += ["## 待人簽裁決（需委員 merge PR 才生效）", ""]
    if awaiting:
        lines += ["| case | 推薦 | blocker | high | medium | low | info |",
                  "|---|---|---|---|---|---|---|"]
        for c in awaiting:
            s = c["severity"]
            lines.append(
                f"| `{c['case_id']}` | **{c['verdict']}** | "
                f"{s['blocker']} | {s['high']} | {s['medium']} | {s['low']} | {s['info']} |"
            )
    else:
        lines.append("_（無）_")
    lines.append("")

    lines += ["## 已裁決", ""]
    if decided:
        lines += ["| case | 推薦 |", "|---|---|"]
        for c in decided:
            lines.append(f"| `{c['case_id']}` | {c['verdict']} |")
    else:
        lines.append("_（無）_")
    lines.append("")

    lines += ["## 近期 rubric 變更（近 30 天）", ""]
    if state["rubric_changes"]:
        lines += [f"- `{l}`" for l in state["rubric_changes"]]
    else:
        lines.append("_（無）_")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="產生 L1 DASHBOARD.md")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="只印到 stdout,不寫檔")
    parser.add_argument("--generated-at", default="(local run)",
                        help="時間戳(Action 會傳;本機跑可不填)")
    args = parser.parse_args()

    # lenses 從 config 拿;避免硬編
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from orchestrator.config import config
        lenses = getattr(config, "review_lenses", None) or ["security"]
    except Exception:
        lenses = ["security"]

    state = collect_state(lenses)
    md = render_markdown(state, generated_at=args.generated_at)

    if args.to_stdout:
        print(md)
    else:
        out = REPO_ROOT / "DASHBOARD.md"
        out.write_text(md, encoding="utf-8")
        print(f"[dashboard] 已寫出 {out}（{len(state['awaiting'])} 待簽 / "
              f"{len(state['decided'])} 已裁決）")


if __name__ == "__main__":
    main()
