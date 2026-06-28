"""Case 持久層——綁 thread、跨多則訊息累積 context 的「有狀態實體」。

這是「對話 ≠ 產物」的落地(見 CLAUDE.md / memory conversation-not-vending-machine):
一則 mention 不再等於一個不可變 case。case 綁在 Slack/Teams thread 上,後續訊息
併入同一個 case,直到結晶成「值得請人裁決的推薦」才跨牆進 git(reviews/)。

刻意是「笨持久層」,**不是狀態機**(見 memory brief-driven-not-state-machine):
  - 沒有 transition() 表、沒有合法轉移 enum。
  - case 的「路徑」由 Claude 讀 brief 判斷(worker 叫起);這裡只負責「記住」。
  - status_note 是 Claude 自己維護的一段自由文字理解,不是我們列舉的狀態。

落點 .runtime/cases/<case_id>/(已被 .runtime/ gitignore;對話/草稿永不進 git,鐵律 #3):
  state.json    ← case 的當前快照(唯一寫者 = worker,避免 lost-update)
  inbox.jsonl   ← listener/poll 端 append 的新訊息(append-only,並發安全),worker drain 吸進 state

thread→case 身分:_index/<thread_key>.json,用 O_CREAT|O_EXCL 原子建立——
  同 thread 並發雙建只會成功一個(輪詢模型下本就循序,這是額外保險)。

純標準庫,可離線測。complement queue.py(傳輸)與 feedback_store.py(慢迴圈回饋)。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import config


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def _cases_dir() -> Path:
    return config.cases_dir


def _case_dir(case_id: str) -> Path:
    return config.case_state_dir(case_id)


def _state_path(case_id: str) -> Path:
    return _case_dir(case_id) / "state.json"


def _inbox_path(case_id: str) -> Path:
    return _case_dir(case_id) / "inbox.jsonl"


def _index_dir() -> Path:
    return _cases_dir() / "_index"


def _thread_key(channel: str, thread_id: str) -> str:
    """檔名安全的 thread key。channel + thread_id 共同決定身分。"""
    raw = f"{channel}__{thread_id}"
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)


# --------------------------------------------------------------------------
# 寫:唯一寫者 = worker(單寫者原則,避免 read-modify-write lost-update)
# --------------------------------------------------------------------------
def _atomic_write(case_id: str, state: dict) -> None:
    """唯一的 state 寫點。tmp 寫好再 rename(複用 queue.py 的 atomic 模式)。"""
    _case_dir(case_id).mkdir(parents=True, exist_ok=True)
    path = _state_path(case_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)


def create(case_id: str, *, channel: str, thread_id: str, submitter: str) -> dict:
    """建立新 case 的初始 state。idempotent:已存在則直接回傳既有 state。"""
    existing = load(case_id)
    if existing is not None:
        return existing
    now = _now()
    state = {
        "case_id": case_id,
        "channel": channel,
        "thread_id": thread_id,
        "submitter": submitter,
        "doc_links": [],          # OneDrive/SharePoint 連結(先連結;attachment 走退路)
        "context": [],            # thread 內累積訊息 [{ts, user, text}]
        "version": 0,             # 改版重審計數(每次 revise +1)
        "reviewed_version": -1,   # 上次跑審查時的 version(判斷料有沒有變)
        "status_note": "",        # Claude 維護的自由文字理解(非列舉狀態)
        "draft_msg_ts": "",       # worker 貼的 verdict 草稿 ts(改版可原地更新)
        "created_at": now,
        "updated_at": now,
    }
    _atomic_write(case_id, state)
    return state


def load(case_id: str) -> dict | None:
    """讀 case state;不存在回 None。"""
    path = _state_path(case_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save(case_id: str, state: dict) -> dict:
    """寫回整份 state(更新 updated_at)。worker 改完 state 後呼叫。"""
    state["updated_at"] = _now()
    _atomic_write(case_id, state)
    return state


def append_doc_link(case_id: str, link: str) -> dict:
    """記一個文件連結(去重)。"""
    state = load(case_id)
    if state is None:
        raise KeyError(f"case 不存在:{case_id}")
    if link and link not in state["doc_links"]:
        state["doc_links"].append(link)
    return save(case_id, state)


def set_status_note(case_id: str, note: str) -> dict:
    """持久化 Claude 對這個 case 的最新理解。"""
    state = load(case_id)
    if state is None:
        raise KeyError(f"case 不存在:{case_id}")
    state["status_note"] = note
    return save(case_id, state)


def bump_version(case_id: str) -> dict:
    """改版重審:version +1。實際重審/開 PR 由 worker 兌現。"""
    state = load(case_id)
    if state is None:
        raise KeyError(f"case 不存在:{case_id}")
    state["version"] += 1
    return save(case_id, state)


# --------------------------------------------------------------------------
# inbox:listener/poll 端 append(並發安全),worker drain 吸進 state
# --------------------------------------------------------------------------
def append_inbox(case_id: str, msg: dict) -> None:
    """把一則新訊息 append 到 case 的 inbox(append-only,跨 process 並發安全)。

    listener / poll 只走這裡,**不寫 state.json**——避免與 worker 的
    read-modify-write 互相覆蓋(單寫者原則)。msg 形狀:{ts, user, text, links?}。
    """
    _case_dir(case_id).mkdir(parents=True, exist_ok=True)
    line = json.dumps(msg, ensure_ascii=False)
    with _inbox_path(case_id).open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def drain_inbox(case_id: str) -> list[dict]:
    """worker 醒來:把 inbox 累積的訊息吸進 state.context(+ doc_links),清空 inbox。

    回傳這次吸收的訊息清單(供 worker 判斷有沒有新東西要處理)。
    讀 inbox → 併入 state → 截斷 inbox 檔。截斷前 worker 是唯一讀寫 state 者,
    且輪詢循序,故 drain 期間不會有人改 state(inbox 仍可被 append,下輪再 drain)。
    """
    state = load(case_id)
    if state is None:
        raise KeyError(f"case 不存在:{case_id}")
    inbox = _inbox_path(case_id)
    if not inbox.exists():
        return []

    drained: list[dict] = []
    for raw in inbox.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            drained.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    for msg in drained:
        state["context"].append(
            {"ts": msg.get("ts", ""), "user": msg.get("user", ""), "text": msg.get("text", "")}
        )
        for link in msg.get("links", []) or []:
            if link and link not in state["doc_links"]:
                state["doc_links"].append(link)

    if drained:
        save(case_id, state)
    # 截斷 inbox(已吸收的不再重吸);輪詢循序,worker 是唯一 drainer
    inbox.write_text("", encoding="utf-8")
    return drained


# --------------------------------------------------------------------------
# thread → case 身分(輪詢循序 + O_CREAT|O_EXCL 雙保險)
# --------------------------------------------------------------------------
def find_by_thread(channel: str, thread_id: str) -> str | None:
    """這個 thread 是否已有對應 case?回傳 case_id 或 None。"""
    idx = _index_dir() / f"{_thread_key(channel, thread_id)}.json"
    if not idx.exists():
        return None
    try:
        return json.loads(idx.read_text(encoding="utf-8")).get("case_id")
    except (json.JSONDecodeError, OSError):
        return None


def register_thread(channel: str, thread_id: str, case_id: str) -> str:
    """把 thread 綁到 case_id。原子建立:若已被搶先綁定,回傳既有的 case_id。

    用 O_CREAT|O_EXCL 確保「第一個贏」——即使兩個 process 同時想建,
    也只會成功一個,另一個讀回既有綁定。輪詢模型下本就循序,這是額外保險。
    """
    _index_dir().mkdir(parents=True, exist_ok=True)
    idx = _index_dir() / f"{_thread_key(channel, thread_id)}.json"
    payload = json.dumps({"case_id": case_id, "channel": channel, "thread_id": thread_id},
                         ensure_ascii=False)
    try:
        fd = os.open(idx, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return case_id
    except FileExistsError:
        # 已被搶先綁定:用既有的 case_id(忽略本次的)
        return find_by_thread(channel, thread_id) or case_id
