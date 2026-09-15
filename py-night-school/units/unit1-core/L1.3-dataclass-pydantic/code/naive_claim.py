"""手写朴素类——Java 视角的「正常写法」，Python 视角的完整痛苦版。

对照 Java：一个只有字段 + 构造器 + toString + equals 的值类，
在 Java 里交给 IDE 生成（或直接换 record）；在 Python 里手写意味着：
  - 字段不存在「类体声明」这回事，全靠 __init__ 里逐个 self.x = x 挂上去；
  - __repr__（≈ toString）不写的话打印出来是 <__main__.ExpenseClaimManual object at 0x...>；
  - __eq__（≈ equals）不写的话，两个内容相同的实例也不相等；
  - 更阴的：一旦定义了 __eq__，Python 自动把 __hash__ 置为 None——实例变不可哈希
    （对照 Java「重写 equals 必须重写 hashCode」的镜像坑，只是 Python 替你「强制翻车」）。

本文件存在的意义就是让你亲手痛一次——下一站 dataclass 才知道它替你干了什么。
"""


class ExpenseClaimManual:
    """报销单（手写版）。金额单位：整数「分」（夜校全教程的约定）。"""

    def __init__(
        self,
        claim_id: str,
        submitter: str,
        items_cents: list[int] | None = None,
        note: str = "",
    ) -> None:
        # self 是什么：方法本质是普通函数，实例只是第一个参数（讲义 §2.1 展开讲）
        self.claim_id = claim_id
        self.submitter = submitter
        # 可变默认值的纪律写法：默认值不能写 items_cents=[]（理由见讲义 §5 坑位），
        # 惯用 None 哨兵 + 函数体内替换成新列表——对照 Java 的 items = new ArrayList<>() 每次构造新建。
        self.items_cents = items_cents if items_cents is not None else []
        self.note = note

    def __repr__(self) -> str:
        # {x!r} 里的 !r 表示用 repr() 渲染（字符串会带引号）；f-string 语法在 L0.1 已见过
        return (
            f"ExpenseClaimManual(claim_id={self.claim_id!r}, submitter={self.submitter!r}, "
            f"items_cents={self.items_cents!r}, note={self.note!r})"
        )

    def __eq__(self, other: object) -> bool:
        # 对照 Java equals：先类型检查再逐字段比较；返回 NotImplemented（不是 False！）
        # 是 Python 协议：让解释器去问对方类型的 __eq__，双方都不认才判不等。
        if not isinstance(other, ExpenseClaimManual):
            return NotImplemented
        return (
            self.claim_id == other.claim_id
            and self.submitter == other.submitter
            and self.items_cents == other.items_cents
            and self.note == other.note
        )

    # 注意：没有 __hash__——定义 __eq__ 后 Python 自动置 __hash__ = None，
    # 本类实例不能放进 set / 当 dict 的 key（测试里验证给你看）。
