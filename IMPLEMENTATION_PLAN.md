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

## Step 2 — 審查 pipeline + GitHub

**目標**:queue 裡的 case 被自動審完,產出走 PR,結果回 Slack。

- [ ] `contracts/finding.schema.json` 定案 + 一個 lens 先跑通驗證。
- [ ] `rubrics/` 先做 3–4 個真正會 gate 上線的維度(security/privacy/legal/ops)。
- [ ] `skills/run-review/SKILL.md`:thin shim,定義 intake→fan-out→synthesize 的步驟與產出位置。
- [ ] `agents/` 各 system prompt(intake / review-lens 共用骨架 / synthesizer)。
- [ ] `orchestrator/worker.py`:輪詢 queue → 佈置工作區 → 叫起 `claude` 跑 run-review → **產出完整性檢查** → commit → `gh pr create` → 回 Slack 貼 PR + @委員。
- [ ] `.github/CODEOWNERS`:`reviews/**/verdict/` 與「腦」變更強制指定人 merge。
- [ ] `contracts/verdict-policy.md`:findings → go/no-go/帶條件,哪些必須人簽。

**驗收**:丟一個提交 → 自動產生一個 PR(含各維度 findings + 推薦)→ Slack 收到連結 + @到人 → 人 merge = 正式裁決。

## Step 3+ — 拓展(之後再展開,先記著)

- [x] **中央化 Feedback 迴圈**(取代原「個人 Claude 同步」):委員 Slack 1:1 → 中央 feedback store → 排程 `feedback-synthesis` 彙整成 skill 修改提案(PR)→ 人覆核 merge。**不走個人訂閱。**(`orchestrator/feedback_store.py`、`scheduled_tasks.run_feedback_synthesis`)
- [x] **Dashboard / 靜態站**:`scripts/build_site.py`(+`generate_dashboard.py`)+ `site/` + `.github/workflows/{dashboard,pages}.yml`。Pages 只放消毒過的彙總(個人帳號 Pages 必公開)。
- [x] **排程任務(部分)**:`daily-digest`、`feedback-synthesis` 已實作;`overdue-reminder`、`submission-patrol` 留骨架。
- [ ] **Meeting Companion**:會議即時提點(互動式,跟 async 審查分開)。
- [ ] **OneDrive 上傳**:用 browser-use 繞 Graph 把檔案副本推上公司雲(合規需求,與聊天前門解耦)。
- [ ] **Teams 第二 adapter**:若之後要,Teams 走 Power Automate,接同一個 queue。
- [ ] **branch protection + 真實 CODEOWNERS**:把 `@org/review-committee` 換成真實帳號,並開 `main` 的 PR 必審,讓「人裁決」在 GitHub 上強制生效。
