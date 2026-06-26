# Review Committee Agent Team

專案上線審查的數位同事團隊。Slack `@claude` 附上專案文件 → 桌機跑多維度審查(資安/隱私/法遵/維運)→ 推薦寫成 GitHub PR → 回 Slack @委員簽核。

**Agent 給推薦,人做裁決。**

## 從哪開始讀

- `CLAUDE.md` — 在 repo 裡幹活的定向 + 不可違反的鐵律。
- `IMPLEMENTATION_PLAN.md` — 分階段計畫(Step 1 = Slack 監聽神經)。
- `co-worker-agent-team-design.md`(上層)— 完整架構設計。

## 架構速覽

```
Slack @claude+檔  ──Socket Mode──▶  桌機(Max)
                                    ├─ slack_listener.py  下載→ack→入列(純機械)
                                    └─ worker.py          審查→commit→開PR→回Slack(外圈,確定性)
                                          └─ 一個 claude session(內圈,subagent fan-out)
                                                intake → 4 lens → synthesize → verdict
狀態/紀錄 ──▶ GitHub(findings/verdict 走 PR,CODEOWNERS 強制人 merge)
```

## 設定

複製 `orchestrator/config.example.toml` → `config.toml`;token 放 `.runtime/secrets.toml`(已 gitignore)。
