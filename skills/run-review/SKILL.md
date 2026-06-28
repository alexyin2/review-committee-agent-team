---
name: run-review
description: 跑一個專案上線審查 case 的內圈 pipeline——intake → 平行 lens fan-out → synthesize verdict。由 worker.py 在佈置好工作區後叫起。
---

# run-review(內圈 thin shim)

這是「內圈」:一個 claude session 讀這份 shim,用 **subagent fan-out** 跑審查。
有副作用的事(commit / 開 PR / 貼 Slack)**不在這裡**——那是外圈 worker.py 的事(CLAUDE.md 鐵律 #2)。

## 輸入(worker.py 已佈置好)

工作目錄 `.runtime/workspace/<case-id>/`:
- `files/`        ← 提交文件副本
- `intake/`       ← (待產)正規化包 + 完整性報告
- `lenses/<dim>/` ← 每維度一夾,內含該維度 rubric 切片
- `findings/`     ← (待產)各 lens 輸出
- `verdict/`      ← (待產)合成推薦

## 步驟

1. **Intake**:讀 `files/`,檢查完整性(對照 `intake-completeness`)。缺漏 → 記下缺什麼、回報,**留在對話收集階段**(由對話大腦 `agents/case-agent.md` 在 thread 裡追問補齊,不是冷冰冰退件)。完整 → 正規化成標準包,切出各維度 context slice 到 `lenses/<dim>/`。

2. **Fan-out(平行)**:對每個維度 spawn 一顆 lens subagent。每顆**只**載自己的 rubric(從 GitHub fetch 最新版,見 `_lib/github_fetch.py`)+ 該維度切片,**互不污染**。產出 `findings/<dim>.json`,符合 `contracts/finding.schema.json`。

3. **Synthesize**:讀所有 `findings/*.json`,套 `contracts/verdict-policy.md`,產 `verdict/recommendation.md`(go/no-go/帶條件 + 理由 + 哪些必須人簽)。

## 產出契約(外圈會驗收)

- `findings/<dim>.json` ×N(每維度一個,缺一不可)
- `verdict/recommendation.md`

worker.py 會在開 PR 前確定性檢查這些是否齊全;缺就不開 PR、回報缺哪顆。
