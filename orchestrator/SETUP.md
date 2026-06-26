# Step 1 設定指南 — 讓 Slack 能呼叫桌機

跑起 `slack_listener.py` 前,要先建一個 Slack app 拿兩個 token。全程在 workspace 層級,**不需** tenant/org admin。

## 1. 建 Slack app

1. 到 <https://api.slack.com/apps> → **Create New App** → **From scratch**。
2. 取名(如 `review-committee`),選你的 workspace。

## 2. 開 Socket Mode(關鍵——讓桌機免公開 endpoint)

1. 左側 **Socket Mode** → 打開 **Enable Socket Mode**。
2. 它會要你建一個 **App-Level Token**,scope 勾 `connections:write` → 產生後複製 `xapp-...`。

## 3. 設 Bot scopes

左側 **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** 加:

- `app_mentions:read` — 收 @claude
- `files:read` — 下載附檔
- `chat:write` — 回訊息

## 4. 訂閱事件

左側 **Event Subscriptions** → 打開 → **Subscribe to bot events** 加 `app_mention`。
(Socket Mode 下不需填 Request URL。)

## 5. 裝到 workspace

**OAuth & Permissions** → **Install to Workspace** → 同意 → 複製 **Bot User OAuth Token** `xoxb-...`。

## 6. 把兩個 token 放進 .runtime/secrets.toml

```bash
cp .runtime/secrets.example.toml .runtime/secrets.toml
# 編輯填入 bot_token (xoxb-) 與 app_token (xapp-)
```

(或設環境變數 `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN`。)

## 7. 把 bot 邀進頻道、跑起來

1. 在要監聽的 Slack 頻道打 `/invite @review-committee`。
2. (選填)把該頻道的 channel id 填進 `orchestrator/config.toml` 的 `review_channel`,限定只在那裡作業。

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m orchestrator.slack_listener
```

## 8. 驗收

在頻道 `@review-committee` 並**附一個檔** → 應看到:

- 頻道回「✅ 收到 N 個檔…已建立 case-…」
- `.runtime/workspace/<case-id>/files/` 出現該檔
- `.runtime/queue/incoming/<case-id>.json` 多一筆

先不接審查——這步只證明「呼叫→收檔→回話→入列」這條神經通了。

> 離線想先測 config+queue(免 token):`python -m orchestrator.smoke_test`
