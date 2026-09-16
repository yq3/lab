"""付款通道连接器：抽象基类 + MockBroker——对版
HKUDS/Vibe-Trading@f84b2977#agent/src/trading/connectors/<broker>/sdk.py。

产品的券商连接器是**模块级函数集**（place_order / get_positions / get_account_snapshot /
get_quote），靠鸭子类型被门调用（「能被调就行」，不是 Protocol、更不是继承基类——14 个
连接器各自独立成模块）。教学版反其道用 ABC：把「门依赖哪些操作」的契约写在一个类里
讲清楚（对版产品 mock 样板 live/advisory/mock.py 的 ABC + Mock 组合），等你把契约背下来，
回到产品看到「模块里有这四个函数」自然认得出来——那就是没有基类的同一份契约。

四个操作映射（交易域 → 付款域）：
  get_positions / get_account_snapshot → today_payments()：门要的「当日已付」快照（读）
  get_quote                            → （裁掉：付款金额是意图自带的，不用行情定价）
  place_order(client_order_id=...)      → pay(intent, ref_id)：幂等键对版 client_order_id
  get_order_by_client_order_id          → get_payment_by_ref(ref_id)：崩溃恢复对账取证（读）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from enforcement import PaymentIntent


class BrokerUnavailable(RuntimeError):
    """付款通道不可用 / 提交结果未知（对版产品连接器抛出的异常族）。"""


class Broker(ABC):
    """付款通道契约：门与对账只依赖这四个操作（教学版显式 ABC；产品是鸭子类型）。

    读操作（today_payments / get_payment_by_ref）失败抛 :class:`BrokerUnavailable`；
    写操作（pay）失败也抛——但**到达与否由通道侧决定**，见 MockBroker 的两种故障。
    """

    @abstractmethod
    def today_payments(self) -> list[dict[str, Any]]:
        """当日已付清单快照（每条含 payee/category/amount_cents/ref_id）。"""

    @abstractmethod
    def balance_cents(self) -> int:
        """付款账户余额（整数分）——物理天花板，门不做主依赖（对版资金 broker 侧执行）。"""

    @abstractmethod
    def pay(self, intent: PaymentIntent, ref_id: str) -> dict[str, Any]:
        """执行一笔付款，ref_id 是幂等键（对版 client_order_id）：同 ref 再来返回同一回执。"""

    @abstractmethod
    def get_payment_by_ref(self, ref_id: str) -> dict[str, Any] | None:
        """按 ref_id 精确取证；查无此单返回 None（对版 get_order_by_client_order_id）。"""


class MockBroker(Broker):
    """确定性内存 Mock（对版产品 MockAdvisory 的「可注入故障 + 调用取证」样式）。

    Args:
        failure: 故障注入模式——
            ``None``：全量成交（pay 记录 ref_id 并返回回执）；
            ``"unreachable"``：pay 抛 BrokerUnavailable 且**款项未到达**（无记录）；
            ``"arrived_unconfirmed"``：款项先入账再抛 BrokerUnavailable——模拟
            「付款已到达通道、进程在拿到确认前崩溃」（对账练习的关键分支）。
        opening_paid: 预置的当日已付清单（构造世界状态用）。
        balance_cents: 账户余额。

    ``pay_calls`` 记录每次 pay 收到的 ref_id——「对账不重发」验收靠数它。
    """

    def __init__(
        self,
        failure: str | None = None,
        opening_paid: list[dict[str, Any]] | None = None,
        balance_cents: int = 5_000_000,
    ) -> None:
        if failure not in (None, "unreachable", "arrived_unconfirmed"):
            raise ValueError(f"unknown failure mode: {failure}")
        self.pay_calls: list[str] = []
        self._failure = failure
        self._balance_cents = balance_cents
        self._records: dict[str, dict[str, Any]] = {}
        for entry in opening_paid or []:
            self._records[str(entry["ref_id"])] = dict(entry)

    def today_payments(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records.values()]

    def balance_cents(self) -> int:
        return self._balance_cents

    def pay(self, intent: PaymentIntent, ref_id: str) -> dict[str, Any]:
        self.pay_calls.append(ref_id)
        existing = self._records.get(ref_id)
        if existing is not None:
            return dict(existing)  # 幂等键命中：同 ref 绝不重复入账（对版 client_order_id）
        if self._failure == "unreachable":
            raise BrokerUnavailable(f"broker unreachable before payment reached the channel (ref={ref_id})")
        record = {
            "ref_id": ref_id,
            "payee": intent.payee,
            "category": intent.category,
            "amount_cents": intent.amount_cents,
            "status": "paid",
        }
        self._records[ref_id] = record  # 先入账（款项已到达）……
        if self._failure == "arrived_unconfirmed":
            raise BrokerUnavailable(  # ……再抛：确认丢失，但证据已留在通道里
                f"payment arrived but confirmation was lost (simulated crash, ref={ref_id})"
            )
        return dict(record)

    def get_payment_by_ref(self, ref_id: str) -> dict[str, Any] | None:
        record = self._records.get(ref_id)
        return dict(record) if record is not None else None
