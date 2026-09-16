"""付款授权合同（mandate）——对版 HKUDS/Vibe-Trading@f84b2977#agent/src/live/mandate/model.py。

域＝报销付款：付款是「高金额不可逆」动作，dimensions 官方映射——无论前面用什么拓扑，
终点必须是 proposal 无权 + 代码门裁决 + mandate 授权 + 哈希链问责。本模块就是那条链的
「授权」一环：用户显式授权后落盘的不可变合同，付款门只读它、绝不改它。

对版关系（交易域 → 付款域）：
  HardCaps（单笔名义/总敞口/杠杆/日次数）      → 单笔付款上限/当日累计/日次数（整数分）
  UniverseConstraint（资产类别/黑名单）        → PayUniverse（科目白名单/收款方黑名单）
  ConsentMeta（consent_token/expires_at 30 天）→ ConsentMeta（consent 指纹/默认 30 天过期）
  Mandate 四件套 frozen dataclass              → PayMandate 四件套 frozen dataclass

刻意不用 Pydantic（产品同款取舍，model.py 原话「零验证面」）：mandate 在门启动时读一次、
之后永不变化，frozen dataclass 给出最强的不可变保证，且**没有**校验/强制转换/宽松解析这层
「验证面」——给 agent 读的合同对象不留任何可利用的解析空间（B5 模式）。需要边界校验的
地方（LLM 输出）才用 Pydantic（L2.4 的分工），合同对象反其道而行。

授权不可达（产品的「命门不变量」）：本模块刻意**没有** save_mandate——授权写入是用户侧
受信路径（对版产品 commit_mandate：不是工具、不进注册表、只由带 consent_ack 的入口调用），
agent 侧只有 load_mandate 只读。被劫持/幻觉的模型无法自我授权。讲义区与练习区的测试都
点名断言这个不变量。

金额一律整数「分」（宪法业务约定）；时间一律 aware UTC datetime（讲义 §2.6 讲 naive 陷阱）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

#: 合同格式版本；gate 拒绝操作未知未来版本（fail-closed，对版 MANDATE_SCHEMA_VERSION）。
PAY_MANDATE_SCHEMA_VERSION = 1

#: 默认授权寿命 30 天——「live mandate 不许永生」（产品 ConsentMeta 原话）。
DEFAULT_MANDATE_LIFETIME_DAYS = 30


@dataclass(frozen=True)
class HardCaps:
    """Layer (a)：用户设定的定量上限（整数分）。

    对版产品 HardCaps（单笔名义/总敞口/杠杆/日交易数）；付款域裁掉杠杆与资金镜像——
    付款没有「敞口加杠杆」语义，余额物理上限由「付款账户只放这么多钱」承担。

    Attributes:
        max_single_payment_cents: 单笔付款上限。
        max_daily_total_cents: 当日累计付款上限（含当日已付）。
        max_payments_per_day: 当日付款笔数上限。
    """

    max_single_payment_cents: int
    max_daily_total_cents: int
    max_payments_per_day: int


@dataclass(frozen=True)
class PayUniverse:
    """Layer (b)：付款的选择域（结构过滤，不是收款方白名单）。

    对版产品 UniverseConstraint（「不是 ticker 白名单——那会杀死 agent 的发现能力」）：
    付款域同理——用户限定**科目**（报销的类别），收款方在结构过滤内自由出现，
    只有明确作恶者进黑名单。

    Attributes:
        allowed_categories: 允许的科目白名单（小写归一）。**空 = 全拒**（fail-closed，
            对版产品 allowed_instruments 空 == deny all）。
        excluded_vendors: 收款方硬黑名单（小写归一），优先级高于其他一切规则。
    """

    allowed_categories: tuple[str, ...]
    excluded_vendors: tuple[str, ...]


@dataclass(frozen=True)
class ConsentMeta:
    """授权出处：证明是用户（而不是 agent）签发了这份合同。

    Attributes:
        consent_token_sha256: 绑定同意 UX 产出的 consent artifact 的指纹——每笔付款
            可回溯到授权它的人工动作（问责链起点）。
        created_at: 用户提交合同的时刻（aware UTC）。
        expires_at: 合同失效时刻（aware UTC）。None 时默认 created_at + 30 天——
            live mandate 不许永生（讲义 §2.6 的 aware-UTC 纪律在这里落地）。
    """

    consent_token_sha256: str
    created_at: datetime
    expires_at: datetime | None = None

    @property
    def effective_expiry(self) -> datetime:
        """生效的过期时刻（expires_at 已由 __post_init__ 填好；给类型检查器的窄化出口）。"""
        expires = self.expires_at
        assert expires is not None
        return expires

    def __post_init__(self) -> None:
        # frozen dataclass 的「紧凑构造器」：record 有 compact constructor 归一化字段，
        # frozen dataclass 用 __post_init__ + object.__setattr__ 达到同款效果（讲义 §2.4）。
        if self.expires_at is None:
            object.__setattr__(self, "expires_at", self.created_at + timedelta(days=DEFAULT_MANDATE_LIFETIME_DAYS))


@dataclass(frozen=True)
class PayMandate:
    """一个付款通道的不可变授权合同（对版产品 Mandate 四件套）。

    Attributes:
        schema_version: 写入时的 PAY_MANDATE_SCHEMA_VERSION；门拒绝未知未来版本。
        hard_caps: Layer (a) 定量上限。
        universe: Layer (b) 选择域。
        consent: 出处/有效期元数据。
    """

    schema_version: int
    hard_caps: HardCaps
    universe: PayUniverse
    consent: ConsentMeta


def _parse_utc(value: Any) -> datetime:
    """ISO-8601 字符串 → aware UTC datetime；无时区信息按 UTC 补齐（naive 见 §2.6）。

    任何解析失败抛 ValueError，由 load_mandate 统一转成 None（fail-closed）。
    """
    if not isinstance(value, str):
        raise ValueError(f"timestamp must be a string, got {type(value).__name__}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def load_mandate(path: Path) -> PayMandate | None:
    """从用户侧受信路径只读加载合同；任何读不到/解析不了/字段缺失 → None。

    返回 None 的语义是 fail-closed：调用方（付款门）见到 None 就 DENY，绝不放行。
    文件缺失、JSON 损坏、schema_version 不认识，一视同仁——对版产品 gate 的
    「no valid mandate on file」分支。

    注意本模块刻意没有 save_mandate：这是「授权不可达」不变量的一半
    （另一半是 commit 路径在 agent 面之外，见 demo.py 的用户侧写入示范）。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("mandate root must be a JSON object")
        caps = data["hard_caps"]
        universe = data["universe"]
        consent = data["consent"]
        mandate = PayMandate(
            schema_version=int(data["schema_version"]),
            hard_caps=HardCaps(
                max_single_payment_cents=int(caps["max_single_payment_cents"]),
                max_daily_total_cents=int(caps["max_daily_total_cents"]),
                max_payments_per_day=int(caps["max_payments_per_day"]),
            ),
            universe=PayUniverse(
                allowed_categories=tuple(str(c).strip().lower() for c in universe["allowed_categories"]),
                excluded_vendors=tuple(str(v).strip().lower() for v in universe["excluded_vendors"]),
            ),
            consent=ConsentMeta(
                consent_token_sha256=str(consent["consent_token_sha256"]),
                created_at=_parse_utc(consent["created_at"]),
                expires_at=_parse_utc(consent["expires_at"]) if consent.get("expires_at") is not None else None,
            ),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # AttributeError：段落不是 dict 时 .get/[] 会抛——一并视为「读不了」（fail-closed）。
        return None
    if mandate.schema_version != PAY_MANDATE_SCHEMA_VERSION:
        return None  # 未知未来版本：fail-closed，对版产品 gate 的版本拒绝分支
    return mandate
