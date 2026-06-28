"""Slack 薄包裝:下載檔案 / 回訊息 / @人。把 Slack API 細節關在這一個檔。

需要的 scopes:app_mentions:read、files:read、chat:write。
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from .config import config


def download_file(file_obj: dict, dest_dir: Path) -> Path:
    """下載 Slack 私有檔的 bytes 到 dest_dir。回傳本機路徑。

    注意:url_private_download 是私有的,一定要帶 Bearer bot token,
    否則拿到的是登入頁 HTML 而非檔案內容。
    """
    url = file_obj.get("url_private_download") or file_obj["url_private"]
    name = file_obj.get("name") or file_obj.get("id", "file")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name

    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {config.slack_bot_token}"}
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (Slack 受信任來源)
        data = resp.read()
    dest.write_bytes(data)
    return dest


def mention(user_id: str) -> str:
    """回傳 Slack mention 語法 <@U123>,給「@指定委員」用。"""
    return f"<@{user_id}>"


def post_thread(channel: str, thread_id: str, text: str) -> str | None:
    """把一則訊息貼回 thread。回傳貼出訊息的 ts;無 token 時走 print 樁回 None。

    這是 worker(外圈)在 thread 內出聲的唯一管道——追問缺料、貼 verdict 草稿、
    貼 PR 連結 + @委員都走這裡。worker 跑在獨立 process,沒有 listener 的 `say`
    closure,所以自己用 bot token 開 WebClient。

    reporter 樁:還沒設 token(Step 1 尚未端到端驗收)時不該炸——降級成 print,
    讓整條流程離線可跑可測。設好 token 後零改動切換成真 Slack(鐵律:可離線測)。
    """
    if not config.slack_bot_token:
        # 無 token:印出來(取代 worker._report_* 的 [slack-TODO] 樁),回 None
        print(f"[slack-stub] post to {channel} thread={thread_id}:\n{text}")
        return None

    # 延後 import:讓 config / 離線測試不必裝 slack_sdk
    from slack_sdk import WebClient

    client = WebClient(token=config.slack_bot_token)
    resp = client.chat_postMessage(channel=channel, thread_ts=thread_id, text=text)
    return resp.get("ts")
