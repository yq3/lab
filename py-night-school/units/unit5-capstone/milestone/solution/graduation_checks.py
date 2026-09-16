# 毕业断言工装（参考答案——三态验证的毕业态把本文件覆盖到里程碑根的 graduation_checks.py）
"""三条主链路的关键取证断言——参考答案版（与学员版仅三个函数体不同，docstring 同款）。

- assert_stream_tail：events_for 读整条流 → type 末尾对齐 expected_tail + seq 全程连续；
- assert_hash_rotated：两张审批单的 content_hash 各自非空、且互不相等（A6）；
- assert_zero_payments：日历聚合上 payment.executed 过滤读出空列表（账本零记录）。
"""

from __future__ import annotations

import eventstore


def assert_stream_tail(store: eventstore.EventStore, run_key: str, expected_tail: tuple[str, ...]) -> None:
    """链路①取证：断言 run 聚合的事件流以 expected_tail 的顺序收尾，且整条流 seq 连续无空洞。"""
    rows = store.events_for(run_key)
    types = [row["type"] for row in rows]
    assert types[-len(expected_tail) :] == list(expected_tail), (
        f"事件流收尾 {types[-len(expected_tail) :]} != {list(expected_tail)}（顺序即审计叙事）"
    )
    seqs = [row["seq"] for row in rows]
    assert seqs == list(range(len(rows))), f"seq 不连续: {seqs}（append-only 应为 0..{len(rows) - 1}）"


def assert_hash_rotated(first: dict, second: dict) -> None:
    """链路②取证：断言拒绝回环重生成后的审批单「批的是新一版内容」（A6 内容版本绑定）。"""
    assert first["content_hash"], "first 缺指纹（空指纹 = 没锁版本的「批了」）"
    assert second["content_hash"], "second 缺指纹（空指纹 = 没锁版本的「批了」）"
    assert second["content_hash"] != first["content_hash"], (
        f"content_hash 没有轮换: {first['content_hash']} == {second['content_hash']}（A6：批的还是旧版）"
    )


def assert_zero_payments(store: eventstore.EventStore, aggregate_id: str) -> None:
    """链路③取证：断言当日账本聚合上 payment.executed 事件一条都没有（「没付」的铁证）。"""
    paid = store.events_for(aggregate_id, type="payment.executed")
    assert paid == [], f"当日账本不应有已付记录，实得 {len(paid)} 条: {[row['payload'] for row in paid]}"
