# Review Committee Agent Team

> Claude Code 進到這個 repo,先讀這份。它告訴你**這專案是什麼、檔案怎麼擺、以及最重要的——哪些決策不能違反**。
> 設計全文見 `co-worker-agent-team-design.md`(在上層目錄)。這份是給「在 repo 裡幹活的 Claude」的精煉定向。

---

## 一句話

一個**專案上線審查團隊(數位同事)**:有人在 Slack/Teams `@claude` 開個話題、丟專案文件(連結或附檔)→ 桌機按自己的時鐘輪詢撈到 → 在對話裡把事情問清楚、跑多維度審查(資安/隱私/法遵/維運)→ 把推薦結晶成 GitHub PR → 回對話貼連結 + @指定委員去簽。**Agent 給推薦,人做裁決。它是同事,不是販賣機。**

## 最高鐵律(違反這些就是做錯了)

1. **Agent 給推薦,人做裁決。** AI 永遠不是「能不能上線」的最終權威。真正的 go/no-go 簽核 = **人 merge 那個 PR**(CODEOWNERS 強制),不是 agent 自己決定。開 PR ≠ agent 裁決了;那只是「把推薦結晶成可被人裁決的東西」。
2. **路徑流動(Claude)、承諾不漏(Python)。** case 該往哪走的**判斷**(料夠不夠審、對方在反駁還是放行、缺什麼怎麼問、要不要重審)由 **Claude 讀 brief(`agents/case-agent.md`)** 決定,可反覆、可回頭。有副作用且**絕不能漏的承諾**(開 PR、commit、貼訊息、@人、產出完整性驗收)由 **Python(`orchestrator/`)**逐項執行+驗收,不交給 model「記得做」。Claude 在行動計畫裡「請求」,Python 兌現。**絕不讓 model 直接觸發開 PR。**
3. **git 放決策、不放審議。** 受治理、改得慢、要留痕的「腦」(principles/contracts/rubrics/agents/skills)和**結晶後的審查紀錄**(reviews/**/findings, verdict)進 git。**對話、草稿、累積 context、被推翻的想法、機密大檔、原始 bytes、佇列、下載副本、secrets 永不進 git**(在 `.runtime/`,已 gitignore)。試金石:「未來稽核者/簽 PR 的委員,需不需要這東西才懂推薦了什麼、依據、誰拍板?」需要才進 git。
4. **pull 不被 push、不另架公開 endpoint。** 桌機按自己的時鐘**輪詢**(約 10 分鐘)各通道 inbox 撈新 @mention,不需要公開 IP/憑證/serverless/webhook。通道是**可插拔 adapter**(`orchestrator/inbox.py`):Slack 先做,Teams 走 Microsoft Graph(delta query)後做。
5. **skill 是 thin shim,動態內容住 GitHub。** skill 只說「去 repo 讀哪幾個檔、產什麼格式」,rubric/原則執行時 fetch。改 rubric = 開 PR,merge 後下次跑就吃到新版,不重發 skill。
6. **對話 ≠ 產物。** 一則 mention **不等於**一個 case;case 綁在 thread 上、跨多則訊息累積,活在 `.runtime/cases/<id>/`(笨持久層,**不是** Python 狀態機)。只有結晶成「值得請人裁決的推薦」才跨牆進 `reviews/`。使用者反反覆覆、補件、改主意,只是讓 case 在對話裡待久一點——這正常,不威脅任何承諾。

## 兩道閘(系統的靈魂)

- **自主閘**:可逆×影響小 → 自動(讀文件、跑分析、寫 findings、對話追問缺料、貼草稿到對話)。不可逆/影響大 → 停下問人(**go/no-go 裁決、否決專案 → 走 PR + CODEOWNERS**)。判準在 `principles/autonomy-gate.md`。
- **Feedback 迴圈(中央化)**:委員透過 **Slack/Teams 1:1 或 thread** 給回饋 → 落 **中央 feedback store**(`.runtime/feedback/`,不進 git)→ 排程的 **feedback-synthesis** agent 定期彙整成 **rubric/skill 修改提案(PR)** → **由人覆核 merge** 才生效(走 skills/rubrics 的 CODEOWNERS)。**全部執行集中在中央主機,不走個人訂閱。**(分流:案子進行中針對當前推薦草稿的反駁 → 回 case context 觸發改版重審;一般 rubric 回饋 → 走這條慢迴圈。)

## 流程(輪詢 → 叫大腦讀 brief → Python 兌現)

```
前門(純機械,無 model;pull 不被 push)
  排程每約 10 分鐘:inbox.poll_inbox(adapter)
   → 撈各通道「自游標以來、@我」的訊息,按 thread 分組
   → 同 thread 併入同一 case(case_store.find_by_thread);新 thread 才建 case
   → append_inbox(對話累積)+ 丟一個 collapse 信號(同 case 多訊息合一)

推進(worker.py 撈 case-activity 信號)
   → drain_inbox 把新訊息吸進 case state
   → 叫起【一個】claude 讀 agents/case-agent.md brief + 整串對話 context
        → 回一份【行動計畫 JSON】:reply_text? run_review? crystallize_pr? new_status_note
   → ★Python 逐項兌現 + 驗收(承諾層):
        run_review   → 佈置工作區(改版先清舊產出)→ 跑審查 → ★產出完整性驗收(缺就不往下)
        reply_text   → post_thread 回貼對話(reporter seam;無 token 時降級 print)
        crystallize_pr → ★Python 確認產出齊全才 open_review_pr(改版=同分支新 commit)+ @委員
        new_status_note → 持久化 Claude 對這個 case 的滾動理解
   → 人 merge PR = 正式裁決(CODEOWNERS)
```

> ※ 本切片只跑 security 一顆 lens、inline 跑。擴到四維時把 fan-out 加回(設計目標:intake → 平行 4 lens subagent → synthesize)。

## 目錄速查

| 路徑 | 是什麼 | 進 git? | 改它要 |
|---|---|---|---|
| `principles/` `contracts/` | 政策、判準、裁決政策、輸出契約 | ✅ | PR + 人 merge |
| `rubrics/` | 各維度審查 rubric(被 skill fetch) | ✅ | PR + 人 merge |
| `agents/` | 各 agent 的 system prompt | ✅ | PR |
| `skills/` | thin shim(去哪讀、產什麼) | ✅ | PR |
| `reviews/<case-id>/` | **結晶後**的審查紀錄:findings/verdict/狀態 | ✅(紀錄) | findings 自動;**verdict 要人 merge** |
| `agents/case-agent.md` | 對話大腦的 brief(路徑判斷依據) | ✅ | PR |
| `orchestrator/` | 桌機 daemon(Python 承諾層) | ✅ | 一般 PR |
| `scripts/` `site/` `.github/` | dashboard 等不需 model 的 ops | ✅ | 一般 PR |
| `.runtime/cases/<id>/` | **對話/草稿/累積 context**(笨持久層,非狀態機) | ❌ gitignore | — |
| `.runtime/` | secrets / queue / cases / 下載副本 / log | ❌ gitignore | — |

## 重要產出契約

- 每顆 lens 輸出符合 `contracts/finding.schema.json` 的 `findings.json`。
- 怎麼把 findings 權衡成 go/no-go/帶條件、哪些必須人簽,在 `contracts/verdict-policy.md`。

## 現在進度

見 `IMPLEMENTATION_PLAN.md`。簡言之:Step 1(Slack 監聽神經)優先,可獨立驗收;Step 2(審查 + GitHub)其次。
