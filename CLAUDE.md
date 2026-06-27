# Review Committee Agent Team

> Claude Code 進到這個 repo,先讀這份。它告訴你**這專案是什麼、檔案怎麼擺、以及最重要的——哪些決策不能違反**。
> 設計全文見 `co-worker-agent-team-design.md`(在上層目錄)。這份是給「在 repo 裡幹活的 Claude」的精煉定向。

---

## 一句話

一個**專案上線審查團隊**:有人在 Slack `@claude` 並附上專案文件 → 桌機接到 → 跑多維度審查(資安/隱私/法遵/維運)→ 把推薦寫成 GitHub PR → 回 Slack 貼連結 + @指定委員去簽。**Agent 給推薦,人做裁決。**

## 最高鐵律(違反這些就是做錯了)

1. **Agent 給推薦,人做裁決。** AI 永遠不是「能不能上線」的最終權威。真正的 go/no-go 簽核 = **人 merge 那個 PR**(CODEOWNERS 強制),不是 agent 自己決定。
2. **外圈確定性、內圈推理。** 有副作用且絕不能漏的事(開 PR、commit、貼 Slack、@人)由 **Python(`orchestrator/`)**做,用迴圈/條件,不交給 model「記得做」。需要隔離與判斷的 fan-out 審查交給 **一個 Claude session + subagent**。
3. **git 只放會受益於版本控制的東西。** 受治理、改得慢、要留痕的「腦」(principles/contracts/rubrics/agents/skills)和「審查紀錄」(reviews/**/findings, verdict)進 git。**機密大檔、原始提交 bytes、佇列、下載副本、secrets 永不進 git**(在 `.runtime/`,已 gitignore)。
4. **不另架前端/公開 endpoint。** 桌機用 Slack **Socket Mode**(對外連 WebSocket)接事件,不需要公開 IP/憑證/serverless。
5. **skill 是 thin shim,動態內容住 GitHub。** skill 只說「去 repo 讀哪幾個檔、產什麼格式」,rubric/原則執行時 fetch。改 rubric = 開 PR,merge 後下次跑就吃到新版,不重發 skill。

## 兩道閘(系統的靈魂)

- **自主閘**:可逆×影響小 → 自動(讀提交、跑分析、寫 findings、更新 case README、貼草稿到頻道)。不可逆/影響大 → 停下問人(**go/no-go 裁決、否決專案 → 走 PR + CODEOWNERS**)。判準在 `principles/autonomy-gate.md`。
- **Feedback 迴圈(中央化)**:委員透過 **Slack 1:1** 跟主機給回饋 → 落 **中央 feedback store**(`.runtime/feedback/`,不進 git)→ 排程的 **feedback-synthesis** agent 定期彙整成 **rubric/skill 修改提案(PR)** → **由人覆核 merge** 才生效(走 skills/rubrics 的 CODEOWNERS)。**全部執行集中在中央主機,不走個人訂閱。**

## 兩段式流程

```
監聽(Step 1,純機械,無 model)
  Slack @claude + 檔案
   → slack_listener.py:下載檔到 .runtime/ → 回 ack「收到 case-xxx」→ 寫 queue
審查(Step 2)
  worker.py 輪詢 queue
   → 佈置 case 工作區
   → 叫起【一個】claude session 跑 run-review skill:
        intake → 平行 spawn 4 顆 lens subagent(各載自己 rubric)→ synthesize → verdict
   → ★Python 驗收產出完整性(4 findings + verdict 都在?缺就不開 PR、回報)
   → git commit + gh pr create
   → 回 Slack 貼 PR 連結 + @指定委員
```

## 目錄速查

| 路徑 | 是什麼 | 進 git? | 改它要 |
|---|---|---|---|
| `principles/` `contracts/` | 政策、判準、裁決政策、輸出契約 | ✅ | PR + 人 merge |
| `rubrics/` | 各維度審查 rubric(被 skill fetch) | ✅ | PR + 人 merge |
| `agents/` | 各 agent 的 system prompt | ✅ | PR |
| `skills/` | thin shim(去哪讀、產什麼) | ✅ | PR |
| `reviews/<case-id>/` | 每案工作區:findings/verdict/狀態 | ✅(紀錄) | findings 自動;**verdict 要人 merge** |
| `orchestrator/` | 桌機 daemon(Python) | ✅ | 一般 PR |
| `scripts/` `site/` `.github/` | dashboard 等不需 model 的 ops | ✅ | 一般 PR |
| `.runtime/` | secrets / queue / 下載副本 / log | ❌ gitignore | — |

## 重要產出契約

- 每顆 lens 輸出符合 `contracts/finding.schema.json` 的 `findings.json`。
- 怎麼把 findings 權衡成 go/no-go/帶條件、哪些必須人簽,在 `contracts/verdict-policy.md`。

## 現在進度

見 `IMPLEMENTATION_PLAN.md`。簡言之:Step 1(Slack 監聽神經)優先,可獨立驗收;Step 2(審查 + GitHub)其次。
