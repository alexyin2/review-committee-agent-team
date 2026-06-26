---
name: intake-completeness
description: 提交完整性檢查——必備文件清單 + 表單欄位驗證 + 「缺什麼」輸出格式。
---

# intake-completeness(thin shim)

1. fetch 必備文件清單與表單欄位規則(待補:`contracts/` 或 `rubrics/intake-*`)。
2. 對照提交 `files/`,逐項核對。
3. 缺漏 → 產 `intake/missing.md`(缺哪些、格式為何不合),供 worker 退回請補。
4. 完整 → 正規化成標準包,切各維度 context slice 到 `lenses/<dim>/`。
