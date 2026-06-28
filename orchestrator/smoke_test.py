"""離線冒煙測試:不需 Slack token / 不需 Azure / 不叫 model,驗證機械骨架健康。

涵蓋:
  1. config 路徑 + queue 收發(原有)。
  2. case_store 生命週期 + thread index + inbox drain。
  3. inbox 輪詢(fake adapter):同 thread 併一 case、信號 collapse、cursor 持久化。
  4. ★行動計畫交棒:餵假的 Claude 行動計畫(monkeypatch _decide)+ 假審查產出
     (monkeypatch invoke_review),驗 worker 的「承諾層」逐項兌現 + 完整性保險絲。
  5. reporter 樁:無 token 時 post_thread 走 print(不炸、無未接線的 [slack-TODO])。

跑法(repo 根目錄):
    python -m orchestrator.smoke_test
真正的 Slack/Teams 端到端要 token / Azure 認證 + 接 adapter 真 API。
git 分支重審冪等另以一次性自清理腳本驗證(不塞進可重複 smoke)。
"""

from __future__ import annotations

import json
import shutil
import subprocess

from . import case_store, inbox, queue, worker
from .config import config


def _clean() -> None:
    shutil.rmtree(config.cases_dir, ignore_errors=True)
    for d in (queue.INCOMING, queue.PROCESSING, queue.DONE):
        shutil.rmtree(d, ignore_errors=True)
    (config.runtime_dir / "inbox_cursor.json").unlink(missing_ok=True)


# --------------------------------------------------------------------------
def test_queue_roundtrip() -> None:
    case_id = "0000-0000-000000-CSMOKE"
    payload = {"case_id": case_id, "source": {"type": "local"}, "submitter": "USMOKE"}
    path = queue.enqueue(case_id, payload)
    assert path.exists(), "enqueue 沒寫出檔"
    claimed = queue.claim_next()
    assert claimed and claimed["case_id"] == case_id, "claim_next 撈不到"
    assert claimed["_queue_file"] == f"{case_id}.json", "claim_next 應回 _queue_file"
    queue.mark_done(claimed)
    assert (queue.DONE / f"{case_id}.json").exists(), "mark_done 沒 move 到 done"
    (queue.DONE / f"{case_id}.json").unlink(missing_ok=True)
    print("[smoke] 1) queue roundtrip ✅")


def test_case_store() -> None:
    cid = "SMOKE-CASE-STORE"
    cs = case_store
    cs.create(cid, channel="C1", thread_id="T1", submitter="U1")
    assert cs.create(cid, channel="C1", thread_id="T1", submitter="U1")["version"] == 0, "create 非 idempotent"
    assert cs.register_thread("C1", "T1", cid) == cid
    assert cs.register_thread("C1", "T1", "OTHER") == cid, "O_EXCL 第一個沒贏"
    cs.append_inbox(cid, {"ts": "1", "user": "U1", "text": "a", "links": ["L1"]})
    cs.append_inbox(cid, {"ts": "2", "user": "U1", "text": "b"})
    assert len(cs.drain_inbox(cid)) == 2
    st = cs.load(cid)
    assert len(st["context"]) == 2 and st["doc_links"] == ["L1"], st
    assert cs.drain_inbox(cid) == [], "drain 後 inbox 該空"
    cs.bump_version(cid)
    assert cs.load(cid)["version"] == 1
    print("[smoke] 2) case_store lifecycle + thread index + inbox drain ✅")


def test_inbox_poll() -> None:
    class FakeAdapter:
        name = "fake"
        def fetch_new_mentions(self, cursor):
            M = inbox.Mention
            return [
                M(channel="C1", thread_id="TA", user="U1", text="開案", ts="1", links=[]),
                M(channel="C1", thread_id="TA", user="U1", text="補圖", ts="2", links=["LX"]),
                M(channel="C1", thread_id="TB", user="U2", text="另案", ts="3", links=[]),
            ], {"last_ts": "3"}

    summary = inbox.poll_inbox(FakeAdapter())
    assert summary["mentions"] == 3 and summary["cases_touched"] == 2, summary
    incoming = sorted(p.name for p in queue.INCOMING.glob("*.json"))
    assert len(incoming) == 2 and all(n.startswith("case-activity-") for n in incoming), incoming
    cid_a = case_store.find_by_thread("C1", "TA")
    assert len(case_store.drain_inbox(cid_a)) == 2, "TA 兩則該併一 case"
    cur = json.loads((config.runtime_dir / "inbox_cursor.json").read_text())
    assert cur["fake"] == {"last_ts": "3"}, cur
    print("[smoke] 3) inbox poll:同 thread 併一 case + 信號 collapse + cursor ✅")


