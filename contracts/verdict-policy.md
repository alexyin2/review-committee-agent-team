# Verdict Policy(裁決政策)

> 怎麼把各維度 findings 權衡成 **go / no-go / 帶條件 go**,以及**哪些裁決必須人簽**。
> 這是審查領域的「自主閘」判準。受治理、走 PR、要留痕。

## 核心原則(不可違反)

**Agent 給推薦,人做裁決。** 這份政策產出的是**推薦的** verdict,寫進 `reviews/<case>/verdict/`。
真正生效 = **人 merge 那個 PR**(CODEOWNERS 強制)。agent 永遠不自己 merge。

## 推薦怎麼算(草案,Step 2 定案)

- 任一 lens 有 `blocker` → 推薦 **no-go**,列出所有 blocker。
- 無 blocker、但有 `high` → 推薦 **帶條件 go**,條件 = 把 high 降到可接受。
- 只有 medium/low/info → 推薦 **go**,附改善建議。

## 哪些必須人簽(必走 PR + 指定 reviewer)

- 任何 go / no-go / 帶條件 go 的**正式裁決**(全部)。
- 否決一個專案。
- 任何專案團隊會當成「官方決定」的東西。

## 誰簽(reviewer 指派)

- 由 `.github/CODEOWNERS` 對 `reviews/**/verdict/` 設定的人。
- Slack 回覆時 @ 對應委員(初期可用 config 的 default_reviewer)。
