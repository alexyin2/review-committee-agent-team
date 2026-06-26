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
