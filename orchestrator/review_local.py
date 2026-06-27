"""本機觸發審查的 CLI(不經 Slack)。也是 Step 2 的開發 / 測試 harness。

設計定位(見 plan):這不是對外的「個人入口」——對外的個人深挖是委員用自己的
Cowork(design §6.3)。這支只是把一個 local case 丟進**同一條** queue,
讓 worker 走**同一條** pipeline,證明整條神經通,且免 Slack token。

跑法(repo 根目錄):
    python -m orchestrator.review_local --files <裝著提交文件的資料夾>

它會:計算各檔 sha256 → 組 local payload → enqueue → 同步跑一次 worker.run_once()
→ 印出結果(findings 摘要 + PR / dry-run 行)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import queue, worker
from .config import config


def _make_case_id() -> str:
    """可讀、可排序的 local case id:2026-0627-143005-LOCAL。

    自帶一份(不 import slack_listener,避免拉進 slack_bolt 相依)。
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m%d-%H%M%S")
    return f"{ts}-LOCAL"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_payload(files_dir: Path) -> dict:
    """掃描資料夾,組一筆 local review payload。"""
    files = []
    for f in sorted(files_dir.iterdir()):
        if f.is_file():
            files.append({"name": f.name, "sha256": _sha256(f)})
    if not files:
        raise SystemExit(f"資料夾沒有任何檔案可審:{files_dir}")

    case_id = _make_case_id()
    return {
        "case_id": case_id,
        "type": "review",
        "source": {"type": "local", "dir": str(files_dir.resolve())},
        "submitter": "local",
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="本機觸發一次審查(免 Slack)。")
    parser.add_argument(
        "--files", required=True,
        help="裝著提交文件的資料夾路徑(該夾內的檔都會被審)。",
    )
    parser.add_argument(
        "--enqueue-only", action="store_true",
        help="只入列、不立刻跑 worker(交給常駐 worker 撈)。",
    )
    args = parser.parse_args()

    files_dir = Path(args.files).expanduser()
    if not files_dir.is_dir():
        raise SystemExit(f"找不到資料夾:{files_dir}")

    payload = build_payload(files_dir)
    path = queue.enqueue(payload["case_id"], payload)
    print(f"[review_local] 已入列 case={payload['case_id']}({len(payload['files'])} 檔)")
    print(f"[review_local]   queue -> {path}")
    print(f"[review_local]   runtime dir = {config.runtime_dir}")

    if args.enqueue_only:
        print("[review_local] --enqueue-only:交給常駐 worker 處理。")
        return

    print("[review_local] 同步跑一次 worker.run_once()…")
    processed = worker.run_once()
    if not processed:
        print("[review_local] (queue 沒撈到 case?——可能已被常駐 worker 取走)")
        return

    # 印 findings 摘要(若有)
    ws = config.workspace_dir(payload["case_id"])
    fpath = ws / "findings" / "security.json"
    if fpath.exists():
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            n = len(data.get("findings", []))
            sev = {}
            for fi in data.get("findings", []):
                sev[fi.get("severity", "?")] = sev.get(fi.get("severity", "?"), 0) + 1
            sev_str = ", ".join(f"{k}:{v}" for k, v in sorted(sev.items())) or "(無)"
            print(f"[review_local] findings/security.json:{n} 條({sev_str})")
        except (json.JSONDecodeError, UnicodeDecodeError):
            print("[review_local] findings/security.json 存在但無法解析")
    print(f"[review_local] 工作區:{ws}")


if __name__ == "__main__":
    main()