def test_action_plan_handoff(monkeypatch_like) -> None:
    """★餵假行動計畫 + 假審查產出,驗承諾層兌現 + 完整性保險絲。不叫 model、不動 git。"""
    cid = "SMOKE-HANDOFF"
    case_store.create(cid, channel="C9", thread_id="T9", submitter="U9")
    case_store.append_inbox(cid, {"ts": "1", "user": "U9", "text": "幫我審這個要上 UT 的東西", "links": []})

    replies: list[str] = []
    monkeypatch_like(worker, "_reply", lambda case, text: replies.append(text))

    # 假 _decide:第一輪「追問缺料」(不審不開PR)
    monkeypatch_like(worker, "_decide", lambda state: {
        "reply_text": "收到!請提供架構圖與資料流說明,我先看一下。",
        "run_review": False, "crystallize_pr": False,
        "new_status_note": "gathering:已請補架構圖", "reasoning": "料還不夠",
    })
    worker._handle_case_activity({"case_id": cid})
    st = case_store.load(cid)
    assert st["status_note"].startswith("gathering"), st
    assert any("架構圖" in r for r in replies), replies

    # 假 invoke_review:模擬 claude 寫出合格 findings + verdict
    def fake_invoke(ws, case_id):
        (ws / "findings" / "security.json").write_text(json.dumps({
            "lens": "security",
            "findings": [{"id": "sec-001", "severity": "high", "title": "缺 TLS",
                          "rationale": "rubric sec-transit", "recommendation": "全程 TLS"}],
        }, ensure_ascii=False), encoding="utf-8")
        (ws / "verdict" / "recommendation.md").write_text("# 帶條件 go\n補 TLS 後可上。", encoding="utf-8")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch_like(worker, "invoke_review", fake_invoke)

    # doc_links 指到一個臨時檔(驗 _fetch_docs 拓副本)
    tmp_doc = config.runtime_dir / "_smoke_doc.md"
    tmp_doc.write_text("# 架構圖\nUT 部署說明", encoding="utf-8")
    case_store.append_doc_link(cid, str(tmp_doc))

    # 第二輪:料齊 → 跑審查(假)+ 回貼草稿
    monkeypatch_like(worker, "_decide", lambda state: {
        "reply_text": "已完成初步審查,推薦帶條件 go(補 TLS)。",
        "run_review": True, "crystallize_pr": False,
        "new_status_note": "verdict-draft v0", "reasoning": "料齊了",
    })
    worker._handle_case_activity({"case_id": cid})
    ws = config.workspace_dir(cid)
    ok, missing = worker.outputs_complete(ws)
    assert ok, f"審查產出應齊全:{missing}"
    assert (ws / "files" / "_smoke_doc.md").exists(), "fetch_docs 沒拓副本"

    # 第三輪:crystallize_pr 但模擬產出被清空 → 保險絲應擋住(不開 PR、回報缺)
    shutil.rmtree(ws / "findings", ignore_errors=True)
    (ws / "findings").mkdir(parents=True, exist_ok=True)
    pr_called = {"n": 0}
    monkeypatch_like(worker.git_ops, "open_review_pr", lambda case: pr_called.__setitem__("n", pr_called["n"] + 1) or "PR!")
    monkeypatch_like(worker, "_decide", lambda state: {
        "reply_text": "", "run_review": False, "crystallize_pr": True,
        "new_status_note": "嘗試結晶", "reasoning": "委員說 OK",
    })
    worker._handle_case_activity({"case_id": cid})
    assert pr_called["n"] == 0, "★完整性保險絲失效:產出不全竟開了 PR"
    assert any("未完整" in r or "缺" in r for r in replies), "應回報缺產出"

    tmp_doc.unlink(missing_ok=True)
    shutil.rmtree(ws, ignore_errors=True)
    print("[smoke] 4) 行動計畫交棒:追問→審查→★保險絲擋住不全產出 ✅")


def test_reporter_stub() -> None:
    """無 token 時 post_thread 走 print 樁、不炸、回 None。"""
    from . import slack_client
    assert not config.slack_bot_token, "smoke 應在無 token 環境跑"
    ret = slack_client.post_thread("C1", "T1", "stub 測試")
    assert ret is None, "無 token 應回 None"
    print("[smoke] 5) reporter 樁:無 token → print 不炸 ✅")


# --------------------------------------------------------------------------
def _make_monkeypatch():
    """極簡 monkeypatch(免 pytest 相依):記錄並還原 setattr。"""
    saved: list[tuple] = []
    def patch(obj, name, value):
        saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)
    def restore():
        for obj, name, old in reversed(saved):
            setattr(obj, name, old)
    return patch, restore


def main() -> None:
    print(f"[smoke] runtime dir = {config.runtime_dir}")
    _clean()
    patch, restore = _make_monkeypatch()
    try:
        test_queue_roundtrip()
        test_case_store()
        test_inbox_poll()
        test_action_plan_handoff(patch)
        test_reporter_stub()
    finally:
        restore()
        _clean()
    print("[smoke] PASS ✅  全部機械骨架健康(case_store / inbox poll / 行動計畫交棒 / reporter 樁)")


if __name__ == "__main__":
    main()
