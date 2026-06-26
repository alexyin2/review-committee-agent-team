"""共用 helper:執行時從 GitHub 取動態內容(rubric / 原則 / verdict-policy)。

thin-shim 的心臟(design §7.2):skill 只說「去哪讀」,內容住 GitHub、執行時 fetch。
改 rubric = 開 PR,merge 後下次跑就吃到新版,不用重發 skill。

讀 main(已治理);要更穩可 pin 到 release tag / commit。
私有 repo 用唯讀 fine-grained PAT 或 GitHub App token;公開可直接 raw。
政策檔很小可每次讀;知識庫大應「需要時才查」。
"""

# import urllib.request

DEFAULT_REF = "main"


def fetch(path: str, ref: str = DEFAULT_REF, token: str | None = None) -> str:
    """從 repo 取單一檔內容(raw)。回傳文字。"""
    raise NotImplementedError("實作:GET raw.githubusercontent / contents API,帶 token")
