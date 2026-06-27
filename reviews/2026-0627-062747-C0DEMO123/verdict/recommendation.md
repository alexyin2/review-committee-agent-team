# 上線審查推薦 — case 2026-0627-062747-C0DEMO123

> **這是推薦,不是裁決。** 依 `contracts/verdict-policy.md` 核心原則:Agent 給推薦,人做裁決。
> 真正生效 = 人 merge 對應 PR(CODEOWNERS 強制)。本 agent 不自行 merge、不自行放行。
> 本次審查僅涵蓋 **security 一個維度**;privacy / legal / ops 維度尚未納入,最終裁決應待其餘維度齊備。

## 推薦:**NO-GO(不建議上線)**

依 verdict-policy:「任一 lens 有 `blocker` → 推薦 no-go,列出所有 blocker」。
security lens 共發現 **3 個 blocker**,單一即足以擋上線。

## 理由 — Blocker 清單(必須全數解決才重審)

| id | 嚴重度 | 問題 | rubric_ref |
|---|---|---|---|
| sec-001 | blocker | Admin endpoints 完全沒有身分驗證(無任何 authn) | sec-authn |
| sec-002 | blocker | 正式環境 DB 密碼硬編碼於 config.py(`DB_PASS="prod-secret-456"`) | sec-secret |
| sec-003 | blocker | 明文儲存使用者密碼、資料靜態未加密 | sec-data |

這三項各自對應 rubric「嚴重度判準」中明列為 blocker 的情形:無任何 authn、硬編碼正式 secret、無加密的敏感資料外洩路徑。

### 附帶問題(降級後仍須處理)

- **sec-004(high)**:無相依套件漏洞掃描 — 即使 blocker 解決,仍須降到可接受才放行。
- **sec-005(medium)**:無安全事件日誌與告警。
- **sec-006(medium,缺證據)**:授權模型未說明。
- **sec-007(medium,缺證據)**:上線前無滲透測試/威脅建模。

## 重審前置條件(blocker 解除門檻)

1. 所有 admin(及對外)endpoints 強制身分驗證,管理操作加 MFA(解 sec-001)。
2. 密碼移出原始碼改用 secret manager,並**輪換已外洩的 `prod-secret-456`**(解 sec-002)。
3. 密碼改用加鹽慢雜湊儲存,含 PII 資料庫啟用靜態加密(解 sec-003)。
4. 補上 sec-004 漏洞掃描;補齊 sec-006 / sec-007 缺證據項目的文件與驗證。

## 哪些必須人簽(依 verdict-policy)

- 本 **no-go 正式裁決** 必走 PR + 指定 reviewer,由人 merge 才生效。
- 「否決專案上線」屬重大決定,必須人簽,agent 不得自行定案。
- 簽核者依 `.github/CODEOWNERS` 對 `reviews/**/verdict/` 之設定;Slack 通知時 @ 對應委員(初期可用 config 的 default_reviewer)。
