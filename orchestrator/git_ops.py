"""git / gh 包裝。審查紀錄進 git、go/no-go 走 PR(CODEOWNERS 強制人 merge)。

只放會受益於版本控制的東西:findings、verdict、case README。
原始提交 bytes 在 .runtime/,永不進 git(CLAUDE.md 鐵律 #3)。

關鍵橋接:內圈把 findings/verdict 寫在 .runtime/workspace/<case>/(gitignored),
這裡確定性地**複製**進 reviews/<case>/(tracked)再 commit。

dry-run:尚無遠端 / 指定 dry-run 時,只在本機開分支 + commit(可 git show 檢視),
跳過 push 與 gh pr create。今天沒設遠端,實際就是走這條。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import REPO_ROOT, config


def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


def _has_remote() -> bool:
    return bool(_git(["remote"], check=False).stdout.strip())


def _current_branch() -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def _staged_outside(rel_prefix: str) -> list[str]:
    """列出 rel_prefix 之外、已 staged(進 index)的路徑。

    我們用顯式 `git add <rel_prefix>` + `git commit`(不帶 -a),所以只有**已 staged**的
    其他改動才可能被掃進審查 commit;modified-unstaged 與 untracked 都安全。
    porcelain v1 第 0 欄 = index 狀態;非空白且非 '?' 即代表已 staged。
    """
    out = _git(["status", "--porcelain"], check=False).stdout
    staged = []
    for line in out.splitlines():
        if not line:
            continue
        index_status = line[0]
        if index_status in (" ", "?"):
            continue  # 未 staged / 未追蹤 → 不會被本案 commit 掃到
        path = line[3:].strip()
        if " -> " in path:  # rename:取新路徑
            path = path.split(" -> ", 1)[1]
        if path and not path.startswith(rel_prefix):
            staged.append(path)
    return staged


def _assert_no_unrelated_staged(rel_prefix: str) -> None:
    """拒絕在「有與本案無關的已 staged 變更」時開審查 commit(會被掃進去)。"""
    dirty = _staged_outside(rel_prefix)
    if dirty:
        raise RuntimeError(
            "index 有與本案無關的已 staged 變更,拒絕開審查 commit(會被掃進去):\n  "
            + "\n  ".join(dirty)
            + "\n請先 git restore --staged 那些檔,或在乾淨的 worktree 跑 worker。"
        )


def stage_review_outputs(case: dict, workspace: Path) -> Path:
    """把內圈產物從 runtime 工作區複製進 tracked 的 reviews/<case>/。回傳該目錄。

    只搬 findings / verdict / README——指標與紀錄,不搬實體 bytes(鐵律 #3)。
    """
    case_id = case["case_id"]
    review_dir = REPO_ROOT / "reviews" / case_id
    (review_dir / "findings").mkdir(parents=True, exist_ok=True)
    (review_dir / "verdict").mkdir(parents=True, exist_ok=True)

    copied = []
    for lens_file in sorted((workspace / "findings").glob("*.json")):
        shutil.copy2(lens_file, review_dir / "findings" / lens_file.name)
        copied.append(f"findings/{lens_file.name}")
    verdict_src = workspace / "verdict" / "recommendation.md"
    if verdict_src.exists():
        shutil.copy2(verdict_src, review_dir / "verdict" / "recommendation.md")
        copied.append("verdict/recommendation.md")

    (review_dir / "README.md").write_text(_render_readme(case, copied), encoding="utf-8")
    return review_dir


def _render_readme(case: dict, copied: list[str]) -> str:
    """產 case 狀態板 README(人看的入口)。"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    files = "、".join(f.get("name", "?") for f in case.get("files", [])) or "(無)"
    src = case.get("source")
    if isinstance(src, dict):
        source_str = src.get("slack_permalink") or src.get("dir") or src.get("type", "?")
    else:
        source_str = str(src)
    return f"""# Case {case['case_id']}

> 本案狀態板。findings/verdict 為 agent 推薦;**真正裁決 = 人 merge 此 PR**(CODEOWNERS)。

- **狀態**:verdict-draft(待人簽)
- **來源**:{source_str}
- **提交者**:{case.get('submitter', '?')}
- **建立時間**:{ts}
- **提交檔**:{files}

## 產出
{chr(10).join(f'- `{c}`' for c in copied) or '- (無)'}

## 結構
- `findings/` — 各 lens 結構化 findings(agent 自動產)
- `verdict/recommendation.md` — 合成推薦(此層變更觸發 go/no-go,CODEOWNERS 強制人 merge)
"""


def _verdict_summary(case: dict) -> str:
    """取 verdict 內容當 PR body(讀 reviews/<case>/verdict)。"""
    vpath = REPO_ROOT / "reviews" / case["case_id"] / "verdict" / "recommendation.md"
    if vpath.exists():
        return vpath.read_text(encoding="utf-8")
    return "(verdict 缺失)"


def open_review_pr(case: dict, dry_run: bool = False) -> str:
    """commit reviews/<case_id>/{findings,verdict,README} → 開分支 →(可)gh pr create。

    回傳:PR URL(實際模式)或 dry-run 說明字串。
    無遠端時自動轉 dry-run(今天的情況)。
    """
    case_id = case["case_id"]
    workspace = config.workspace_dir(case_id)
    rel_prefix = f"reviews/{case_id}/"

    # 0) 安全護欄:不可有與本案無關的已 staged 變更(會被掃進審查 commit)
    _assert_no_unrelated_staged(rel_prefix)

    # 1) 橋接:runtime 產物 → tracked reviews/
    stage_review_outputs(case, workspace)

    # 2) 無遠端 → 強制 dry-run
    if not dry_run and not _has_remote():
        print("[git_ops] 偵測不到 git remote,自動轉 dry-run(只本機 commit,跳過 push/PR)。")
        dry_run = True

    original_branch = _current_branch()
    branch = f"review/{case_id}"

    # 3) 開分支 + add + commit
    if _git(["rev-parse", "--verify", branch], check=False).returncode == 0:
        _git(["switch", branch])
    else:
        _git(["switch", "-c", branch])

    try:
        _git(["add", rel_prefix])
        # 沒東西可 commit?(理論上不該,保險起見)
        if _git(["diff", "--cached", "--quiet"], check=False).returncode == 0:
            raise RuntimeError(f"沒有可提交的審查產出於 {rel_prefix}")
        _git(["commit", "-m", f"review({case_id}): security findings + recommendation"])

        if dry_run:
            return (
                f"[dry-run] 已在分支 {branch} 本機 commit {rel_prefix};"
                f"跳過 push + PR。檢視:git show {branch}"
            )

        # 4) 實際模式:push + gh pr create
        push = _git(["push", "-u", "origin", branch], check=False)
        if push.returncode != 0:
            raise RuntimeError(f"git push 失敗:{push.stderr.strip()}")

        pr = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", f"Review: {case_id}",
                "--body", _verdict_summary(case),
                "--base", config_default_branch(),
                "--head", branch,
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if pr.returncode != 0:
            raise RuntimeError(
                "gh pr create 失敗(gh 未登入?)。原訊息:\n" + pr.stderr.strip()
            )
        return pr.stdout.strip()
    finally:
        # 不論成敗都回到原分支,避免 daemon 卡在審查分支
        _git(["switch", original_branch], check=False)


def config_default_branch() -> str:
    """PR base 分支。預設 main。"""
    return "main"
