"""模擬一個 Slack @claude 觸發——不需 token、不連網。

它跑的是**真正的** slack_listener.handle_mention(Step 1 的程式),只是:
  - 餵一個假的 app_mention event(帶一個假附檔);
  - 把 slack_client.download_file 換成「從本機樣本檔複製」(取代真正的 HTTP 下載);
  - say / client 用紀錄用的假物件,印出 bot 會回什麼。

證明的事:Slack 這條神經(收 mention → 下載到 .runtime/workspace → ack → 入列)
和 local CLI 走的是**同一條 queue**,只是 producer 不同。

跑法:
    python scripts/sim_slack_trigger.py [樣本檔路徑]
不給路徑就用內建的「不安全範例」。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from orchestrator import slack_client, slack_listener  # noqa: E402

SAMPLE = """# Demo Service — Launch Doc(Slack 提交)

A customer-facing web API submitted via Slack.

## Auth
No authentication on the admin endpoints yet.
The database password is hardcoded in config.py as DB_PASS="prod-secret-456".

## Data
We store user emails and plaintext passwords in MySQL. No encryption at rest.

## Ops
No logging or alerting. No dependency vulnerability scanning.
"""


class _FakeSay:
    """紀錄 bot 在頻道/thread 回了什麼。"""
    def __init__(self):
        self.messages = []

    def __call__(self, *, thread_ts=None, text=""):
        self.messages.append(text)
        print(f"  [slack bot 回覆] {text}")


class _FakeClient:
    """只實作 handle_mention 會用到的 chat_getPermalink。"""
    def chat_getPermalink(self, *, channel, message_ts):
        return {"permalink": f"https://example.slack.com/archives/{channel}/p{message_ts}"}


class _Logger:
    def info(self, *a): pass
    def warning(self, *a): pass
    def exception(self, *a): print("  [logger.exception]", *a)


def main() -> None:
    # 樣本檔:參數優先,否則寫一份內建的到暫存
    if len(sys.argv) > 1:
        sample_path = Path(sys.argv[1]).expanduser()
        if not sample_path.is_file():
            raise SystemExit(f"找不到樣本檔:{sample_path}")
    else:
        sample_path = REPO_ROOT / ".runtime" / "_sim_slack_sample.md"
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_text(SAMPLE, encoding="utf-8")

    # 把真正的 HTTP 下載換成「從本機樣本複製到工作區」——這是唯一的 stub
    def fake_download(file_obj, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file_obj["name"]
        dest.write_bytes(sample_path.read_bytes())
        return dest

    slack_client.download_file = fake_download
    # handle_mention 用 from-import 綁了同名符號,也要一起換
    slack_listener.slack_client.download_file = fake_download

    # 假的 app_mention event(就是 Slack 真的會送來的形狀)
    event = {
        "channel": "C0DEMO123",
        "ts": "1750000000.000100",
        "user": "U0SUBMITTER",
        "files": [{
            "id": "F0SAMPLE1",
            "name": "launch-doc.md",
            "url_private_download": "https://files.slack.com/…(被 stub 取代)",
        }],
    }

    say = _FakeSay()
    print("=== 模擬 Slack @claude(附檔)===")
    print(f"  樣本檔:{sample_path}")
    slack_listener.handle_mention(event, say, _FakeClient(), _Logger())
    print("=== handle_mention 結束(case 已入列,等 worker 撈)===")


if __name__ == "__main__":
    main()
