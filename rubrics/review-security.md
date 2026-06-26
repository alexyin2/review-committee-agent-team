# Security Review Rubric

> 資安維度的審查 criteria。**動態內容**——被 `skills/review-security` 在執行時 fetch。
> 改它 = 開 PR,merge 後下次審查就吃到新版,不用重發 skill(CLAUDE.md 鐵律 #5)。
> 這是骨架草案,Step 2 由領域專家補實。

## 要問的問題(每條對應一個 rubric_ref)

- `sec-authn`:身分驗證機制是什麼?有無 MFA?
- `sec-authz`:授權模型?最小權限?
- `sec-data`:敏感資料在傳輸/靜態下是否加密?
- `sec-secret`:secrets 怎麼管?有無硬編碼?
- `sec-deps`:相依套件有無已知漏洞掃描?
- `sec-logging`:有無安全事件日誌與告警?
- `sec-pentest`:上線前有無滲透測試/威脅建模?

## 嚴重度判準(對應 finding.schema 的 severity)

- **blocker**:無加密的敏感資料外洩路徑、硬編碼正式環境 secret、無任何 authn。
- **high**:缺 MFA、無漏洞掃描、過度授權。
- **medium/low**:日誌不足、文件缺漏等。

## 輸出

依 `contracts/finding.schema.json`,產 `findings.json`,`lens: "security"`。每條 finding 標 `rubric_ref` 與 `evidence`(提交文件依據;無證據要明說)。
