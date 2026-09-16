# 毕业断言工装（单变量编辑约束：只改本文件 TODO 标注的函数体**与所需的顶部 import**，其余不要动）
"""三条主链路的关键取证断言——毕业判据里「你亲手钉」的那三颗钉子（本里程碑唯一编码 TODO）。

tests/test_graduation.py 把三条主链路完整跑通并给出大部分断言（given，不要改）；
每条链路**最关键的一处取证**留在这里由你补全——毕业测试全绿意味着毕业判据的
证据是你亲手从事件表里取的，不是抄来的：

- assert_stream_tail（链路①核心，链路③复用）：run 聚合事件流的「收尾顺序 + seq 连续」
  断言——A7「批准只是授权、门查过才付款」的证据在事件表里，不在终态字段里；
- assert_hash_rotated（链路②核心）：拒绝回环后「批的是新一版内容」的指纹断言（A6）；
- assert_zero_payments（链路③核心）：fail-closed 拒绝后「一分都没付」的账本断言
  ——「没付」的证据是当日账本零记录，不是 paid_cents 为 None。

取证入口只有两个（都在本 PoC 的 L5.3 层）：
- store.events_for(聚合键, type=...)——读一个聚合的事件流（list[dict]：seq/type/payload/created_at）；
- 事件流的 append-only 铁律——seq 从 0 起、每聚合单调 +1、无空洞（eventstore.append 的语义）。
"""

from __future__ import annotations

import eventstore


def assert_stream_tail(store: eventstore.EventStore, run_key: str, expected_tail: tuple[str, ...]) -> None:
    """链路①取证：断言 run 聚合的事件流以 expected_tail 的顺序收尾，且整条流 seq 连续无空洞。

    判定口径（tests 的毕业判据清单同款措辞）：
    - **顺序**：事件 type 列表的末 len(expected_tail) 个 == list(expected_tail)——
      链路① 传 ("submitted", "gate.checked", "payment.executed")：submitted（批准只是
      授权）→ gate.checked（门裁决）→ payment.executed（实付），A7 的执行史叙事；
      链路③ 复用本工装，传 ("gate.checked", "gate.denied", "advice.drafted")：
      批了、没付、转人审；
    - **seq 连续**：整条流的 seq 列表 == list(range(条数))——append-only 从 0 起无空洞，
      有空洞 = 有人动过账。
    """
    # TODO(g1): 先取证——rows = store.???（读 run 聚合整条流，不按 type 过滤）
    # TODO(g1): 断言顺序——types 末尾与 expected_tail 对齐（注意 expected_tail 是 tuple，断言前要不要变 list？）
    # TODO(g1): 断言 seq 连续——从 0 数到 len(rows)-1，一条不多一条不少
    raise NotImplementedError("TODO(g1): assert_stream_tail")


def assert_hash_rotated(first: dict, second: dict) -> None:
    """链路②取证：断言拒绝回环重生成后的审批单「批的是新一版内容」（A6 内容版本绑定）。

    输入是两张审批单（approvals.Ticket 的 dict 形态，interrupt payload 登记而来），
    各带 content_hash 键。判定口径：
    - 两张单的 content_hash 都非空（空指纹 = 没锁版本的「批了」）；
    - second 的 content_hash != first 的 content_hash——同一单据重生成出不同建议单，
      指纹必须跟着变（graph.content_hash 的契约）；不变 = 批的还是旧版，回环白跑。
    （ticket_id 不同这件事 given 断言已管，这里不重复。）
    """
    # TODO(g2): 两张单的 content_hash 各自非空
    # TODO(g2): second 的指纹 != first 的指纹——A6：内容一变指纹变
    raise NotImplementedError("TODO(g2): assert_hash_rotated")


def assert_zero_payments(store: eventstore.EventStore, aggregate_id: str) -> None:
    """链路③取证：断言当日账本聚合上 payment.executed 事件一条都没有（「没付」的铁证）。

    aggregate_id 是日历聚合键（graph.PaymentLedger.day_aggregate(today)，形如
    "ledger:2026-09-16"）。判定口径：在该聚合上按 type="payment.executed" 过滤读事件，
    结果必须为空列表——账本是「世界状态」的投影，零条 = 这一天这笔钱确实没出账。
    终态字段的 paid_cents=None 只是图的记忆，账本零记录才是审计能信的证据。
    """
    # TODO(g3): 在 aggregate_id 聚合上只取 payment.executed 一类事件
    # TODO(g3): 断言取到的列表为空
    raise NotImplementedError("TODO(g3): assert_zero_payments")
