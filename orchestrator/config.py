"""設定載入:config.toml(可選)+ .runtime/secrets.toml(放 token)。

設計:不依賴 Slack SDK,純標準庫——讓 queue / config 可離線測試。
真正的 token 只放 .runtime/secrets.toml(已 gitignore),絕不進 config.toml。
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# repo 根目錄 = 這個檔的上上層(orchestrator/ 的 parent)
REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


class Config:
    """合併 config.toml + secrets.toml + 環境變數,提供 Step 1 需要的欄位。"""

    def __init__(self) -> None:
        cfg = _load_toml(REPO_ROOT / "orchestrator" / "config.toml")
        runtime_cfg = cfg.get("runtime", {})
        slack_cfg = cfg.get("slack", {})
        review_cfg = cfg.get("review", {})

        # .runtime 目錄(queue / 下載副本 / secrets / log)
        self.runtime_dir = REPO_ROOT / runtime_cfg.get("dir", ".runtime")
        self.poll_interval = int(runtime_cfg.get("poll_interval_seconds", 10))

        secrets = _load_toml(self.runtime_dir / "secrets.toml")
        slack_secrets = secrets.get("slack", {})

        # token:環境變數優先,否則讀 secrets.toml。Socket Mode 需要兩個。
        self.slack_bot_token = (
            os.environ.get("SLACK_BOT_TOKEN") or slack_secrets.get("bot_token", "")
        )
        self.slack_app_token = (
            os.environ.get("SLACK_APP_TOKEN") or slack_secrets.get("app_token", "")
        )

        # 選填:限定監聽頻道 / 預設 @ 的委員
        self.review_channel = slack_cfg.get("review_channel", "")
        self.default_reviewer = slack_cfg.get("default_reviewer", "")

        # 內圈叫起 claude 的方式 + model 分層(design §10.6)。環境變數可覆寫。
        self.claude_cmd = os.environ.get("REVIEW_CLAUDE_CMD") or review_cfg.get(
            "claude_cmd", "claude"
        )
        self.claude_model = os.environ.get("REVIEW_CLAUDE_MODEL") or review_cfg.get(
            "claude_model", "us.anthropic.claude-opus-4-8"
        )
        self.rubric_source = review_cfg.get("rubric_source", "local")
        # 本切片只跑 security;config 可列更多維度供 dashboard / 未來 fan-out 用。
        self.review_lenses = review_cfg.get("lenses", ["security"])

    # ---- 衍生路徑 ----
    @property
    def queue_dir(self) -> Path:
        return self.runtime_dir / "queue"

    def workspace_dir(self, case_id: str) -> Path:
        return self.runtime_dir / "workspace" / case_id

    def require_slack_tokens(self) -> None:
        """Step 1 啟動前的明確檢查,給出可行動的錯誤訊息。"""
        missing = []
        if not self.slack_bot_token:
            missing.append("bot_token (xoxb-...)")
        if not self.slack_app_token:
            missing.append("app_token (xapp-...)")
        if missing:
            raise SystemExit(
                "缺少 Slack token:" + ", ".join(missing) + "\n"
                f"請在 {self.runtime_dir / 'secrets.toml'} 填入,格式:\n"
                "  [slack]\n"
                '  bot_token = "xoxb-..."\n'
                '  app_token = "xapp-..."\n'
                "或設環境變數 SLACK_BOT_TOKEN / SLACK_APP_TOKEN。"
            )


# 單例,import 即用
config = Config()
