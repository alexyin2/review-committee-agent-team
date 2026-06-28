# Implementation Plan

> 分階段。每階段有**可獨立驗收的成果**,不必等下一階段。
> 設計依據:`co-worker-agent-team-design.md` §10;在 repo 內幹活的定向:`CLAUDE.md`。

---

## Step 1 — Slack 監聽神經(純機械,無 model)

**目標**:證明「Slack @claude + 附檔 → 桌機收到檔 → 回 ack → 入列」這條神經通。**完全不碰審查、不碰 GitHub。**

程式已寫成可跑版(離線 smoke test 通過、import/compile 通過)。剩下要**你本人操作**的是建 Slack app 拿 token,見 `orchestrator/SETUP.md`。

- [x] `orchestrator/config.py`:讀 config.toml + .runtime/secrets.toml,token 缺失給可行動錯誤。
- [x] `orchestrator/queue.py`:檔案佇列(incoming/processing/done,atomic 寫入)。
- [x] `orchestrator/slack_client.py`:`download_file`(帶 Bearer)/`mention`。
- [x] `orchestrator/slack_listener.py`:Socket Mode,`app_mention` → 下載 → ack → 入列;`build_app()` factory 讓 import 免連網。
- [x] `orchestrator/smoke_test.py`:離線驗證 config+queue(免 token)。
- [x] `orchestrator/SETUP.md`:建 Slack app / 拿 token / scopes 逐步清單。
- [ ] **(你)** 依 SETUP.md 建 Slack app,拿 bot token(xoxb-)+ app-level token(xapp-),放 `.runtime/secrets.toml`。
- [ ] **(你)** 把 bot 邀進頻道,跑 `python -m orchestrator.slack_listener`,做下方端到端驗收。
- [ ] `orchestrator/watchdog.py` 雛形:WebSocket 斷線重連、keep-awake(可延後到拓展)。

**驗收**:在 Slack 頻道 @claude 附一個 PDF → 桌機 `.runtime/` 出現該檔 + queue 多一筆 → 頻道看到 ack。

## Step 2 — 對話式審查同事(brief 驅動,非狀態機)+ GitHub

**目標**:case 綁 thread、跨多則訊息累積;Claude 讀 brief 判斷路徑,Python 兌現承諾;結晶成 PR 回對話。**不是**「一則 mention 跑一次就開 PR」的交易管線(見 memory conversation-not-vending-machine / brief-driven-not-state-machine)。

- [x] `contracts/finding.schema.json` + security lens 跑通驗證。
- [x] `rubrics/` security/privacy/legal/ops(本切片只 gate security)。
- [x] `skills/run-review/SKILL.md`:thin shim(intake→fan-out→synthesize 與產出位置)。
- [x] `agents/`:intake / review-lens / synthesizer + **`case-agent.md`(對話大腦 brief)**。
- [x] `orchestrator/case_store.py`:綁 thread 的笨持久層(state.json + inbox.jsonl + thread index)。
- [x] `orchestrator/inbox.py`:輪詢 + 可插拔 `InboxAdapter`(Slack 先;Teams/Graph 佔位)。
- [x] `orchestrator/slack_client.post_thread`:reporter seam(無 token 降級 print)。
- [x] `orchestrator/worker.py`:撈 `case-activity` → drain → 叫大腦拿行動計畫 → **Python 逐項執行+完整性驗收** → commit → (有 remote)`gh pr create` → 回對話 + @委員。
- [x] `orchestrator/git_ops.py`:改版重審冪等(清舊產出、無變更不炸、commit 帶 version)。
- [x] `.github/CODEOWNERS`:`reviews/**/verdict/` 與「腦」變更強制指定人 merge。
- [x] `contracts/verdict-policy.md`:findings → go/no-go/帶條件,哪些必須人簽。
- [ ] **(你)** 設 Slack token 後接 `SlackInboxAdapter.fetch_new_mentions` 真 API(`conversations.history`)。
- [ ] 擴從 security 一顆 lens → 四維 subagent fan-out。

**驗收**:在 thread 開話題(可分多則補件)→ agent 對話追問→ 料齊自動審→ 貼推薦草稿→ 委員說 OK → 結晶成 PR(含 findings + 推薦)→ 對話收到連結 + @到人 → 人 merge = 正式裁決。離線驗收見 `smoke_test`(fake adapter + 假行動計畫,不需 token)。

## Step 3+ — 拓展(之後再展開,先記著)

- [x] **中央化 Feedback 迴圈**(取代原「個人 Claude 同步」):委員 Slack 1:1 → 中央 feedback store → 排程 `feedback-synthesis` 彙整成 skill 修改提案(PR)→ 人覆核 merge。**不走個人訂閱。**(`orchestrator/feedback_store.py`、`scheduled_tasks.run_feedback_synthesis`)
- [x] **Dashboard / 靜態站**:`scripts/build_site.py`(+`generate_dashboard.py`)+ `site/` + `.github/workflows/{dashboard,pages}.yml`。Pages 只放消毒過的彙總(個人帳號 Pages 必公開)。
- [x] **排程任務(部分)**:`daily-digest`、`feedback-synthesis` 已實作;`overdue-reminder`、`submission-patrol` 留骨架。
- [ ] **Meeting Companion**:會議即時提點(互動式,跟 async 審查分開)。
- [ ] **OneDrive/SharePoint 文件**:訊息帶連結,審查時拓臨時副本(`worker._fetch_docs` 已有本機/`file://` 路徑;http(s) 待接 Graph)。先連結、保留 attachment 退路,穩了再考慮強制。
- [ ] **Teams 第二 adapter**:`inbox.GraphInboxAdapter`(已佔位)走 Microsoft Graph delta query 輪詢,接同一條 case_store/worker。需 Azure app 註冊 + admin consent(`ChannelMessage.Read.All`)。與 OneDrive 共用同一套 Graph 認證。
- [ ] **branch protection + 真實 CODEOWNERS**:把 `@org/review-committee` 換成真實帳號,並開 `main` 的 PR 必審,讓「人裁決」在 GitHub 上強制生效。
