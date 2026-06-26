---
name: review-security
description: 資安維度的 review lens。fetch 最新 review-security rubric,對提交切片產結構化 findings。
---

# review-security(thin shim 範例)

1. fetch `rubrics/review-security.md` 最新版(`_lib/github_fetch.py`,讀 main)。
2. 載入 `agents/review-lens.md` 骨架 + 上面的資安 rubric。
3. 只看自己維度的提交切片 `lenses/security/`。
4. 對照 rubric 逐條,產 `findings/security.json`,符合 `contracts/finding.schema.json`。

> 其他維度(privacy / legal / ops)複製此 shim,只換 rubric 路徑與 lens 名。
> rubric 改了不用動這個 skill——下次跑自動吃新版。
