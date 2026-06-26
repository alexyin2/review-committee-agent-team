# Case <case-id>

> 每個審查 case 一夾,複製此 `_template`。這份 README = 本案狀態板(人看的入口)。

- **狀態**:intake | reviewing | verdict-draft | awaiting-signoff | decided
- **來源**:<Slack permalink> /(OneDrive 連結,若有)
- **提交者**:<@user>
- **建立時間**:<ts>

## 連結

- Slack thread:
- 審查 PR(go/no-go 簽核在此):
- @指定委員:

## 結構

- `submission/manifest.json` — 只放指標(來源連結 / 檔名 / sha256),**不放實體 bytes**
- `intake/` — 正規化包 + 完整性報告
- `findings/` — 各 lens 結構化 findings
- `verdict/` — 合成推薦(此層變更觸發 go/no-go PR,CODEOWNERS 強制人 merge)
