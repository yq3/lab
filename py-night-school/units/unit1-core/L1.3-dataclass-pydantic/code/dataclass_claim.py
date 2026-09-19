"""dataclass 版报销单——与 naive_claim.ExpenseClaimManual 行为等价，几行干完几十行的活。

@dataclass 是装饰器：L1.5 会拆开它的原理，本课先当「语法」用——
它读类体里的「类型标注」，自动生成 __init__ / __repr__ / __eq__：
  - claim_id: str          <- 「字段名: 类型」既是类型标注，也是 dataclass 的字段声明
  - 有默认值的字段排后面（与 Java「构造参数带默认值」同理，无默认在前有默认在后）
"""

from dataclasses import dataclass, field


@dataclass
class ExpenseClaimData:
    """报销单（dataclass 版）：自动获得 __init__ / __repr__ / __eq__，且 eq 默认全字段参与。"""

    claim_id: str
    submitter: str
    # 可变默认值的唯一正确姿势：field(default_factory=list)——「每个实例调一次 list() 现做」。
    # 裸写 items_cents: list[int] = [] 会在类定义时直接 ValueError（讲义 §5 最小复现）。
    items_cents: list[int] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class Policy:
    """不可变值对象——Java record 的最近对应物。

    frozen=True 后：给字段赋值抛 FrozenInstanceError；同时自动生成 __hash__，
    实例可当 dict 的 key / 进 set（普通 @dataclass 定义了 __eq__ 就不可哈希）。
    对照 record：record 的 final 字段天然不可变 + 基于全字段的 hashCode。
    """

    item_limit_cents: int
    total_limit_cents: int


# 重要边界：dataclass 不验证任何东西——类型标注在 dataclass 里只是「文档 + IDE 提示」。
# ExpenseClaimData(claim_id="garbage", submitter="", items_cents=[-5]) 照样构造成功，
# 不会抛任何错（测试 test_dataclass_validates_nothing 验证给你看）。要「构造即验证」，看 claims.py。
