"""桌機是單點故障。這檔補:WebSocket 斷線重連、keep-awake、session 重新登入。

設計文件 §5.1 已點出:桌機會睡眠、session 會過期、會當機、無受管自動重啟。
Socket Mode 的 WebSocket URL 也會定期刷新、要處理重連。

TODO:
  - keep-awake(macOS: caffeinate / Windows: SetThreadExecutionState)
  - listener / worker 行程監看 + 自動重啟
  - Claude Code session 過期偵測 + 重新登入提示/處理
"""

raise NotImplementedError("拓展階段實作 — 見檔頭 TODO")
