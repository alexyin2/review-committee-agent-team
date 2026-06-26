"""Step 1 — Slack 監聽神經(純機械,無 model)。

設計鐵律(見 CLAUDE.md):
  - 這層**不叫任何 model**。偵測 @claude + 附檔 → 下載 → 回 ack → 寫 queue,全是機械動作。
  - 用 Slack Socket Mode:桌機**對外**連 WebSocket,不需要公開 endpoint / 憑證 / serverless。
  - 「收事件」與「做事」拆開:這裡只 ack + 落 queue;真正審查由 worker.py 撈 queue 處理。

驗收標準:Slack @claude 附 PDF → .runtime/ 出現該檔 + queue 多一筆 → 頻道看到 ack。

跑法(在 repo 根目錄):
    python -m orchestrator.slack_listener
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from . import queue, slack_client
from .config import config


def _make_case_id(channel: str) -> str:
    """可讀、可排序的 case id:2026-0627-143005-C01ABCD。"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m%d-%H%M%S")
    return f"{ts}-{channel}"


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def handle_mention(event, say, client, logger):
    """有人在頻道 @claude。帶檔 → 建 case、下載、ack、入列;無檔 → 提示附檔。

    註冊在 build_app() 裡;抽成具名函式讓 import 不需網路、也方便單測。
    """
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts")
    user = event.get("user", "")
    files = event.get("files", []) or []

    # 選填:限定只在指定頻道作業
    if config.review_channel and channel != config.review_channel:
        logger.info("忽略非審查頻道的 mention: %s", channel)
        return

    if not files:
        say(thread_ts=thread_ts, text="收到呼叫，但沒看到附件檔。請把專案文件附在 @claude 的訊息裡。")
        return

    case_id = _make_case_id(channel)
    workspace_files = config.workspace_dir(case_id) / "files"

    saved = []
    for f in files:
        try:
            local = slack_client.download_file(f, workspace_files)
            saved.append({
                "name": local.name,
                "sha256": _sha256(local),
                "slack_file_id": f.get("id", ""),
            })
        except Exception as e:  # 下載失敗不應吞掉——回報、記錄
            logger.exception("下載檔案失敗: %s", f.get("name"))
            say(thread_ts=thread_ts, text=f"⚠️ 下載 `{f.get('name')}` 失敗：{e}")
            return

    permalink = ""
    try:
        resp = client.chat_getPermalink(channel=channel, message_ts=event["ts"])
        permalink = resp.get("permalink", "")
    except Exception:
        logger.warning("取 permalink 失敗，略過")

    payload = {
        "case_id": case_id,
        "source": {"slack_permalink": permalink},
        "channel": channel,
        "thread_ts": thread_ts,
        "submitter": user,
        "files": saved,
    }
    queue.enqueue(case_id, payload)

    file_list = "、".join(s["name"] for s in saved)
    say(
        thread_ts=thread_ts,
        text=f"✅ 收到 {len(saved)} 個檔（{file_list}），已建立 `{case_id}`，排入審查佇列。",
    )
    logger.info("已入列 case=%s files=%d", case_id, len(saved))


def build_app() -> App:
    """延後建立 App,並關掉建構期的 auth.test(否則 import/啟動都要先連網)。
    真正的認證在 Socket Mode 連線時發生。"""
    app = App(token=config.slack_bot_token, token_verification_enabled=False)
    app.event("app_mention")(handle_mention)
    return app


def main() -> None:
    config.require_slack_tokens()
    app = build_app()
    handler = SocketModeHandler(app, config.slack_app_token)
    print(f"[listener] Socket Mode 連線中… 監聽頻道："
          f"{config.review_channel or '(全部)'}")
    handler.start()


if __name__ == "__main__":
    main()
