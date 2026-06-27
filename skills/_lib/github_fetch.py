"""共用 helper:執行時從 GitHub 取動態內容(rubric / 原則 / verdict-policy)。

thin-shim 的心臟(design §7.2):skill 只說「去哪讀」,內容住 GitHub、執行時 fetch。
改 rubric = 開 PR,merge 後下次跑就吃到新版,不用重發 skill。

讀 main(已治理);要更穩可 pin 到 release tag / commit。
私有 repo 用唯讀 fine-grained PAT 或 GitHub App token;公開可直接 raw。
政策檔很小可每次讀;知識庫大應「需要時才查」。

兩種模式:
  - **local**(開發 / 尚未推遠端):直接讀本機 checkout。
    觸發條件:ref == "local" 或環境變數 REVIEW_FETCH_LOCAL=1。
    worker.py 跑內圈時會設 REVIEW_FETCH_LOCAL=1,讓 lens 預設讀本機。
  - **real**:GET raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>,
    owner/repo 由環境變數 REVIEW_GH_REPO="owner/repo" 提供(尚未設遠端前會明確報錯)。
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

DEFAULT_REF = "main"
LOCAL_REF = "local"

# repo 根目錄 = 這個檔的上上上層(skills/_lib/github_fetch.py → repo root 往上三層)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _use_local(ref: str) -> bool:
    """是否走本機模式。ref=='local' 或 REVIEW_FETCH_LOCAL=1 都算。"""
    if ref == LOCAL_REF:
        return True
    return os.environ.get("REVIEW_FETCH_LOCAL", "") not in ("", "0", "false", "False")


def _fetch_local(path: str) -> str:
    """從本機 checkout 讀單一檔。path 相對 REPO_ROOT。"""
    full = (REPO_ROOT / path).resolve()
    if not full.exists():
        raise FileNotFoundError(
            f"github_fetch 本機模式找不到檔:{full}(path={path!r}, repo_root={REPO_ROOT})"
        )
    return full.read_text(encoding="utf-8")


def _fetch_remote(path: str, ref: str, token: str | None) -> str:
    """從 GitHub raw 取單一檔。owner/repo 由 REVIEW_GH_REPO 提供。"""
    repo = os.environ.get("REVIEW_GH_REPO", "")
    if not repo or "/" not in repo:
        raise NotImplementedError(
            "尚未設定遠端 repo。請設環境變數 REVIEW_GH_REPO=\"owner/repo\"(或改用 ref='local')。"
        )
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (GitHub 受信任來源)
        return resp.read().decode("utf-8")


def fetch(path: str, ref: str = DEFAULT_REF, token: str | None = None) -> str:
    """取單一治理檔內容(raw)。回傳文字。

    path:相對 repo root 的路徑,如 "rubrics/review-security.md"。
    ref :"local"(讀本機)/ "main" / tag / commit。預設讀本機由 REVIEW_FETCH_LOCAL 控制。
    token:私有 repo 的唯讀 token(只在 real 模式用)。
    """
    if _use_local(ref):
        return _fetch_local(path)
    return _fetch_remote(path, ref, token)
