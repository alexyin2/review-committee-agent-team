"""前門:輪詢式 inbox + 可插拔通道 adapter(pull 不被 push)。

設計原則(見 memory poll-not-push-channel-adapters):
  鐵律 #4 從「用 Slack Socket Mode」(機制)升級為「**pull,不被 push**」(原則)。
  我們按自己的時鐘每約 10 分鐘去撈各通道 inbox 的新 @mention,不需要任何
  公開 endpoint / webhook。Teams 即時收訊要 Azure Bot + 公開 HTTPS,正是這要避開的;
  Graph 提供 pull(delta query),所以 Teams 之後也走同一個輪詢模型。

為何輪詢比 push 好(對這個 async 審查場景):
  - 天然批次化:同 thread 10 分鐘內連發多則,醒來一次就看到全部 →
    並發雙建 case / 重複 ack 的 race 直接蒸發(循序處理)。
  - 直接掛在現有排程骨架(scheduler.py / scheduled_tasks.HANDLERS),基礎建設一半已在。
  - 代價:首次回應最多延遲一個輪詢週期——對以小時/天計的審查無感。

這個檔只負責「把新訊息收進 case 持久層 + 丟一個信號」。真正的判斷(料夠不夠、
這人在反駁還是放行)由 worker 叫起 Claude 讀 brief 決定(見 agents/case-agent.md)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from . import case_store, queue
from .config import config


# --------------------------------------------------------------------------
# 通道無關的訊息形狀
# --------------------------------------------------------------------------
@dataclass
class Mention:
    """一則「有人 @我」的訊息,通道無關。

    channel + thread_id 共同決定 case 身分;links 是文件連結(先連結,attachment 退路)。
    """
    channel: str
    thread_id: str
    user: str
    text: str
    ts: str
    links: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)


class InboxAdapter(Protocol):
    """通道 adapter 介面。Slack 先做;Teams(Graph)後做,實作同一介面。

    fetch_new_mentions:回傳 (自 cursor 以來、@我 的訊息, 新 cursor)。
    cursor 由 poll_inbox 持久化(.runtime/inbox_cursor.json),adapter 不必自己存。
    """

    name: str

    def fetch_new_mentions(self, cursor: dict | None) -> tuple[list[Mention], dict]:
        ...


# --------------------------------------------------------------------------
# Slack adapter(重用 slack_client;主路徑改 pull,Socket Mode 降為可選即時實作)
# --------------------------------------------------------------------------
class SlackInboxAdapter:
    """用 Slack Web API 拉「自上次以來、@我」的訊息。

    取代 slack_listener 的 Socket Mode push 為**主路徑**(listener 仍保留為可選即時版)。
    需 scopes:channels:history、groups:history;@我 的偵測靠 bot user id 出現在 text。
    """

    name = "slack"

    def fetch_new_mentions(self, cursor: dict | None) -> tuple[list[Mention], dict]:
        # 真正接線(需 token)時:用 conversations.history(channel=review_channel,
        # oldest=cursor['last_ts'])撈訊息,過濾含 bot mention 者,組成 Mention。
        # 本切片:無 token 時回空(離線可測);真 API 接線屬 Slack token 就緒後。
        if not config.slack_bot_token:
            return [], (cursor or {})
        raise NotImplementedError(
            "SlackInboxAdapter 真 API 拉取待接線(需 conversations.history)。"
            "目前主路徑可用 slack_listener 的 Socket Mode 即時版,或離線測試走 fake adapter。"
        )


class GraphInboxAdapter:
    """Teams via Microsoft Graph(delta query)。佔位——需 Azure app 註冊 + admin consent。

    待實作:GET /teams/{id}/channels/{id}/messages/delta,帶 cursor(deltaLink),
    過濾 @我,組成 Mention。OneDrive/SharePoint 文件讀取共用同一套 Graph 認證。
    """

    name = "teams"

    def fetch_new_mentions(self, cursor: dict | None) -> tuple[list[Mention], dict]:
        raise NotImplementedError(
            "GraphInboxAdapter 待實作(需 Azure app 註冊 + ChannelMessage.Read.All admin consent)。"
        )


# --------------------------------------------------------------------------
# cursor 持久化
# --------------------------------------------------------------------------
def _cursor_path():
    return config.runtime_dir / "inbox_cursor.json"


def _load_cursor() -> dict:
    p = _cursor_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cursor(cursor: dict) -> None:
    p = _cursor_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cursor, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(p)


# --------------------------------------------------------------------------
# 信號:每 case 一個 collapse 檔名,同 case 多訊息合併成一個 pending 信號
# --------------------------------------------------------------------------
def _signal_file(case_id: str) -> str:
    """同 case 多訊息 collapse:固定檔名,enqueue 覆蓋 → 只留一個 pending 信號。"""
    return f"case-activity-{case_id}"


def enqueue_case_activity(case_id: str, *, channel: str, thread_id: str) -> None:
    """丟一個輕量 case-activity 信號讓 worker 醒來處理該 case 的當前 inbox+state。

    payload 刻意輕(不是不可變快照):真正的 context 在 case_store。
    type=case-activity 走 worker.run_once 的同一條 dispatch。
    """
    queue.enqueue(
        _signal_file(case_id),
        {
            "case_id": case_id,
            "type": "case-activity",
            "channel": channel,
            "thread_id": thread_id,
            "source": {"type": "inbox"},
        },
    )


# --------------------------------------------------------------------------
# 輪詢主流程(無 model、純機械:收訊息 → 落 case_store → 丟信號)
# --------------------------------------------------------------------------
def ingest_mention(m: Mention) -> str:
    """把一則 mention 收進 case 持久層,回傳對應 case_id。

    同 thread 併入同一 case(find_by_thread);沒有就建。listener/poll 只 append_inbox,
    **不寫 state**(單寫者原則,唯一寫者是 worker 的 drain_inbox)。
    """
    case_id = case_store.find_by_thread(m.channel, m.thread_id)
    if case_id is None:
        # 可讀+可排序的 id;真相來源仍是 thread index,case_id 字串不承擔查找
        case_id = f"{m.ts}-{m.channel}"
        case_store.create(case_id, channel=m.channel, thread_id=m.thread_id, submitter=m.user)
        case_store.register_thread(m.channel, m.thread_id, case_id)
    case_store.append_inbox(
        case_id,
        {"ts": m.ts, "user": m.user, "text": m.text, "links": m.links},
    )
    return case_id


def poll_inbox(adapter: InboxAdapter) -> dict:
    """跑一輪輪詢:撈新 mention → 收進 case_store → 對每個被碰到的 case 丟一個信號。

    回傳一段摘要(供排程回報)。對被碰到的 case 去重後各丟一個 collapse 信號,
    所以同 thread 連發多則只會讓 worker 醒來處理該 case 一次。
    """
    cursor = _load_cursor()
    chan_cursor = cursor.get(adapter.name)
    mentions, new_chan_cursor = adapter.fetch_new_mentions(chan_cursor)

    touched: dict[str, Mention] = {}  # case_id -> 任一則該 case 的 mention(取通道/thread)
    for m in mentions:
        case_id = ingest_mention(m)
        touched[case_id] = m

    for case_id, m in touched.items():
        enqueue_case_activity(case_id, channel=m.channel, thread_id=m.thread_id)

    cursor[adapter.name] = new_chan_cursor
    _save_cursor(cursor)

    return {
        "adapter": adapter.name,
        "mentions": len(mentions),
        "cases_touched": len(touched),
    }
