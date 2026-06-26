"""本機檔案佇列。listener 寫入,worker 撈出。

為何是「移動檔案」而非真正的 MQ:零外部依賴、最穩、看得見。
  .runtime/queue/incoming/   ← listener 寫入新 case
  .runtime/queue/processing/ ← worker 撈起時 move 過來(崩了還在這,可重撈)
  .runtime/queue/done/       ← 處理完 move 過來

之後若要把佇列換成 GitHub issue / Notion,只動這個檔,listener 與 worker 不變。
純標準庫,可離線測試。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import config

INCOMING = config.queue_dir / "incoming"
PROCESSING = config.queue_dir / "processing"
DONE = config.queue_dir / "done"


def _ensure_dirs() -> None:
    for d in (INCOMING, PROCESSING, DONE):
        d.mkdir(parents=True, exist_ok=True)


def enqueue(case_id: str, payload: dict) -> Path:
    """Step 1:把 payload 寫成 incoming/<case_id>.json。回傳路徑。"""
    _ensure_dirs()
    path = INCOMING / f"{case_id}.json"
    tmp = path.with_suffix(".json.tmp")
    # 先寫 tmp 再 rename,避免 worker 讀到寫到一半的檔(atomic)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)
    return path


def claim_next() -> dict | None:
    """Step 2:把最舊的 incoming move 到 processing 並回傳其 payload;無則 None。"""
    _ensure_dirs()
    candidates = sorted(INCOMING.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return None
    src = candidates[0]
    dst = PROCESSING / src.name
    src.rename(dst)
    return json.loads(dst.read_text(encoding="utf-8"))


def mark_done(case_id: str) -> None:
    """Step 2:把 processing/<case_id>.json move 到 done。"""
    _ensure_dirs()
    src = PROCESSING / f"{case_id}.json"
    if src.exists():
        shutil.move(str(src), str(DONE / src.name))
