"""git / gh 包裝。審查紀錄進 git、go/no-go 走 PR(CODEOWNERS 強制人 merge)。

只放會受益於版本控制的東西:findings、verdict、case README。
原始提交 bytes 在 .runtime/,永不進 git(CLAUDE.md 鐵律 #3)。
"""

# import subprocess


def open_review_pr(case: dict) -> str:
    """commit reviews/<case_id>/{findings,verdict,README} → 開分支 → gh pr create。
    PR body = 推理摘要;diff = 改動;reviewer 由 CODEOWNERS / verdict-policy 決定。
    回傳 PR URL。
    """
    raise NotImplementedError
